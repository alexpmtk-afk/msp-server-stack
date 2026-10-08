import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEM = ROOT / "config" / "mpstats" / "semantics"
TOOLS_DOC = ROOT / "docs" / "MPSTATS_TOOLS_2026-10-07.md"

class TestMpstatsSemantics(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((SEM / "catalog.json").read_text(encoding="utf-8"))
        self.routing = json.loads((SEM / "routing.json").read_text(encoding="utf-8"))
        self.policy = json.loads((SEM / "tool_policy.json").read_text(encoding="utf-8"))

    def test_live_inventory_is_fully_covered(self):
        raw = TOOLS_DOC.read_text(encoding="utf-8")
        names = set(re.findall(r"^### `([^`]+)`$", raw, re.MULTILINE))
        policy_names = set(self.policy["tools"])
        self.assertEqual(len(names), 108)
        self.assertEqual(self.policy["tool_count"], 108)
        self.assertEqual(names, policy_names)

    def test_all_tools_have_known_family_and_access_policy(self):
        families = set(self.catalog["families"])
        for name, p in self.policy["tools"].items():
            self.assertIn(p["family"], families, name)
            self.assertTrue(p["access_mode"], name)
            self.assertIn("automatic_use_allowed", p, name)
            self.assertIn("explicit_user_confirmation_required", p, name)

    def test_write_and_escape_hatches_are_guarded(self):
        p = self.policy["tools"]
        self.assertEqual(p["wb_shelves_project"]["access_mode"], "mpstats_account_write")
        self.assertFalse(p["wb_shelves_project"]["automatic_use_allowed"])
        self.assertTrue(p["wb_shelves_project"]["explicit_user_confirmation_required"])
        self.assertEqual(p["pe_run"]["access_mode"], "creative_escape_hatch")
        self.assertFalse(p["pe_run"]["automatic_use_allowed"])
        self.assertTrue(p["pe_run"]["explicit_user_confirmation_required"])
        self.assertEqual(p["lk_wb_request"]["access_mode"], "read_only_escape_hatch")
        self.assertFalse(p["lk_wb_request"]["automatic_use_allowed"])

    def test_stateful_cabinet_selector_is_not_plain_read(self):
        p = self.policy["tools"]["lk_wb_cabinets"]
        self.assertEqual(p["access_mode"], "mixed_scope_state")
        self.assertTrue(any("select/reset" in n for n in p["notes"]))

    def test_internal_source_precedence_is_explicit(self):
        rules = self.routing["precedence_rules"]
        text = json.dumps(rules, ensure_ascii=False)
        self.assertIn("msp_data.v_product_catalog", text)
        self.assertIn("msp_data.v_self_purchase", text)
        self.assertIn("msp_data.v_price_history", text)

if __name__ == "__main__":
    unittest.main()
