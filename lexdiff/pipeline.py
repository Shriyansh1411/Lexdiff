"""End-to-end orchestration of the nine Lexdiff stages.

1 Screen -> 2 Redline -> 3 Obligations (+ human approval) -> 4 Impact -> 5 Failing tests
-> 6 Canary -> 7 Prove -> 8 Evidence -> 9 Guard
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .canary import run_canary
from .evidence import build_certificate, format_summary, write_certificate
from .graph import build_graph
from .guard import format_findings, run_guard
from .llm import LLMClient
from .obligations import approve, load_obligations, save_obligation
from .obligations.draft import draft
from .obligations.planner import plan_checks
from .obligations.testgen import generate
from .proof import open_source, verify
from .regulation import actionable, format_changes, parse_text_file, redline, word_count
from .screen import screen
from .util import load_target_config


class Workspace:
    """Where Lexdiff keeps its files for one repository."""

    def __init__(self, root="."):
        self.root = Path(root).resolve()
        self.obligations = self.root / "compliance" / "obligations"
        self.tests = self.root / "compliance" / "tests"
        self.lock = self.root / "compliance" / "tests.lock.json"
        self.changes = self.root / "compliance" / "test_changes.yaml"
        self.out = self.root / ".lexdiff"

    def save_json(self, name: str, data) -> Path:
        self.out.mkdir(parents=True, exist_ok=True)
        p = self.out / name
        p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return p

    def rewrites(self) -> list:
        return (yaml.safe_load(self.changes.read_text()) or []) if self.changes.exists() else []


def run_pipeline(root, base, head, reg_old, reg_new, approver="", client: LLMClient | None = None,
                 engine="auto", log=print) -> dict:
    ws = Workspace(root)
    client = client or LLMClient()
    with open_source(base) as b, open_source(head) as h:
        cfg = load_target_config(b.path)

        log("[1/9] Screen: checking repo text for instructions aimed at AI agents")
        scr = screen(b.path, client)
        ws.save_json("screen.json", scr)
        log(f"      {len(scr['flagged'])} of {scr['scanned']} comments/docstrings flagged")
        for f in scr["flagged"]:
            log(f"      ! {f['file']}:{f['line']} {f['reason']}: {f['text'][:70]}")

        log("[2/9] Redline: diffing the regulation clause by clause")
        old, new = parse_text_file(reg_old), parse_text_file(reg_new)
        changes = redline(old, new)
        ws.save_json("redline.json", {"old_words": word_count(old), "new_words": word_count(new),
                                      "changes": [c.to_dict() for c in changes]})
        log(f"      {word_count(old)} -> {word_count(new)} words; {len(changes)} clause changes")
        log("\n".join("      " + ln for ln in format_changes(changes).splitlines()))

        log("[3/9] Obligations: drafting from verbatim clause text (quotes must be verbatim)")
        res = draft(actionable(changes), client)
        for n in res.notes:
            log("      note: " + n)
        for r in res.rejected:
            log(f"      rejected {r['clause']}: {r['reason']}")
        for ob in res.obligations:
            save_obligation(ob, ws.obligations)
        log(f"      {len(res.obligations)} drafted, {len(res.rejected)} rejected")
        if not approver:
            log("      Obligations are 'proposed'. A named human must approve them: "
                "lexdiff approve <ID> --by <name>, or re-run with --approver.")
            return {"stopped": "awaiting_approval", "obligations": [o.id for o in res.obligations]}
        for ob in res.obligations:
            approve(ws.obligations, ob.id, approver)
        log(f"      approved by {approver}")

        log("[4/9] Impact: building the code graph of the base")
        graph = build_graph(b.path, cfg)
        ws.save_json("graph.json", graph.to_dict())
        st = graph.stats()
        log(f"      {st['nodes']} nodes, {st['edges']} edges; "
            f"{len(graph.routes_missing_mfa(cfg.get('public_routes', [])))} routes skip MFA; "
            f"{len(graph.traces())} sensitive trace(s)")

        log("[5/9] Fix: writing the failing obligation tests first (hash-locked)")
        obligations = load_obligations(ws.obligations)
        for ob in obligations:
            ob.checks = plan_checks(ob, graph, cfg)
            save_obligation(ob, ws.obligations)
        written = generate(obligations, ws.tests, ws.lock, ws.changes)
        log(f"      {sum(len(o.checks) for o in obligations)} checks in {len(written)} test files")

        log("[6/9] Canary: planting a synthetic SSN and bank account, sweeping every store")
        before = run_canary(b.path, cfg)
        ws.save_json("canary_base.json", before)
        log(f"      base hits {before['by_store']}")

        log("[7/9] Prove: each obligation test must fail on base and pass on the fix")
        ver = verify(b.path, h.path, ws.tests, ws.lock, ws.changes, engine=engine)
        ws.save_json("verification.json", ver)
        rows = ver["tests"]
        disc = sum(1 for r in rows.values() if r["verdict"] == "discriminating")
        log(f"      {disc} of {len(rows)} tests discriminate (test engine: {ver['engine']}); "
            f"regression suite green: {ver['regression']['green']}; locked tests clean: {ver['integrity']['clean']}")

        log("[8/9] Evidence: grading each obligation")
        cert = build_certificate(obligations, ver, b.label, h.label, ws.rewrites())
        jp, hp = write_certificate(cert, ws.out)

        log("[9/9] Guard: zero-LLM gate over the fix")
        findings = run_guard(h.path, cfg)
        log("      " + format_findings(findings).replace("\n", "\n      "))
        log(format_summary(cert))
        log(f"\nCertificate: {hp}")
        return {"certificate": cert, "paths": {"json": str(jp), "html": str(hp)}}
