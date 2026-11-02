"""Benchmark Lexdiff against a keyword search on a target whose violations are tagged in source.

Tags: ``PLANTED:<id>:<kind>`` marks a violation, ``DECOY:<id>:<kind>`` marks something that looks bad
but is fine. Numbers are computed here, never hard-coded.
"""
from __future__ import annotations

import re
from pathlib import Path

from .canary import run_canary
from .graph import build_graph
from .guard import run_guard
from .util import iter_files, load_target_config

TAG = re.compile(r"(PLANTED|DECOY):(\w+):(\w+)")
KEYWORDS = re.compile(r"\b(ssn|tin|social|account_number|acct|password|secret)\b", re.I)


def collect_tags(target: Path) -> list[dict]:
    tags = []
    for p in iter_files(target, suffixes=(".py", ".sql", ".json", ".md"), skip_tests=True):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            m = TAG.search(line)
            if m:
                tags.append({"role": m.group(1).lower(), "id": m.group(2), "kind": m.group(3),
                             "file": p.relative_to(target).as_posix(), "line": i})
    return tags


def keyword_baseline(target: Path) -> dict:
    lines, files = 0, set()
    for p in iter_files(target, skip_tests=True):
        n = sum(1 for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if KEYWORDS.search(ln))
        if n:
            lines += n
            files.add(p.relative_to(target).as_posix())
    return {"lines": lines, "files": files}


def run_benchmark(target) -> dict:
    target = Path(target).resolve()
    cfg = load_target_config(target)
    tags = collect_tags(target)
    planted = [t for t in tags if t["role"] == "planted"]
    decoys = [t for t in tags if t["role"] == "decoy"]
    findings = run_guard(target, cfg, build_graph(target, cfg))
    canary = run_canary(target, cfg)
    at_line = {(f.file, f.line) for f in findings}
    has_notice = any(f.rule == "G-NOTICE" for f in findings)

    def lexdiff_found(t) -> bool:
        if t["kind"] == "notice":
            return has_notice
        if t["kind"] == "db":
            return canary["by_store"].get("db", 0) > 0
        return (t["file"], t["line"]) in at_line

    kw = keyword_baseline(target)
    found = [t for t in planted if lexdiff_found(t)]
    missed = [t for t in planted if not lexdiff_found(t)]
    kw_found = [t for t in planted if t["file"] in kw["files"]]
    kw_decoys = [d for d in decoys if d["file"] in kw["files"]]
    return {
        "planted": len(planted), "decoys": len(decoys),
        "lexdiff": {"found": len(found), "missed": [f"{t['id']} ({t['kind']})" for t in missed],
                    "findings": len(findings), "decoys_flagged": sum(1 for d in decoys if (d["file"], d["line"]) in at_line)},
        "keyword": {"found_by_file": len(kw_found), "lines_to_triage": kw["lines"], "decoys_flagged": len(kw_decoys)},
        "note": "n = 1 target app, built by us. Violations outside the current rule packs are reported as missed.",
    }


def format_benchmark(r: dict) -> str:
    kw, lx = r["keyword"], r["lexdiff"]
    rows = [
        ("Approach", "Found", "To triage", "Decoys flagged"),
        ("Keyword search", f"{kw['found_by_file']} (by file)", f"{kw['lines_to_triage']} lines", str(kw["decoys_flagged"])),
        ("Lexdiff guard+canary", f"{lx['found']} of {r['planted']}", f"{lx['findings']} (each cites a clause)", str(lx["decoys_flagged"])),
    ]
    widths = [max(len(row[i]) for row in rows) + 3 for i in range(4)]
    table = ["".join(c.ljust(w) for c, w in zip(row, widths)).rstrip() for row in rows]
    return "\n".join([
        f"Target has {r['planted']} planted violations and {r['decoys']} decoys.", "", *table, "",
        "Missed by Lexdiff today (next rule packs): " + (", ".join(lx["missed"]) or "none"),
        r["note"],
    ])
