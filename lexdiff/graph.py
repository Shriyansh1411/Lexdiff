"""Step 4 - Impact: a code graph of routes, mounted blueprints, SQL view aliases and data sinks.

Pure static analysis (``ast`` + regex), no model. It answers:
  * which routes skip the MFA decorator (including blueprints mounted under a prefix)?
  * which log calls pass customer data or the raw request body?
  * where does a sensitive column go after a SQL view renames it (ssn -> tin) into a file write?
"""
from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .util import iter_files

HTTP_VERBS = {"get", "post", "put", "delete", "patch"}
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
LOG_OBJECTS = {"logger", "log", "logging", "LOGGER"}
BODY_ATTRS = {"data", "json", "form", "stream", "values"}
BODY_CALLS = {"get_data", "get_json"}
FILE_WRITE_ATTRS = {"write", "writerow", "writerows"}
SAFE_WRAPPER = re.compile(r"^(mask|redact|hash|scrub|encrypt|tokenize)", re.I)
VIEW_RE = re.compile(
    r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS\s+SELECT\s+(.*?)\s+FROM\s+(.*?)(?:;|$)", re.I | re.S)
COLUMN_RE = re.compile(r"^(?:(\w+)\.)?(\w+)(?:\s+AS\s+(\w+))?$", re.I)
TABLE_RE = re.compile(r"(?:FROM|JOIN)\s+(\w+)(?:\s+(?:AS\s+)?(?!JOIN\b|ON\b|WHERE\b|LEFT\b|INNER\b)(\w+))?", re.I)


@dataclass
class Route:
    method: str
    path: str
    function: str
    file: str
    line: int
    has_mfa: bool


@dataclass
class Sink:
    kind: str  # log | file_write
    file: str
    line: int
    function: str
    sensitive: list = field(default_factory=list)


@dataclass
class View:
    name: str
    sensitive_aliases: dict = field(default_factory=dict)  # alias -> table.column


@dataclass
class FunctionInfo:
    name: str
    file: str
    line: int
    sensitive_sql: list = field(default_factory=list)


@dataclass
class Graph:
    routes: list = field(default_factory=list)
    sinks: list = field(default_factory=list)
    views: list = field(default_factory=list)
    functions: list = field(default_factory=list)
    sensitive_names: list = field(default_factory=list)

    def routes_missing_mfa(self, public=()) -> list[Route]:
        return [r for r in self.routes if not r.has_mfa and r.path not in set(public)]

    def log_leaks(self) -> list[Sink]:
        return [s for s in self.sinks if s.kind == "log" and s.sensitive]

    def export_leaks(self) -> list[tuple[Sink, FunctionInfo]]:
        funcs = {(f.file, f.name): f for f in self.functions}
        out = []
        for s in self.sinks:
            fi = funcs.get((s.file, s.function))
            if s.kind == "file_write" and fi and fi.sensitive_sql:
                out.append((s, fi))
        return out

    def traces(self) -> list[str]:
        alias_src = {a: src for v in self.views for a, src in v.sensitive_aliases.items()}
        view_of = {a: v.name for v in self.views for a in v.sensitive_aliases}
        out = []
        for sink, fi in self.export_leaks():
            for name in fi.sensitive_sql:
                head = f"{alias_src[name]} -> {view_of[name]}.{name}" if name in alias_src else name
                out.append(f"{head} -> job:{fi.file} -> file_write:{sink.file}:{sink.line}")
        return sorted(set(out))

    def stats(self) -> dict:
        nodes = len(self.routes) + len(self.functions) + len(self.sinks) + len(self.views)
        edges = len(self.routes) + len(self.sinks) + sum(len(v.sensitive_aliases) for v in self.views) \
            + sum(len(f.sensitive_sql) for f in self.functions)
        return {"nodes": nodes, "edges": edges, "routes": len(self.routes), "sinks": len(self.sinks),
                "views": len(self.views)}

    def to_dict(self) -> dict:
        return {
            "stats": self.stats(),
            "routes": [asdict(r) for r in self.routes],
            "sinks": [asdict(s) for s in self.sinks],
            "views": [asdict(v) for v in self.views],
            "functions": [asdict(f) for f in self.functions],
            "traces": self.traces(),
        }


def _split_top_level(text: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def parse_views(sql: str, sensitive: set[str]) -> list[View]:
    views = []
    for m in VIEW_RE.finditer(sql):
        name, select_list, from_part = m.group(1), m.group(2), m.group(3)
        tables = {}
        for table, alias in TABLE_RE.findall("FROM " + from_part):
            tables[alias or table] = table
        v = View(name)
        for item in _split_top_level(select_list):
            cm = COLUMN_RE.match(item)
            if not cm:  # expression such as substr(a.ssn, -4): derived/masked, not propagated
                continue
            prefix, col, alias = cm.group(1), cm.group(2), cm.group(3) or cm.group(2)
            if col in sensitive:
                v.sensitive_aliases[alias] = f"{tables.get(prefix, prefix or '?')}.{col}"
        views.append(v)
    return views


def _is_request(node) -> bool:
    return isinstance(node, ast.Name) and node.id == "request"


def sensitive_in(node, names: set[str]) -> list[str]:
    """Names of sensitive data an expression would pass along (masked forms are safe)."""
    found: list[str] = []

    def visit(n):
        if isinstance(n, ast.Call):
            fn = n.func
            fname = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
            if SAFE_WRAPPER.match(fname):
                return
            if isinstance(fn, ast.Attribute) and fn.attr in BODY_CALLS and _is_request(fn.value):
                found.append("request body")
                return
        if isinstance(n, ast.Subscript):
            if isinstance(n.slice, ast.Slice):
                lo = n.slice.lower
                if isinstance(lo, ast.UnaryOp) and isinstance(lo.op, ast.USub) \
                        and isinstance(lo.operand, ast.Constant) and lo.operand.value <= 4:
                    return  # ssn[-4:] keeps only the last four characters
            elif isinstance(n.slice, ast.Constant) and n.slice.value in names:
                found.append(str(n.slice.value))
                return
        if isinstance(n, ast.Name) and n.id in names:
            found.append(n.id)
            return
        if isinstance(n, ast.Attribute):
            if n.attr in names:
                found.append(n.attr)
                return
            if n.attr in BODY_ATTRS and _is_request(n.value):
                found.append("request body")
                return
        for child in ast.iter_child_nodes(n):
            visit(child)

    visit(node)
    return found


def _decorator_info(dec):
    """Return (verb_or_route, path, methods) for a Flask-style route decorator, else None."""
    if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
        return None
    attr = dec.func.attr
    if attr not in HTTP_VERBS and attr != "route":
        return None
    if not dec.args or not isinstance(dec.args[0], ast.Constant) or not isinstance(dec.args[0].value, str):
        return None
    if attr == "route":
        methods = ["GET"]
        for kw in dec.keywords:
            if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                methods = [e.value.upper() for e in kw.value.elts if isinstance(e, ast.Constant)]
    else:
        methods = [attr.upper()]
    return dec.args[0].value, methods, dec.func.value.id if isinstance(dec.func.value, ast.Name) else ""


def build_graph(target, cfg: dict | None = None) -> Graph:
    from .util import load_target_config

    target = Path(target)
    cfg = cfg or load_target_config(target)
    base_names = set(cfg.get("sensitive_names", ["ssn", "account_number"]))
    mfa_name = (cfg.get("mfa") or {}).get("decorator", "require_mfa")

    trees: dict[str, ast.AST] = {}
    for p in iter_files(target, skip_tests=True):
        try:
            trees[p.relative_to(target).as_posix()] = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

    g = Graph(sensitive_names=sorted(base_names))

    # Pass A: SQL views (their column renames extend the set of sensitive names).
    views: dict[str, View] = {}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and "VIEW" in node.value.upper():
                for v in parse_views(node.value, base_names):
                    views[v.name] = v
    g.views = list(views.values())
    sensitive = set(base_names)
    sensitive_views = set()
    for v in g.views:
        sensitive |= set(v.sensitive_aliases)
        if v.sensitive_aliases:
            sensitive_views.add(v.name)

    # Pass B: blueprint prefixes (mounted sub-apps and in-module url_prefix).
    mounted: dict[str, str] = {}
    local_prefix: dict[tuple[str, str], str] = {}
    for rel, tree in trees.items():
        module = Path(rel).stem
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "register_blueprint" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
                    for kw in node.keywords:
                        if kw.arg == "url_prefix" and isinstance(kw.value, ast.Constant):
                            mounted[arg.value.id] = kw.value.value
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                    and getattr(node.value.func, "id", getattr(node.value.func, "attr", "")) == "Blueprint":
                for kw in node.value.keywords:
                    if kw.arg == "url_prefix" and isinstance(kw.value, ast.Constant):
                        for t in node.targets:
                            if isinstance(t, ast.Name):
                                local_prefix[(module, t.id)] = kw.value.value

    # Pass C: routes, sinks and sensitive SQL per function.
    seen_sinks: set[tuple] = set()
    for rel, tree in trees.items():
        module = Path(rel).stem
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            has_mfa = any(
                (isinstance(d, ast.Name) and d.id == mfa_name) or (isinstance(d, ast.Attribute) and d.attr == mfa_name)
                for d in fn.decorator_list)
            for dec in fn.decorator_list:
                info = _decorator_info(dec)
                if info:
                    path, methods, bp_var = info
                    full = mounted.get(module, "") + local_prefix.get((module, bp_var), "") + path
                    for method in methods:
                        g.routes.append(Route(method, full, fn.name, rel, fn.lineno, has_mfa))

            matched_sql: set[str] = set()
            for node in ast.walk(fn):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(r"\bselect\b", node.value, re.I):
                    for name in sensitive | sensitive_views:
                        if re.search(rf"\b{re.escape(name)}\b", node.value, re.I):
                            if name in sensitive:
                                matched_sql.add(name)
                            else:  # reading a view that renames sensitive columns exposes all of its aliases
                                matched_sql |= set(views[name].sensitive_aliases)
            if matched_sql:
                g.functions.append(FunctionInfo(fn.name, rel, fn.lineno, sorted(matched_sql)))

            for node in ast.walk(fn):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                attr, owner = node.func.attr, node.func.value
                if attr in LOG_METHODS and isinstance(owner, ast.Name) and owner.id in LOG_OBJECTS:
                    leaks: list[str] = []
                    for arg in list(node.args[1:]) + [k.value for k in node.keywords]:
                        leaks += sensitive_in(arg, sensitive)
                    if node.args and isinstance(node.args[0], ast.JoinedStr):
                        leaks += sensitive_in(node.args[0], sensitive)
                    key = ("log", rel, node.lineno)
                    if key not in seen_sinks:
                        seen_sinks.add(key)
                        g.sinks.append(Sink("log", rel, node.lineno, fn.name, sorted(set(leaks))))
                elif attr in FILE_WRITE_ATTRS or (attr == "dump" and isinstance(owner, ast.Name) and owner.id in {"json", "pickle"}):
                    key = ("file_write", rel, node.lineno)
                    if key not in seen_sinks:
                        seen_sinks.add(key)
                        g.sinks.append(Sink("file_write", rel, node.lineno, fn.name))
    g.routes.sort(key=lambda r: (r.file, r.line, r.method))
    g.sinks.sort(key=lambda s: (s.file, s.line))
    return g


def summarize(g: Graph, public=()) -> str:
    st = g.stats()
    lines = [f"Graph: {st['nodes']} nodes, {st['edges']} edges"]
    missing = g.routes_missing_mfa(public)
    lines.append(f"\nRoutes missing MFA ({len(missing)}):")
    lines += [f"  {r.file}:{r.line}  {r.method} {r.path}" for r in missing]
    leaks = g.log_leaks()
    lines.append(f"\nLog calls passing sensitive data ({len(leaks)}):")
    lines += [f"  {s.file}:{s.line}  {', '.join(s.sensitive)}" for s in leaks]
    exports = g.export_leaks()
    lines.append(f"\nSensitive data reaching file writes ({len(exports)}):")
    lines += [f"  {s.file}:{s.line}  {', '.join(fi.sensitive_sql)}" for s, fi in exports]
    traces = g.traces()
    if traces:
        lines.append("\nTraces:")
        lines += [f"  {t}" for t in traces]
    return "\n".join(lines)
