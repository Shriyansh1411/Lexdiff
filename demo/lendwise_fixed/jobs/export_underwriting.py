"""Nightly underwriting export for the credit partner."""
import csv

from app import config, db

FIELDS = ["application_id", "applicant", "tin_last4", "acct_last4", "amount"]


def run() -> str:
    path = config.path("exports", "underwriting_export.csv")
    conn = db.connect()
    rows = conn.execute("SELECT * FROM v_uw_export").fetchall()
    conn.close()
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    return path
