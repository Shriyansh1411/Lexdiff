"""Obligations: testable requirements drafted from clause text.

Every quote must be a verbatim span of the clause (whitespace-normalised). Paraphrases are rejected.
Obligations stay ``proposed`` until a named human approves them.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import yaml

from ..util import norm_ws


@dataclass
class Obligation:
    id: str
    clause: str
    quote: str
    requirement: str
    kind: str
    params: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    status: str = "proposed"  # proposed | approved
    approved_by: str = ""
    approved_at: str = ""
    source: str = "offline"  # offline | model

    def to_dict(self) -> dict:
        return asdict(self)


def validate_quote(quote: str, clause_text: str) -> tuple[bool, str]:
    q, c = norm_ws(quote), norm_ws(clause_text)
    if len(q.split()) < 4:
        return False, "quote is too short to be meaningful (minimum 4 words)"
    if q not in c:
        return False, "quote is not a verbatim substring of the clause text"
    return True, "ok"


def save_obligation(ob: Obligation, directory) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ob.id}.yaml"
    path.write_text(yaml.safe_dump(ob.to_dict(), sort_keys=False, width=100, allow_unicode=True), encoding="utf-8")
    return path


def load_obligations(directory) -> list[Obligation]:
    directory = Path(directory)
    names = {f.name for f in fields(Obligation)}
    out = []
    for p in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        out.append(Obligation(**{k: v for k, v in data.items() if k in names}))
    return out


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def approve(directory, ob_id: str, by: str) -> Obligation:
    if not by.strip():
        raise ValueError("approval needs a named human approver")
    for ob in load_obligations(directory):
        if ob.id == ob_id:
            ob.status, ob.approved_by, ob.approved_at = "approved", by.strip(), now_iso()
            save_obligation(ob, directory)
            return ob
    raise KeyError(f"no obligation {ob_id} in {directory}")


def validate_dir(directory, clauses: dict) -> list[dict]:
    """Check every stored obligation's quote against the regulation text."""
    rows = []
    for ob in load_obligations(directory):
        clause = clauses.get(ob.clause)
        if clause is None:
            rows.append({"id": ob.id, "ok": False, "reason": f"clause {ob.clause} not found in the regulation"})
            continue
        ok, reason = validate_quote(ob.quote, clause.text)
        rows.append({"id": ob.id, "ok": ok, "reason": reason})
    return rows
