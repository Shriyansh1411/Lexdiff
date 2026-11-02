"""Step 3 - Obligations: draft testable requirements from added/modified clauses.

Offline mode uses deterministic rules. With an LLM provider the model drafts from the verbatim
clause text only, and every draft still passes the same verbatim validator.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..llm import LLMClient, LLMError
from ..regulation.redline import Change
from .model import Obligation, validate_quote

ID_BY_KIND = {
    "no_plaintext_customer_data": "SG-3",
    "mfa_required": "SG-5",
    "manual_review": "SG-7",
    "breach_notice": "SG-9",
}
RULES = [
    ("mfa_required", r"multi-?factor authentication",
     "Every individual accessing an information system must pass a second authentication factor."),
    ("no_plaintext_customer_data", r"protect by encryption",
     "Customer information (government IDs, account numbers) must not appear in readable form "
     "in logs or exports, and must be protected at rest."),
    ("breach_notice", r"notify the federal trade commission",
     "A notification event affecting the threshold number of consumers must produce an FTC notice "
     "deadline within the stated number of days of discovery."),
    ("manual_review", r"change management",
     "Change-management procedures are organisational; automated checks cannot verify them."),
]


@dataclass
class DraftResult:
    obligations: list[Obligation] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _quote_for(text: str, pattern: str) -> str:
    for sentence in re.split(r"(?<=[.;])\s+", text):
        if re.search(pattern, sentence, re.I):
            return sentence.strip()
    return text.strip()


def _params(kind: str, text: str) -> dict:
    if kind != "breach_notice":
        return {}
    days = re.search(r"(\d+)\s+days", text)
    count = re.search(r"at least\s+([\d,]+)\s+consumers", text)
    return {
        "days": int(days.group(1)) if days else 30,
        "min_consumers": int(count.group(1).replace(",", "")) if count else 500,
    }


def draft_offline(changes: list[Change]) -> DraftResult:
    res = DraftResult()
    for ch in changes:
        for kind, pattern, requirement in RULES:
            if re.search(pattern, ch.new_text, re.I):
                quote = _quote_for(ch.new_text, pattern)
                ok, reason = validate_quote(quote, ch.new_text)
                if not ok:
                    res.rejected.append({"clause": ch.key, "quote": quote, "reason": reason})
                    continue
                res.obligations.append(Obligation(
                    id=ID_BY_KIND[kind], clause=ch.key, quote=quote, requirement=requirement,
                    kind=kind, params=_params(kind, ch.new_text), source="offline"))
                break
    return res


SYSTEM = (
    "You are a regulatory analyst. Use ONLY the clause text provided; never rely on memory of the law. "
    "For each clause that creates a testable software or data obligation, return one item. The quote MUST be "
    "copied verbatim from the clause. kind must be one of: " + ", ".join(ID_BY_KIND) + ". "
    'Reply as JSON: {"obligations":[{"clause":"","quote":"","requirement":"","kind":"","params":{}}]}'
)


def draft_with_model(changes: list[Change], client: LLMClient) -> DraftResult:
    clauses = {c.key: c.new_text for c in changes}
    data = client.complete_json(SYSTEM, json.dumps([{"clause": k, "text": t} for k, t in clauses.items()]))
    res = DraftResult()
    for item in data.get("obligations", []):
        key, quote, kind = item.get("clause", ""), item.get("quote", ""), item.get("kind", "")
        if key not in clauses or kind not in ID_BY_KIND:
            res.rejected.append({"clause": key, "quote": quote, "reason": "unknown clause or kind"})
            continue
        ok, reason = validate_quote(quote, clauses[key])
        if not ok:
            res.rejected.append({"clause": key, "quote": quote, "reason": reason})
            continue
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        params = {**_params(kind, clauses[key]), **params} if kind == "breach_notice" else {}
        res.obligations.append(Obligation(
            id=ID_BY_KIND[kind], clause=key, quote=quote.strip(),
            requirement=item.get("requirement", "") or dict((k, r) for k, _, r in RULES)[kind],
            kind=kind, params=params, source="model"))
    return res


def draft(changes: list[Change], client: LLMClient | None = None) -> DraftResult:
    if client is not None and client.online:
        try:
            return draft_with_model(changes, client)
        except LLMError as exc:
            res = draft_offline(changes)
            res.notes.append(f"model drafting failed ({exc}); used deterministic drafter")
            return res
    return draft_offline(changes)
