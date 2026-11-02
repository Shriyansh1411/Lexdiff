"""Clause-level redline: what changed between two regulation versions.

Pure renumbering (same text, new key) is detected and set aside so it never
becomes a false obligation.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass

from ..util import norm_ws
from .clauses import Clause


@dataclass
class Change:
    kind: str  # added | removed | modified | renumbered
    key: str
    old_key: str | None
    old_text: str
    new_text: str
    similarity: float
    word_diff: list

    def to_dict(self) -> dict:
        return asdict(self)


def _natural(key: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", key)]


def _word_diff(a: str, b: str) -> list[dict]:
    aw, bw = a.split(), b.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, aw, bw, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"op": "equal", "text": " ".join(aw[i1:i2])})
            continue
        if i2 > i1:
            out.append({"op": "delete", "text": " ".join(aw[i1:i2])})
        if j2 > j1:
            out.append({"op": "insert", "text": " ".join(bw[j1:j2])})
    return out


def redline(old: dict[str, Clause], new: dict[str, Clause], renumber_threshold: float = 0.92) -> list[Change]:
    changes: list[Change] = []
    only_new = [k for k in new if k not in old]
    only_old = [k for k in old if k not in new]
    for key, clause in new.items():
        if key in old and norm_ws(old[key].text) != norm_ws(clause.text):
            ratio = difflib.SequenceMatcher(None, norm_ws(old[key].text), norm_ws(clause.text), autojunk=False).ratio()
            changes.append(Change("modified", key, key, old[key].text, clause.text, ratio,
                                  _word_diff(old[key].text, clause.text)))
    claimed: set[str] = set()
    for key in only_new:
        best, best_key = 0.0, None
        for ok in only_old:
            if ok in claimed:
                continue
            r = difflib.SequenceMatcher(None, norm_ws(old[ok].text), norm_ws(new[key].text), autojunk=False).ratio()
            if r > best:
                best, best_key = r, ok
        if best_key is not None and best >= renumber_threshold:
            claimed.add(best_key)
            changes.append(Change("renumbered", key, best_key, old[best_key].text, new[key].text, best, []))
        else:
            changes.append(Change("added", key, None, "", new[key].text, 0.0,
                                  [{"op": "insert", "text": new[key].text}]))
    for ok in only_old:
        if ok not in claimed:
            changes.append(Change("removed", ok, ok, old[ok].text, "", 0.0,
                                  [{"op": "delete", "text": old[ok].text}]))
    changes.sort(key=lambda c: _natural(c.key))
    return changes


def actionable(changes: list[Change]) -> list[Change]:
    """Changes that can create new obligations (renumbering and removals cannot)."""
    return [c for c in changes if c.kind in ("added", "modified")]


def format_changes(changes: list[Change]) -> str:
    if not changes:
        return "No clause-level changes."
    mark = {"added": "+", "removed": "-", "modified": "~", "renumbered": "="}
    lines = []
    for c in changes:
        extra = f" (was {c.old_key}, similarity {c.similarity:.2f})" if c.kind == "renumbered" else ""
        lines.append(f"{mark[c.kind]} {c.kind:<10} §{c.key}{extra}")
        text = c.new_text or c.old_text
        lines.append(f"    {text[:150]}{'…' if len(text) > 150 else ''}")
    return "\n".join(lines)
