import unittest

from lexdiff.regulation import Clause, actionable, parse_ecfr_xml, parse_text_file, redline
from tests.common import REG_NEW, REG_OLD


def C(**kw):
    return {k.replace("_", "."): Clause(k.replace("_", "."), v) for k, v in kw.items()}


class RedlineTests(unittest.TestCase):
    def test_demo_versions(self):
        ch = redline(parse_text_file(REG_OLD), parse_text_file(REG_NEW))
        kinds = {c.key: c.kind for c in ch}
        self.assertEqual(kinds["314.4(c)"], "modified")
        self.assertEqual(kinds["314.4(c)(5)"], "added")
        self.assertEqual(kinds["314.4(j)(1)"], "added")
        self.assertEqual(len(actionable(ch)), 5)

    def test_pure_renumbering_is_set_aside(self):
        text = "Maintain an inventory of all systems that store customer information and review it each year."
        old = {"314.4(e)": Clause("314.4(e)", text)}
        new = {"314.4(f)": Clause("314.4(f)", text)}
        ch = redline(old, new)
        self.assertEqual([c.kind for c in ch], ["renumbered"])
        self.assertEqual(ch[0].old_key, "314.4(e)")
        self.assertEqual(actionable(ch), [])

    def test_removed_and_word_diff(self):
        old = {"1": Clause("1", "You must keep records for five years."), "2": Clause("2", "Gone entirely now.")}
        new = {"1": Clause("1", "You must keep records for seven years.")}
        ch = {c.key: c for c in redline(old, new)}
        self.assertEqual(ch["1"].kind, "modified")
        self.assertIn({"op": "insert", "text": "seven"}, ch["1"].word_diff)
        self.assertEqual(ch["2"].kind, "removed")

    def test_ecfr_xml_parser(self):
        xml = """<ECFR><DIV8 N="§ 314.4" TYPE="SECTION"><HEAD>Elements</HEAD>
        <P>(c) Design and implement safeguards, including by:</P>
        <P>(1) Implement access controls.</P>
        <P>(5) Implement multi-factor authentication for any individual accessing any information system;</P>
        <P>(j)(1) Notify the Commission within 30 days.</P></DIV8></ECFR>"""
        got = parse_ecfr_xml(xml)
        self.assertEqual(set(got), {"314.4(c)", "314.4(c)(1)", "314.4(c)(5)", "314.4(j)(1)"})
        self.assertIn("multi-factor", got["314.4(c)(5)"].text)


if __name__ == "__main__":
    unittest.main()
