"""Optional: fetch dated versions of 16 CFR 314 from the public eCFR versioner API.

Needs network access. Not used by the offline demo or the test-suite.
"""
from __future__ import annotations

from .clauses import Clause, parse_ecfr_xml

URL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-16.xml?part=314"


def fetch_clauses(date: str, section: str = "314.4", timeout: int = 60) -> dict[str, Clause]:
    import requests  # imported lazily so the offline paths need no network library

    resp = requests.get(URL.format(date=date), headers={"Accept": "application/xml"}, timeout=timeout)
    resp.raise_for_status()
    clauses = parse_ecfr_xml(resp.text, section=section)
    if not clauses:
        raise ValueError(f"no clauses parsed for section {section} on {date}; check the date and section")
    return clauses
