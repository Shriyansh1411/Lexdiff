import shutil
import tempfile
import unittest
from pathlib import Path

from lexdiff.benchmark import run_benchmark
from lexdiff.canary import run_canary
from lexdiff.graph import build_graph, parse_views, sensitive_in
from lexdiff.guard import format_findings, run_guard
from lexdiff.screen import screen
from lexdiff.util import load_target_config
from tests.common import BASE, FIXED
import ast


class ScreenTests(unittest.TestCase):
    def test_flags_only_the_planted_injection(self):
        r = screen(BASE)
        self.assertEqual(len(r["flagged"]), 1)
        self.assertEqual(r["flagged"][0]["file"], "app/support_legacy.py")
        self.assertGreater(r["scanned"], 5)

    def test_fixed_repo_is_clean(self):
        self.assertEqual(screen(FIXED)["flagged"], [])


class GraphTests(unittest.TestCase):
    def test_view_alias_tracking(self):
        sql = "CREATE VIEW v AS SELECT a.ssn AS tin, substr(a.ssn, -4) AS tin_last4 FROM applications a;"
        v = parse_views(sql, {"ssn"})[0]
        self.assertEqual(v.sensitive_aliases, {"tin": "applications.ssn"})  # the masked expression is not propagated

    def test_sensitive_expression_analysis(self):
        names = {"ssn"}
        s = lambda src: sensitive_in(ast.parse(src, mode="eval").body, names)
        self.assertEqual(s("ssn"), ["ssn"])
        self.assertEqual(s("payload['ssn']"), ["ssn"])
        self.assertEqual(s("request.get_data(as_text=True)"), ["request body"])
        self.assertEqual(s("ssn[-4:]"), [])
        self.assertEqual(s("mask_ssn(ssn)"), [])
        self.assertEqual(s("ssn_last4"), [])

    def test_base_graph_finds_routes_mounts_and_renamed_traces(self):
        cfg = load_target_config(BASE)
        g = build_graph(BASE, cfg)
        missing = {(r.method, r.path) for r in g.routes_missing_mfa(cfg["public_routes"])}
        self.assertIn(("GET", "/support/impersonate/<int:customer_id>"), missing)  # blueprint mounted under /support
        self.assertEqual(len(missing), 4)
        self.assertTrue(any("applications.ssn -> v_uw_export.tin" in t for t in g.traces()))


class GuardTests(unittest.TestCase):
    def test_base_findings_cite_clauses_and_skip_decoys(self):
        cfg = load_target_config(BASE)
        f = run_guard(BASE, cfg)
        self.assertEqual(sorted({x.rule for x in f}), ["G-EXPORT", "G-LOG", "G-MFA", "G-NOTICE"])
        self.assertEqual(len(f), 8)
        self.assertTrue(all(x.clause.startswith("16 CFR 314.4") for x in f))
        text = BASE.joinpath("app/main.py").read_text().splitlines()
        decoy_lines = {i for i, ln in enumerate(text, 1) if "DECOY" in ln}
        self.assertFalse({x.line for x in f if x.file == "app/main.py"} & decoy_lines)

    def test_fixed_is_clean(self):
        self.assertEqual(run_guard(FIXED), [])

    def test_regression_fails_on_the_exact_line(self):
        tmp = Path(tempfile.mkdtemp()) / "repo"
        shutil.copytree(FIXED, tmp)
        mw = tmp / "app" / "logging_mw.py"
        lines = mw.read_text().splitlines()
        idx = next(i for i, ln in enumerate(lines) if "logger.debug" in ln)
        lines.insert(idx + 1, '        logger.debug("request body=%s", request.get_data(as_text=True))')
        mw.write_text("\n".join(lines) + "\n")
        f = run_guard(tmp)
        self.assertEqual([(x.file, x.line, x.rule) for x in f], [("app/logging_mw.py", idx + 2, "G-LOG")])
        self.assertIn(f"::error file=app/logging_mw.py,line={idx + 2}", format_findings(f, "github"))


class CanaryAndBenchmarkTests(unittest.TestCase):
    def test_canary_before_and_after(self):
        base, fixed = run_canary(BASE), run_canary(FIXED)
        self.assertEqual(base["errors"], [])
        self.assertGreater(base["by_store"]["logs"], 0)
        self.assertGreater(base["by_store"]["exports"], 0)
        self.assertEqual(fixed["by_store"]["logs"], 0)
        self.assertEqual(fixed["by_store"]["exports"], 0)
        self.assertGreater(fixed["by_store"]["db"], 0)  # plaintext at rest remains: kept honest on purpose

    def test_benchmark_reports_misses_honestly(self):
        r = run_benchmark(BASE)
        self.assertEqual(r["planted"], 11)
        self.assertEqual(r["lexdiff"]["found"], 9)
        self.assertEqual(r["lexdiff"]["decoys_flagged"], 0)
        self.assertEqual(sorted(r["lexdiff"]["missed"]), ["V10 (crypto)", "V11 (secret)"])


if __name__ == "__main__":
    unittest.main()
