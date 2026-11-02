"""Step 8 - Evidence: a graded certificate that never says "compliant"."""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from . import __version__

GRADES = ["Verified", "Partially verified", "Unverified", "Human review required"]
CAVEATS = [
    "Automated checks only. This certificate states what Lexdiff's tests verified; it is not a statement of "
    "compliance and not legal advice.",
    "Only code-checkable obligations are covered. Policies, training, vendor oversight and similar duties need "
    "human review.",
    "Evidence applies to the exact base and head source trees recorded by the hashes below.",
]


def grade(ob: dict, rows: list[dict]) -> tuple[str, str]:
    if ob["kind"] == "manual_review" or not rows:
        return "Human review required", "No automated test applies to this obligation."
    verdicts = [r["verdict"] for r in rows]
    if "regression" in verdicts:
        return "Unverified", "A check that passed before now fails."
    good, held = verdicts.count("discriminating"), verdicts.count("already_passing")
    failing = [r["name"] for r in rows if r["verdict"] == "failing_on_head"]
    if not failing and good:
        extra = f"; {held} already passed on the base and stay as regression guards" if held else ""
        return "Verified", f"{good} check(s) fail on the base and pass on the fix{extra}."
    if failing and good:
        return "Partially verified", f"{good} of {len(rows)} checks proven; still failing on the fix: {', '.join(failing)}."
    return "Unverified", "No check both failed before and passed after the change."


def build_certificate(obligations, verification: dict, base_label: str, head_label: str, rewrites=None) -> dict:
    tests = verification["tests"]
    rows_out, summary = [], {g: 0 for g in GRADES}
    for ob in obligations:
        rows = [{"name": c["name"], **tests[c["name"]]} for c in ob.checks if c["name"] in tests]
        g, note = grade(ob.to_dict(), rows)
        if not verification["integrity"]["clean"] and g in ("Verified", "Partially verified"):
            g, note = "Unverified", "Locked tests changed without an approved rewrite: " + "; ".join(verification["integrity"]["violations"])
        summary[g] += 1
        rows_out.append({"id": ob.id, "clause": ob.clause, "quote": ob.quote, "requirement": ob.requirement,
                         "status": ob.status, "approved_by": ob.approved_by, "approved_at": ob.approved_at,
                         "grade": g, "note": note, "tests": rows})
    base_total, head_total = verification["canary"]["base"]["total"], verification["canary"]["head"]["total"]
    return {
        "run_id": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "lexdiff_version": __version__,
        "base": {"label": base_label, "tree_sha256": verification["artifacts"]["base_tree_sha256"]},
        "head": {"label": head_label, "tree_sha256": verification["artifacts"]["head_tree_sha256"]},
        "test_engine": verification["engine"],
        "summary": summary,
        "obligations": rows_out,
        "canary": {"base_hits": base_total, "head_hits": head_total,
                   "base_by_store": verification["canary"]["base"]["by_store"],
                   "head_by_store": verification["canary"]["head"]["by_store"]},
        "guard_head_findings": len(verification["guard_head"]),
        "integrity": verification["integrity"],
        "regression": verification["regression"],
        "approved_test_rewrites": rewrites or [],
        "caveats": CAVEATS,
    }


def write_certificate(cert: dict, out_dir) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, hp = out_dir / "certificate.json", out_dir / "certificate.html"
    jp.write_text(json.dumps(cert, indent=2), encoding="utf-8")
    hp.write_text(render_html(cert), encoding="utf-8")
    return jp, hp


COLORS = {"Verified": "#34d399", "Partially verified": "#60a5fa", "Unverified": "#f25f4c", "Human review required": "#fbbf24"}


def render_html(cert: dict) -> str:
    e = html.escape
    rows = ""
    for ob in cert["obligations"]:
        tests = "".join(
            f"<li><code>{e(t['name'])}</code> base:{e(t['base'])} head:{e(t['head'])} <em>{e(t['verdict'])}</em></li>"
            for t in ob["tests"]) or "<li>no automated tests</li>"
        rows += (f"<tr><td>{e(ob['id'])}</td><td>{e(ob['clause'])}</td><td><q>{e(ob['quote'])}</q></td>"
                 f"<td style='color:{COLORS[ob['grade']]};font-weight:700'>{e(ob['grade'])}</td>"
                 f"<td>{e(ob['note'])}<ul>{tests}</ul><small>approved by {e(ob['approved_by'] or 'n/a')}</small></td></tr>")
    summary = " · ".join(f"{e(k)}: {v}" for k, v in cert["summary"].items())
    caveats = "".join(f"<li>{e(c)}</li>" for c in cert["caveats"])
    return f"""<!doctype html><meta charset="utf-8"><title>Lexdiff Evidence Certificate</title>
<style>body{{font:15px/1.5 system-ui;background:#0b1220;color:#f1f5f9;max-width:1100px;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #26324a;padding:.6rem;vertical-align:top;text-align:left}}
th{{background:#26324a}}code{{color:#94a3b8}}small{{color:#94a3b8}}</style>
<h1>Lexdiff Evidence Certificate</h1>
<p>Run {e(cert['run_id'])} · Lexdiff {e(cert['lexdiff_version'])} · test engine {e(cert['test_engine'])}</p>
<p><b>Base</b> {e(cert['base']['label'])} <code>{cert['base']['tree_sha256'][:16]}</code><br>
<b>Head</b> {e(cert['head']['label'])} <code>{cert['head']['tree_sha256'][:16]}</code></p>
<p><b>{summary}</b></p>
<p>Canary hits (synthetic customer data found in stores): base {cert['canary']['base_hits']} → head {cert['canary']['head_hits']}.
Guard findings on head: {cert['guard_head_findings']}. Locked tests clean: {cert['integrity']['clean']}.
Regression suite green: {cert['regression']['green']}. Human-approved test rewrites: {len(cert['approved_test_rewrites'])}.</p>
<table><tr><th>Obligation</th><th>Clause</th><th>Quote</th><th>Grade</th><th>Evidence</th></tr>{rows}</table>
<h3>Read this first</h3><ul>{caveats}</ul>"""


def format_summary(cert: dict) -> str:
    lines = ["", "Obligation  Clause          Grade"]
    for ob in cert["obligations"]:
        lines.append(f"{ob['id']:<11} {ob['clause']:<15} {ob['grade']}")
    lines.append("")
    lines.append(f"Canary hits: {cert['canary']['base_hits']} -> {cert['canary']['head_hits']}  "
                 f"(head by store: {cert['canary']['head_by_store']})")
    lines.append("This certificate states what automated checks verified. It never says 'compliant'.")
    return "\n".join(lines)
