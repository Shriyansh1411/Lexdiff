"""Shared helpers: hashing, text normalisation, file walking, subprocess env."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", "data", ".lexdiff", ".pytest_cache"}


def norm_ws(text: str) -> str:
    """Collapse whitespace and normalise typographic quotes (used for verbatim checks)."""
    text = (
        text.replace("\u2019", "'").replace("\u2018", "'")
        .replace("\u201c", '"').replace("\u201d", '"').replace("\u00a0", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def iter_files(root, suffixes=(".py",), skip_tests=False):
    """Yield files under *root* with the given suffixes in a stable order."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not (skip_tests and d == "tests")
        )
        for name in sorted(filenames):
            if name.endswith(suffixes):
                yield Path(dirpath) / name


def tree_hash(root, suffixes=(".py", ".json", ".sql")) -> str:
    """Stable content hash of a source tree (recorded in the evidence certificate)."""
    root = Path(root)
    h = hashlib.sha256()
    for p in iter_files(root, suffixes):
        h.update(p.relative_to(root).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def load_target_config(target) -> dict:
    p = Path(target) / "lexdiff_target.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found: every target repo needs a lexdiff_target.json")
    return json.loads(p.read_text(encoding="utf-8"))


def subprocess_env(extra: dict | None = None) -> dict:
    env = dict(os.environ)
    paths = [str(PKG_ROOT)] + [x for x in env.get("PYTHONPATH", "").split(os.pathsep) if x]
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra or {})
    return env


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
