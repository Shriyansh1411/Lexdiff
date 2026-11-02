import json
import tempfile
import unittest
from pathlib import Path

from lexdiff.llm import LLMClient, LLMError
from lexdiff.obligations import approve, load_obligations, save_obligation, validate_quote
from lexdiff.obligations.draft import draft, draft_offline
from lexdiff.obligations.model import validate_dir
from lexdiff.obligations.planner import plan_checks
from lexdiff.obligations.testgen import LockedTestError, generate
from lexdiff.graph import build_graph
from lexdiff.regulation import actionable, parse_text_file, redline
from lexdiff.util import load_target_config
from tests.common import BASE, REG_NEW, REG_OLD, ROOT


def changes():
    return actionable(redline(parse_text_file(REG_OLD), parse_text_file(REG_NEW)))


class ValidatorTests(unittest.TestCase):
    CLAUSE = "Implement multi-factor authentication for any individual accessing any information system;"

    def test_verbatim_quote_passes(self):
        self.assertTrue(validate_quote("multi-factor authentication for any individual", self.CLAUSE)[0])

    def test_whitespace_and_curly_quotes_are_normalised(self):
        self.assertTrue(validate_quote("multi-factor   authentication\nfor any individual", self.CLAUSE)[0])

    def test_paraphrase_is_rejected(self):
        ok, reason = validate_quote("Staff must use two-step login on all systems", self.CLAUSE)
        self.assertFalse(ok)
        self.assertIn("verbatim", reason)

    def test_demo_paraphrase_draft_is_rejected(self):
        rows = validate_dir(ROOT / "compliance" / "drafts", parse_text_file(REG_NEW))
        self.assertEqual([r["ok"] for r in rows], [False])


class DraftTests(unittest.TestCase):
    def test_offline_drafts_four_obligations_with_verbatim_quotes(self):
        res = draft_offline(changes())
        self.assertEqual(sorted(o.id for o in res.obligations), ["SG-3", "SG-5", "SG-7", "SG-9"])
        self.assertEqual(res.rejected, [])
        notice = next(o for o in res.obligations if o.id == "SG-9")
        self.assertEqual(notice.params, {"days": 30, "min_consumers": 500})

    def test_model_drafts_are_validated_and_paraphrases_rejected(self):
        good = "Implement multi-factor authentication for any individual accessing any information system"
        reply = {"obligations": [
            {"clause": "314.4(c)(5)", "quote": good, "requirement": "MFA", "kind": "mfa_required"},
            {"clause": "314.4(c)(3)", "quote": "Encrypt everything always", "requirement": "x", "kind": "no_plaintext_customer_data"},
        ]}
        client = LLMClient(provider="openai", api_key="k", transport=lambda payload: json.dumps(reply))
        res = draft(changes(), client)
        self.assertEqual([o.id for o in res.obligations], ["SG-5"])
        self.assertEqual(len(res.rejected), 1)

    def test_request_is_temperature_zero_json(self):
        seen = {}
        client = LLMClient(provider="openai", api_key="k", transport=lambda p: seen.update(p) or "{}")
        client.complete_json("s", "u")
        self.assertEqual(seen["temperature"], 0)
        self.assertEqual(seen["response_format"], {"type": "json_object"})

    def test_bad_model_output_falls_back_to_offline_drafter(self):
        client = LLMClient(provider="openai", api_key="k", transport=lambda p: "not json at all")
        res = draft(changes(), client)
        self.assertEqual(len(res.obligations), 4)
        self.assertTrue(res.notes)

    def test_offline_client_never_calls_a_model(self):
        with self.assertRaises(LLMError):
            LLMClient(provider="offline").complete_json("s", "u")


class PlanAndLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = load_target_config(BASE)
        graph = build_graph(BASE, self.cfg)
        self.obs = draft_offline(changes()).obligations
        for ob in self.obs:
            ob.status, ob.approved_by = "approved", "Tester"
            ob.checks = plan_checks(ob, graph, self.cfg)

    def test_plan_expands_from_the_graph(self):
        by_id = {o.id: o for o in self.obs}
        self.assertEqual(len(by_id["SG-5"].checks), 5)  # every non-public route
        self.assertEqual(len(by_id["SG-3"].checks), 3)  # logs, exports, db
        self.assertEqual(by_id["SG-7"].checks, [])      # manual review

    def test_locked_tests_block_a_silent_rewrite(self):
        tests, lock, changes_file = self.tmp / "t", self.tmp / "lock.json", self.tmp / "changes.yaml"
        generate(self.obs, tests, lock, changes_file)
        sg9 = next(o for o in self.obs if o.id == "SG-9")
        sg9.checks[0]["days"] = 45
        with self.assertRaises(LockedTestError):
            generate(self.obs, tests, lock, changes_file)
        generate(self.obs, tests, lock, changes_file, allow_rewrite_by="Compliance Lead", reason="policy change")
        import yaml
        rec = yaml.safe_load(changes_file.read_text())
        self.assertEqual(rec[0]["approved_by"], "Compliance Lead")

    def test_approval_needs_a_name(self):
        d = self.tmp / "ob"
        save_obligation(self.obs[0], d)
        with self.assertRaises(ValueError):
            approve(d, self.obs[0].id, "  ")
        self.assertEqual(approve(d, self.obs[0].id, "Ada").approved_by, "Ada")
        self.assertEqual(load_obligations(d)[0].status, "approved")


if __name__ == "__main__":
    unittest.main()
