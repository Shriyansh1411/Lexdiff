"""Canary driver. Runs INSIDE a sandboxed subprocess against one target repo.

Plants a synthetic SSN and bank account, drives the app through the scenario in
``lexdiff_target.json`` (HTTP calls + background jobs), then sweeps every data store
(logs, exports, database) for the planted values. Synthetic data only.
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path


def _import(spec: str):
    module, _, attr = spec.partition(":")
    return getattr(importlib.import_module(module), attr)


def _subst(obj, mapping: dict):
    if isinstance(obj, str):
        for k, v in mapping.items():
            obj = obj.replace("{{" + k + "}}", v)
        return obj
    if isinstance(obj, dict):
        return {k: _subst(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_subst(v, mapping) for v in obj]
    return obj


def _count(haystack: bytes, values: list[str]) -> int:
    return sum(haystack.count(v.encode()) for v in values)


def sweep(data_dir: Path, stores: dict, needles: dict) -> list[dict]:
    hits = []
    for store, rel in stores.items():
        base = data_dir / rel
        if store == "db":
            if not base.exists():
                continue
            conn = sqlite3.connect(str(base))
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
                for row in conn.execute(f"SELECT * FROM {table}"):
                    for col, val in zip(cols, row):
                        blob = str(val).encode()
                        for label, values in needles.items():
                            n = _count(blob, values)
                            if n:
                                hits.append({"store": store, "path": f"{rel}#{table}.{col}", "needle": label, "count": n})
            conn.close()
            continue
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file()) if base.exists() else []
        for f in files:
            blob = f.read_bytes()
            for label, values in needles.items():
                n = _count(blob, values)
                if n:
                    hits.append({"store": store, "path": f.relative_to(data_dir).as_posix(), "needle": label, "count": n})
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    target, data = Path(args.target).resolve(), Path(args.data).resolve()
    cfg = json.loads((target / "lexdiff_target.json").read_text())
    can = cfg["canary"]
    os.environ[cfg["data_dir_env"]] = str(data)
    os.chdir(target)
    sys.path.insert(0, str(target))

    ssn, acct = can["ssn"], can["account_number"]
    mapping = {"ssn": ssn, "account_number": acct}
    needles = {"ssn": [ssn, ssn.replace("-", "")], "account_number": [acct]}

    app = _import(cfg["app_factory"])()
    client = app.test_client()
    mfa = cfg.get("mfa")
    code_fn = _import(mfa["code_from"]) if mfa else None

    steps, errors = [], []
    for step in can.get("scenario", []):
        headers = dict(step.get("headers", {}))
        if step.get("mfa") and mfa:
            headers[mfa["header"]] = code_fn()
        kwargs = {"headers": headers}
        if "json" in step:
            kwargs["json"] = _subst(step["json"], mapping)
        try:
            resp = client.open(step["path"], method=step["method"], **kwargs)
            steps.append({"step": f'{step["method"]} {step["path"]}', "status": resp.status_code})
        except Exception as exc:  # noqa: BLE001 - the audit must keep going and report
            errors.append(f'{step["method"]} {step["path"]}: {exc!r}')
    for job in can.get("jobs", []):
        try:
            _import(job)()
            steps.append({"step": f"job {job}", "status": "ok"})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"job {job}: {exc!r}")
    logging.shutdown()

    hits = sweep(data, can["stores"], needles)
    by_store = {s: 0 for s in can["stores"]}
    for h in hits:
        by_store[h["store"]] += h["count"]
    Path(args.out).write_text(json.dumps({
        "hits": hits, "by_store": by_store, "total": sum(by_store.values()), "steps": steps, "errors": errors,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
