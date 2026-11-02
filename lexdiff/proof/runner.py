"""Step 7 - Prove: every obligation test must FAIL on the base and PASS on the fix.

Sources may be plain directories or ``path/to/repo@ref`` (a git ref, exported with ``git archive``).
Existing tests are locked: obligation tests are hash-checked and the target's own suite must stay green.
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..canary import run_canary
from ..guard import run_guard
from ..util import sha256_file, subprocess_env, tree_hash


@dataclass
class Source:
    path: Path
    label: str


@contextlib.contextmanager
def open_source(spec: str):
    """Resolve a directory or ``repo@ref`` into a directory on disk."""
    p = Path(spec)
    if p.is_dir():
        yield Source(p.resolve(), str(spec))
        return
    if "@" not in spec:
        raise FileNotFoundError(f"{spec} is not a directory, and has no @ref to treat as a git repo")
    repo, ref = spec.rsplit("@", 1)
    tar = subprocess.run(["git", "-C", repo, "archive", "--format=tar", ref], capture_output=True)
    if tar.returncode != 0:
        raise FileNotFoundError(f"git archive failed for {spec}: {tar.stderr.decode()[:200]}")
    sha = subprocess.run(["git", "-C", repo, "rev-parse", "--short", ref], capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="lexdiff-src-") as tmp:
        with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as tf:
            tf.extractall(tmp, filter="data")
        yield Source(Path(tmp).resolve(), f"{spec} ({sha})")


def run_suite(target, tests_dir, engine: str = "auto", timeout: int = 300) -> dict:
    """Run a test directory with the target repo as working directory. Returns {engine, results}."""
    target, tests_dir = Path(target).resolve(), Path(tests_dir).resolve()
    with tempfile.TemporaryDirectory(prefix="lexdiff-run-") as tmp:
        out = Path(tmp) / "results.json"
        proc = subprocess.run(
            [sys.executable, "-m", "lexdiff.proof.worker", "--tests", str(tests_dir), "--out", str(out), "--engine", engine],
            cwd=target, env=subprocess_env({"LEXDIFF_TARGET": str(target)}), capture_output=True, text=True, timeout=timeout)
        if not out.exists():
            raise RuntimeError(f"test worker failed:\n{proc.stderr[-1500:]}")
        return json.loads(out.read_text())


def classify(base: dict[str, str], head: dict[str, str]) -> dict[str, dict]:
    """Per-test verdict from the base-vs-head outcomes."""
    rows = {}
    for name in sorted(set(base) | set(head)):
        b, h = base.get(name, "missing"), head.get(name, "missing")
        b_pass, h_pass = b == "passed", h == "passed"
        if not b_pass and h_pass:
            verdict = "discriminating"      # fails before, passes after: it proves the fix
        elif b_pass and h_pass:
            verdict = "already_passing"     # passes either way: a regression guard, but not proof of a fix
        elif b_pass and not h_pass:
            verdict = "regression"
        else:
            verdict = "failing_on_head"     # still failing after the change
        rows[name] = {"base": b, "head": h, "verdict": verdict}
    return rows


def check_integrity(tests_dir, lock_path, changes_path=None) -> dict:
    """Locked tests must be unchanged unless a named human approved the rewrite."""
    tests_dir, lock_path = Path(tests_dir), Path(lock_path)
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    changes = []
    if changes_path and Path(changes_path).exists():
        changes = yaml.safe_load(Path(changes_path).read_text()) or []
    approved = {c["new_sha256"] for c in changes if c.get("approved_by")}
    violations = []
    for name, sha in lock.items():
        f = tests_dir / name
        if not f.exists():
            violations.append(f"{name}: locked test is missing")
        elif sha256_file(f) != sha and sha256_file(f) not in approved:
            violations.append(f"{name}: changed since it was locked, with no approved rewrite")
    return {"clean": not violations, "violations": violations, "approved_rewrites": len(changes), "locked_files": len(lock)}


def verify(base_path, head_path, tests_dir, lock_path, changes_path=None, own_tests="tests", engine="auto") -> dict:
    base_path, head_path = Path(base_path), Path(head_path)
    base_run, head_run = run_suite(base_path, tests_dir, engine), run_suite(head_path, tests_dir, engine)
    rows = classify(base_run["results"], head_run["results"])

    regression = {"ran": False, "green": True, "regressed": []}
    if (base_path / own_tests).is_dir() and (head_path / own_tests).is_dir():
        b, h = run_suite(base_path, base_path / own_tests, engine), run_suite(head_path, head_path / own_tests, engine)
        regressed = sorted(n for n, o in b["results"].items() if o == "passed" and h["results"].get(n) != "passed")
        regression = {"ran": True, "green": not regressed, "regressed": regressed,
                      "tests": len(b["results"]), "passing_on_head": sum(1 for o in h["results"].values() if o == "passed")}

    return {
        "engine": head_run["engine"],
        "tests": rows,
        "canary": {"base": run_canary(base_path), "head": run_canary(head_path)},
        "integrity": check_integrity(tests_dir, lock_path, changes_path),
        "regression": regression,
        "guard_head": [f.to_dict() for f in run_guard(head_path)],
        "artifacts": {"base_tree_sha256": tree_hash(base_path), "head_tree_sha256": tree_hash(head_path)},
    }
