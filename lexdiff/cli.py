"""Command-line interface: ``python -m lexdiff <command>``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .benchmark import format_benchmark, run_benchmark
from .canary import run_canary
from .graph import build_graph, summarize
from .guard import format_findings, run_guard
from .llm import LLMClient
from .obligations import approve, load_obligations
from .obligations.draft import draft
from .obligations.model import validate_dir
from .obligations.planner import plan_checks
from .obligations.testgen import LockedTestError, generate
from .pipeline import Workspace, run_pipeline
from .proof import open_source, verify
from .regulation import actionable, format_changes, parse_text_file, redline, word_count
from .screen import screen
from .util import load_target_config


def _out(args, data, text):
    print(json.dumps(data, indent=2, default=str) if getattr(args, "json", False) else text)


def cmd_screen(a):
    r = screen(a.target, LLMClient())
    _out(a, r, f"Screened {r['scanned']} comments/docstrings; {len(r['flagged'])} flagged\n" +
         "\n".join(f"  {f['file']}:{f['line']}  {f['reason']}: {f['text'][:80]}" for f in r["flagged"]))
    return 1 if r["flagged"] else 0


def cmd_redline(a):
    old, new = parse_text_file(a.old), parse_text_file(a.new)
    ch = redline(old, new)
    _out(a, [c.to_dict() for c in ch], f"{word_count(old)} -> {word_count(new)} words\n{format_changes(ch)}")
    return 0


def cmd_fetch(a):
    from .regulation.clauses import write_text_file
    from .regulation.ecfr import fetch_clauses

    clauses = fetch_clauses(a.date, a.section)
    write_text_file(a.out, clauses, header=f"16 CFR {a.section} as in force on {a.date}, fetched from eCFR")
    print(f"Wrote {len(clauses)} clauses ({word_count(clauses)} words) to {a.out}")
    return 0


def cmd_draft(a):
    ws = Workspace(a.root)
    ch = actionable(redline(parse_text_file(a.old), parse_text_file(a.new)))
    res = draft(ch, LLMClient())
    from .obligations import save_obligation

    for ob in res.obligations:
        save_obligation(ob, ws.obligations)
    _out(a, {"drafted": [o.to_dict() for o in res.obligations], "rejected": res.rejected},
         "\n".join([f"{o.id}  {o.clause}  [{o.source}]  \"{o.quote[:70]}...\"" for o in res.obligations] +
                   [f"REJECTED {r['clause']}: {r['reason']}" for r in res.rejected] + res.notes))
    return 0


def cmd_validate(a):
    rows = validate_dir(a.dir, parse_text_file(a.regulation))
    for r in rows:
        print(("OK        " if r["ok"] else "REJECTED  ") + f"{r['id']}: {r['reason']}")
    if all(r["ok"] for r in rows):
        print("All obligations valid.")
    return 0 if all(r["ok"] for r in rows) else 1


def cmd_approve(a):
    ob = approve(Workspace(a.root).obligations, a.id, a.by)
    print(f"{ob.id} approved by {ob.approved_by} at {ob.approved_at}")
    return 0


def cmd_graph(a):
    cfg = load_target_config(a.target)
    g = build_graph(a.target, cfg)
    _out(a, g.to_dict(), summarize(g, cfg.get("public_routes", [])))
    return 0


def cmd_gen_tests(a):
    ws = Workspace(a.root)
    cfg = load_target_config(a.target)
    g = build_graph(a.target, cfg)
    obs = load_obligations(ws.obligations)
    from .obligations import save_obligation

    for ob in obs:
        ob.checks = plan_checks(ob, g, cfg)
        save_obligation(ob, ws.obligations)
    try:
        written = generate(obs, ws.tests, ws.lock, ws.changes, a.by if a.allow_rewrite else "", a.reason)
    except LockedTestError as exc:
        print(f"BLOCKED (exit 2): {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {len(written)} locked test files to {ws.tests}")
    return 0


def cmd_canary(a):
    r = run_canary(a.target)
    _out(a, r, f"Canary hits by store: {r['by_store']} (total {r['total']})\n" +
         "\n".join(f"  {h['path']}  {h['needle']} x{h['count']}" for h in r["hits"]))
    return 0


def cmd_verify(a):
    ws = Workspace(a.root)
    with open_source(a.base) as b, open_source(a.head) as h:
        v = verify(b.path, h.path, ws.tests, ws.lock, ws.changes, engine=a.engine)
    print("Fail before, pass after:")
    for name, r in v["tests"].items():
        print(f"  base {r['base'].upper():<7} head {r['head'].upper():<7} {r['verdict']:<19} {name}")
    disc = sum(1 for r in v["tests"].values() if r["verdict"] == "discriminating")
    print(f"\nVerification complete (engine: {v['engine']}).\n  Obligation tests : {len(v['tests'])}\n  Discriminating   : {disc}"
          f"\n  Integrity clean  : {v['integrity']['clean']}\n  Regression green : {v['regression']['green']}")
    ws.save_json("verification.json", v)
    return 0


def cmd_guard(a):
    cfg = load_target_config(a.target)
    findings = run_guard(a.target, cfg)
    print(format_findings(findings, a.format))
    return 1 if findings else 0


def cmd_benchmark(a):
    r = run_benchmark(a.target)
    _out(a, r, format_benchmark(r))
    return 0


def cmd_run(a):
    res = run_pipeline(a.root, a.base, a.head, a.reg_old, a.reg_new, a.approver, LLMClient(), a.engine)
    return 0 if "certificate" in res else 3


def cmd_dashboard(a):
    import subprocess

    app = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app), "--", "--root", a.root])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lexdiff", description="Diff the law. Test the code.")
    p.add_argument("--version", action="version", version=f"lexdiff {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    s = add("screen", cmd_screen, "flag comments aimed at AI agents (prompt injection)")
    s.add_argument("--target", required=True); s.add_argument("--json", action="store_true")
    s = add("redline", cmd_redline, "clause-level diff of two regulation versions")
    s.add_argument("--old", required=True); s.add_argument("--new", required=True); s.add_argument("--json", action="store_true")
    s = add("fetch-ecfr", cmd_fetch, "download a dated version of a CFR section from eCFR (needs network)")
    s.add_argument("--date", required=True); s.add_argument("--out", required=True); s.add_argument("--section", default="314.4")
    s = add("draft", cmd_draft, "draft obligations from a redline (verbatim quotes enforced)")
    s.add_argument("--old", required=True); s.add_argument("--new", required=True); s.add_argument("--root", default="."); s.add_argument("--json", action="store_true")
    s = add("validate", cmd_validate, "check every obligation quote is verbatim")
    s.add_argument("dir"); s.add_argument("--regulation", required=True)
    s = add("approve", cmd_approve, "a named human approves an obligation")
    s.add_argument("id"); s.add_argument("--by", required=True); s.add_argument("--root", default=".")
    s = add("graph", cmd_graph, "build the code graph of a target")
    s.add_argument("--target", required=True); s.add_argument("--json", action="store_true")
    s = add("gen-tests", cmd_gen_tests, "generate hash-locked obligation tests")
    s.add_argument("--target", required=True); s.add_argument("--root", default=".")
    s.add_argument("--allow-rewrite", action="store_true"); s.add_argument("--by", default=""); s.add_argument("--reason", default="")
    s = add("canary", cmd_canary, "plant synthetic data, run the app, sweep logs/exports/db")
    s.add_argument("--target", required=True); s.add_argument("--json", action="store_true")
    s = add("verify", cmd_verify, "prove: obligation tests fail on base and pass on the fix")
    s.add_argument("--base", required=True, help="directory or repo@ref"); s.add_argument("--head", required=True)
    s.add_argument("--root", default="."); s.add_argument("--engine", default="auto", choices=["auto", "pytest", "unittest"])
    s = add("guard", cmd_guard, "zero-LLM CI gate; exit 1 on findings")
    s.add_argument("--target", required=True); s.add_argument("--format", default="text", choices=["text", "json", "github"])
    s = add("benchmark", cmd_benchmark, "compare Lexdiff with a keyword search on a tagged target")
    s.add_argument("--target", required=True); s.add_argument("--json", action="store_true")
    s = add("run", cmd_run, "run all nine stages end to end")
    s.add_argument("--base", required=True); s.add_argument("--head", required=True)
    s.add_argument("--reg-old", required=True); s.add_argument("--reg-new", required=True)
    s.add_argument("--approver", default="", help="named human approving the drafted obligations")
    s.add_argument("--root", default="."); s.add_argument("--engine", default="auto", choices=["auto", "pytest", "unittest"])
    s = add("dashboard", cmd_dashboard, "open the Streamlit dashboard")
    s.add_argument("--root", default=".")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
