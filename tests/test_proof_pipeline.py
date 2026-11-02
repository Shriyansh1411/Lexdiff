import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from lexdiff.evidence import grade
from lexdiff.pipeline import run_pipeline
from lexdiff.proof import check_integrity, classify, open_source
from lexdiff.proof.worker import parse_junit
from tests.common import BASE, FIXED, REG_NEW, REG_OLD, ROOT


class ClassifyTests(unittest.TestCase):
    def test_verdicts(self):
        rows = classify({"a": "failed", "b": "passed", "c": "passed", "d": "failed"},
                        {"a": "passed", "b": "passed", "c": "failed", "d": "failed"})
        self.assertEqual({k: v["verdict"] for k, v in rows.items()},
                         {"a": "discriminating", "b": "already_passing", "c": "regression", "d": "failing_on_head"})

    def test_grading(self):
        ob = {"kind": "mfa_required"}
        row = lambda v: {"name": "t", "verdict": v}
        self.assertEqual(grade(ob, [row("discriminating"), row("already_passing")])[0], "Verified")
        self.assertEqual(grade(ob, [row("discriminating"), row("failing_on_head")])[0], "Partially verified")
        self.assertEqual(grade(ob, [row("already_passing")])[0], "Unverified")
        self.assertEqual(grade(ob, [row("discriminating"), row("regression")])[0], "Unverified")
        self.assertEqual(grade({"kind": "manual_review"}, [])[0], "Human review required")

    def test_junit_parser_for_the_pytest_path(self):
        xml = """<testsuites><testsuite><testcase name="test_a"/>
        <testcase name="test_b"><failure message="x"/></testcase>
        <testcase name="test_c"><error message="x"/></testcase>
        <testcase name="test_d"><skipped/></testcase></testsuite></testsuites>"""
        p = Path(tempfile.mkdtemp()) / "r.xml"
        p.write_text(xml)
        self.assertEqual(parse_junit(p), {"test_a": "passed", "test_b": "failed", "test_c": "error", "test_d": "skipped"})


class IntegrityTests(unittest.TestCase):
    def test_hand_edit_is_caught_unless_approved(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "test_x.py").write_text("print(1)\n")
        from lexdiff.obligations.testgen import write_lock
        write_lock(tmp, tmp / "lock.json")
        self.assertTrue(check_integrity(tmp, tmp / "lock.json")["clean"])
        (tmp / "test_x.py").write_text("print(2)\n")
        res = check_integrity(tmp, tmp / "lock.json")
        self.assertFalse(res["clean"])
        self.assertIn("test_x.py", res["violations"][0])


class GitSourceTests(unittest.TestCase):
    def test_repo_at_ref_is_exported(self):
        repo = Path(tempfile.mkdtemp())
        run = lambda *a: subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t.test", *a],
                                        check=True, capture_output=True)
        run("init", "-b", "main")
        (repo / "a.txt").write_text("one")
        run("add", "."); run("commit", "-m", "one")
        run("branch", "feature")
        (repo / "a.txt").write_text("two")
        run("commit", "-am", "two")
        with open_source(f"{repo}@feature") as src:
            self.assertEqual((src.path / "a.txt").read_text(), "one")
        with open_source(f"{repo}@main") as src:
            self.assertEqual((src.path / "a.txt").read_text(), "two")


class EndToEndTests(unittest.TestCase):
    def test_full_pipeline_grades_honestly(self):
        root = Path(tempfile.mkdtemp())
        (root / "compliance").mkdir()
        res = run_pipeline(root, BASE, FIXED, REG_OLD, REG_NEW, approver="Compliance Lead", log=lambda *_: None)
        cert = res["certificate"]
        grades = {o["id"]: o["grade"] for o in cert["obligations"]}
        self.assertEqual(grades, {"SG-3": "Partially verified", "SG-5": "Verified",
                                  "SG-7": "Human review required", "SG-9": "Verified"})
        self.assertTrue(cert["integrity"]["clean"])
        self.assertTrue(cert["regression"]["green"])
        self.assertEqual(cert["guard_head_findings"], 0)
        self.assertGreater(cert["canary"]["base_hits"], cert["canary"]["head_hits"])
        self.assertNotIn("compliant", json.dumps(cert["summary"]).lower().replace("non-compliant", ""))
        for name in ("certificate.json", "certificate.html", "verification.json", "redline.json"):
            self.assertTrue((root / ".lexdiff" / name).exists(), name)

    def test_pipeline_stops_until_a_human_approves(self):
        root = Path(tempfile.mkdtemp())
        res = run_pipeline(root, BASE, FIXED, REG_OLD, REG_NEW, approver="", log=lambda *_: None)
        self.assertEqual(res["stopped"], "awaiting_approval")
        self.assertFalse((root / ".lexdiff" / "certificate.json").exists())


if __name__ == "__main__":
    unittest.main()
