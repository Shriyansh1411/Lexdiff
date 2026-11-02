"""Step 6 - Canary: plant synthetic data, run the app, and inspect what is actually stored."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from ..util import load_target_config, subprocess_env


class CanaryError(RuntimeError):
    pass


def run_canary(target, cfg: dict | None = None, timeout: int = 120) -> dict:
    target = Path(target).resolve()
    cfg = cfg or load_target_config(target)
    if "canary" not in cfg:
        raise CanaryError("lexdiff_target.json has no 'canary' section")
    with tempfile.TemporaryDirectory(prefix="lexdiff-canary-") as tmp:
        data, out = Path(tmp) / "data", Path(tmp) / "result.json"
        data.mkdir()
        proc = subprocess.run(
            [sys.executable, "-m", "lexdiff.canary.driver", "--target", str(target), "--data", str(data), "--out", str(out)],
            cwd=target, env=subprocess_env(), capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0 or not out.exists():
            raise CanaryError(f"canary driver failed:\n{proc.stderr[-1500:]}")
        return json.loads(out.read_text())
