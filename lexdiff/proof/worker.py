"""Runs a test directory and writes {test name: outcome} JSON.

Uses pytest when it is installed (parsing its JUnit XML) and falls back to the standard
library's unittest runner otherwise. Both produce the same result shape.
Runs in a subprocess with the target repo as the working directory.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_junit(path) -> dict[str, str]:
    results = {}
    for tc in ET.parse(path).getroot().iter("testcase"):
        if tc.find("failure") is not None:
            outcome = "failed"
        elif tc.find("error") is not None:
            outcome = "error"
        elif tc.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        results[tc.get("name")] = outcome
    return results


class _Collect(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.outcomes: dict[str, str] = {}

    def _name(self, test) -> str:
        return test.id().split(".")[-1]

    def addSuccess(self, test):
        self.outcomes[self._name(test)] = "passed"

    def addFailure(self, test, err):
        self.outcomes[self._name(test)] = "failed"

    def addError(self, test, err):
        self.outcomes[self._name(test)] = "error"

    def addSkip(self, test, reason):
        self.outcomes[self._name(test)] = "skipped"


def run_unittest(tests_dir: str) -> dict[str, str]:
    suite = unittest.TestLoader().discover(tests_dir, pattern="test_*.py", top_level_dir=tests_dir)
    result = _Collect()
    suite.run(result)
    return result.outcomes


def run_pytest(tests_dir: str, junit: str) -> dict[str, str]:
    import pytest

    pytest.main(["-q", "-p", "no:cacheprovider", "--junitxml", junit, tests_dir])
    return parse_junit(junit)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", default="auto", choices=["auto", "pytest", "unittest"])
    args = ap.parse_args(argv)
    tests_dir = os.path.abspath(args.tests)
    sys.path.insert(0, os.getcwd())
    use_pytest = args.engine == "pytest" or (args.engine == "auto" and importlib.util.find_spec("pytest") is not None)
    if use_pytest:
        engine, results = "pytest", run_pytest(tests_dir, args.out + ".xml")
    else:
        engine, results = "unittest", run_unittest(tests_dir)
    Path(args.out).write_text(json.dumps({"engine": engine, "results": results}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
