"""Helpers used by the generated obligation tests.

The tests run in a subprocess whose working directory is the target repo (see proof/worker.py);
LEXDIFF_TARGET points at it. Each helper turns one obligation check into assertions.
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

_canary_cache: dict[str, dict] = {}


def target() -> Path:
    return Path(os.environ.get("LEXDIFF_TARGET", os.getcwd())).resolve()


def config() -> dict:
    return json.loads((target() / "lexdiff_target.json").read_text())


def _client():
    cfg = config()
    sys.path.insert(0, str(target()))
    os.environ[cfg["data_dir_env"]] = tempfile.mkdtemp(prefix="lexdiff-test-")
    module, _, attr = cfg["app_factory"].partition(":")
    return getattr(importlib.import_module(module), attr)().test_client()


def _concrete(path: str) -> str:
    return re.sub(r"<[^>]+>", "1", path)  # fill <int:customer_id> style placeholders


def assert_route_requires_mfa(tc, method: str, path: str) -> None:
    """Without a second factor the route must answer 'MFA required'; with one it must be reachable."""
    cfg = config()
    mfa = cfg["mfa"]
    client = _client()
    denied_header = mfa.get("denied_header", "X-MFA-Required")
    resp = client.open(_concrete(path), method=method)
    denied = resp.status_code in (401, 403) and resp.headers.get(denied_header) == "true"
    tc.assertTrue(denied, f"{method} {path} answered {resp.status_code} without a second factor; expected MFA denial")
    code = getattr(importlib.import_module(mfa["code_from"].partition(":")[0]), mfa["code_from"].partition(":")[2])()
    ok = client.open(_concrete(path), method=method, headers={mfa["header"]: code})
    tc.assertNotEqual(ok.headers.get(denied_header), "true", f"{method} {path} rejects a valid second factor")


def assert_canary_clean(tc, store: str) -> None:
    from .canary import run_canary

    key = str(target())
    if key not in _canary_cache:
        _canary_cache[key] = run_canary(target())
    res = _canary_cache[key]
    tc.assertEqual(res["errors"], [], f"canary scenario errors: {res['errors']}")
    tc.assertEqual(res["by_store"].get(store, 0), 0,
                   f"synthetic customer data found in '{store}': " + "; ".join(
                       f"{h['path']} x{h['count']}" for h in res["hits"] if h["store"] == store))


def assert_ftc_notice(tc, days: int, min_consumers: int) -> None:
    cfg = config().get("notice")
    tc.assertIsNotNone(cfg, "target declares no notification handler")
    sys.path.insert(0, str(target()))
    os.environ[config()["data_dir_env"]] = tempfile.mkdtemp(prefix="lexdiff-test-")
    try:
        handler = getattr(importlib.import_module(cfg["module"]), cfg["function"])
    except (ImportError, AttributeError) as exc:
        tc.fail(f"breach-notification handler {cfg['module']}.{cfg['function']} is missing ({exc})")
    discovered = dt.date(2026, 10, 1)
    hit = handler({"affected_consumers": min_consumers, "discovered_on": discovered.isoformat()})
    tc.assertTrue(hit.get("required"), f"an event affecting {min_consumers} consumers must require FTC notice")
    deadline = dt.date.fromisoformat(hit["notify_by"])
    tc.assertLessEqual((deadline - discovered).days, days, "notice deadline is later than the allowed window")
    miss = handler({"affected_consumers": min_consumers - 1, "discovered_on": discovered.isoformat()})
    tc.assertFalse(miss.get("required"), f"an event affecting {min_consumers - 1} consumers must not trigger notice")
