"""Step 9 - Guard: a zero-LLM static gate that fails a pull request on the exact offending line.

Every finding cites the clause that makes it a finding. No model is called, so results are
deterministic and auditable. Exit status 1 when anything is found.
"""
from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .graph import build_graph
from .util import load_target_config

CLAUSE = {
    "G-LOG": "16 CFR 314.4(c)(3)",
    "G-EXPORT": "16 CFR 314.4(c)(3)",
    "G-MFA": "16 CFR 314.4(c)(5)",
    "G-NOTICE": "16 CFR 314.4(j)(1)",
}


@dataclass
class Finding:
    rule: str
    clause: str
    file: str
    line: int
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def _notice_missing(target: Path, cfg: dict) -> str | None:
    notice = cfg.get("notice")
    if not notice:
        return None
    rel = notice["module"].replace(".", "/") + ".py"
    path = target / rel
    if path.exists():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(isinstance(n, ast.FunctionDef) and n.name == notice["function"] for n in ast.walk(tree)):
                return None
        except SyntaxError:
            pass
    return rel


def run_guard(target, cfg: dict | None = None, graph=None) -> list[Finding]:
    target = Path(target)
    cfg = cfg or load_target_config(target)
    g = graph or build_graph(target, cfg)
    public = cfg.get("public_routes", [])
    findings: list[Finding] = []
    for s in g.log_leaks():
        findings.append(Finding("G-LOG", CLAUSE["G-LOG"], s.file, s.line,
                                f"Log call passes sensitive argument: {', '.join(s.sensitive)}"))
    for sink, fi in g.export_leaks():
        findings.append(Finding("G-EXPORT", CLAUSE["G-EXPORT"], sink.file, sink.line,
                                f"File write in a function that reads sensitive columns ({', '.join(fi.sensitive_sql)})"))
    for r in g.routes_missing_mfa(public):
        findings.append(Finding("G-MFA", CLAUSE["G-MFA"], r.file, r.line,
                                f"Route {r.method} {r.path} is not protected by the second-factor decorator"))
    missing = _notice_missing(target, cfg)
    if missing:
        n = cfg["notice"]
        findings.append(Finding("G-NOTICE", CLAUSE["G-NOTICE"], missing, 1,
                                f"No breach-notification handler: expected {n['module']}.{n['function']}()"))
    findings.sort(key=lambda f: (f.file, f.line, f.rule))
    return findings


def format_findings(findings: list[Finding], fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps([f.to_dict() for f in findings], indent=2)
    if fmt == "github":  # GitHub Actions annotations: annotate the pull-request line
        return "\n".join(f"::error file={f.file},line={f.line},title={f.rule} · {f.clause}::{f.message}" for f in findings)
    if not findings:
        return "Guard: no findings."
    return "\n".join(f"{f.file}:{f.line}  {f.rule}  {f.clause}  {f.message}" for f in findings)
