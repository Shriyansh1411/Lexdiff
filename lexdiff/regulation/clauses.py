"""Clause parsing for two input formats.

* demo text files:  ``§ 314.4(c)(5) | clause text``
* official eCFR XML (``lexdiff fetch-ecfr``): hierarchical paragraphs under a DIV8 section
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Clause:
    key: str
    text: str


def parse_text_file(path) -> dict[str, Clause]:
    out: dict[str, Clause] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, text = line.partition("|")
        if not sep:
            raise ValueError(f"bad clause line (expected 'KEY | TEXT'): {line[:70]}")
        key = key.strip().lstrip("§").strip()
        out[key] = Clause(key, text.strip())
    return out


def write_text_file(path, clauses: dict[str, Clause], header: str = "") -> None:
    lines = [f"# {h}" for h in header.splitlines()] if header else []
    lines += [f"§ {c.key} | {c.text}" for c in clauses.values()]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def word_count(clauses: dict[str, Clause]) -> int:
    return sum(len(c.text.split()) for c in clauses.values())


_ROMAN = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"}


def _level(marker: str, last_letter: str) -> int:
    if marker.isdigit():
        return 2
    if marker.isalpha() and marker.isupper():
        return 4
    if marker in _ROMAN and not (marker == "i" and last_letter == "h"):
        return 3
    return 1


def parse_ecfr_xml(xml_text: str, section: str = "314.4") -> dict[str, Clause]:
    """Parse eCFR full-text XML into {key: Clause} for one section."""
    root = ET.fromstring(xml_text)
    out: dict[str, Clause] = {}
    for div in root.iter("DIV8"):
        if (div.get("N") or "").replace("§", "").strip() != section:
            continue
        stack: dict[int, str] = {}
        last_key = None
        for p in div.iter("P"):
            text = "".join(p.itertext()).strip()
            m = re.match(r"^((?:\(\w+\)\s*)+)", text)
            if not m:
                if last_key:  # unmarked continuation paragraph
                    out[last_key].text += " " + text
                continue
            for marker in re.findall(r"\((\w+)\)", m.group(1)):
                level = _level(marker, stack.get(1, ""))
                stack = {lv: mk for lv, mk in stack.items() if lv < level}
                stack[level] = marker
            key = section + "".join(f"({stack[lv]})" for lv in sorted(stack))
            body = text[m.end():].strip()
            if key in out:
                out[key].text += " " + body
            else:
                out[key] = Clause(key, body)
            last_key = key
    return out
