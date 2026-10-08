import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEM = ROOT / "config" / "mpstats" / "semantics"
TOOLS_DOC = ROOT / "docs" / "MPSTATS_TOOLS_2026-10-07.md"
SKILL = ROOT / "apps" / "hermes" / "mpstats_skill" / "SKILL.md"
DEPLOY = ROOT / "scripts" / "deploy" / "install-mpstats-skill.sh"

class TestMpstatsSemantics(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((SEM / "catalog.json").read_text(encoding="utf-8"))
        self.routing = json.loads((SEM / "routing.json").read_text(encoding="utf-8"))
        self.policy = json.loads((SEM / "tool_policy.json").read_text(encoding="utf-8"))
        self.response_shapes = json.loads((SEM / "response_shapes.json").read_text(encoding="utf-8"))
        self.metric_semantics = json.loads((SEM / "metric_semantics.json").read_text(encoding="utf-8"))

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

    def test_response_shape_audit_is_policy_linked_and_value_free(self):
        self.assertEqual(len(self.response_shapes["tools"]), 8)
        for name, observed in self.response_shapes["tools"].items():
            self.assertIn(name, self.policy["tools"])
            self.assertIn(observed["validation_status"], {"observed_success", "observed_tool_error"})
            for field in observed["fields"]:
                self.assertEqual(set(field), {"path", "type"})
        self.assertEqual(
            self.response_shapes["tools"]["lk_wb_dashboard_widget30days"]["validation_status"],
            "observed_tool_error",
        )
        self.assertEqual(
            self.response_shapes["tools"]["lk_ozon_overview"]["validation_status"],
            "observed_tool_error",
        )

    def test_second_audit_is_structural_and_classifies_tool_errors(self):
        batch = self.response_shapes["batch2"]
        self.assertEqual(batch["total_probes"], 13)
        self.assertEqual(batch["successful_probes"], 10)
        self.assertEqual(batch["tool_error_probes"], 3)
        self.assertEqual(len(batch["probes"]), 13)
        self.assertEqual(
            {
                k for k, p in batch["probes"].items()
                if p["validation_status"] == "observed_tool_error"
            },
            {"mine_products_list", "lk_wb_products_stocks",
             "lk_wb_dashboard_business_economics"},
        )
        for name, probe in batch["probes"].items():
            self.assertIn(probe["canonical_tool"], self.policy["tools"], name)
            for field in probe["fields"]:
                self.assertEqual(set(field), {"path", "type"})
                self.assertIn(field["type"], {
                    "null","boolean","integer","number","string","object","array"
                })
        wb = batch["probes"]["wb_sku_full"]["fields"]
        self.assertIn({"path": "$.price.wallet_price", "type": "integer"}, wb)
        ozon = batch["probes"]["ozon_sku_full"]["fields"]
        self.assertIn({"path": "$.price.ozon_card_price", "type": "integer"}, ozon)
        bidder = batch["probes"]["wbbidder_products"]["fields"]
        self.assertFalse(any(".data[]" in field["path"] for field in bidder))

    def test_metric_separates_price_and_purchase_definitions(self):
        self.assertEqual(
            self.metric_semantics["price_field_semantics"]["wb"]["unit"],
            "currency_unverified",
        )
        self.assertEqual(
            self.metric_semantics["price_field_semantics"]["ozon"]["unit"],
            "currency_unverified",
        )
        self.assertEqual(
            self.metric_semantics["purchase_metric_warning"]["canonical_self_purchase_source"],
            "msp_data.v_self_purchase",
        )
        self.assertIn(
            "unverified",
            self.metric_semantics["stock_semantics"]["freshness"]
        )

    def test_agent_skill_references_semantic_contract(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("name: mpstats", text)
        for ref in (
            "references/catalog.json",
            "references/routing.json",
            "references/tool_policy.json",
            "references/response_shapes.json",
            "references/metric_semantics.json",
            "references/official-knowledge.md",
            "references/live-tools.md",
            "references/semantic-layer.md",
        ):
            self.assertIn(ref, text)
        self.assertIn("wb_shelves_project", text)
        self.assertIn("v_self_purchase", text)
        self.assertIn("v_price_history", text)
        self.assertTrue(DEPLOY.exists())

    def test_metric_semantics_do_not_invent_units(self):
        metrics = self.metric_semantics["metrics"]
        self.assertEqual(metrics["ctr"]["unit"], "percent_scale_unverified")
        self.assertEqual(metrics["drr"]["unit"], "percent_scale_unverified")
        self.assertEqual(metrics["revenue"]["unit"], "unverified_currency")
        self.assertEqual(metrics["orders_sum"]["unit"], "unverified_currency")
        self.assertEqual(metrics["turnover_in_days"]["unit"], "days")
        rules = " ".join(self.metric_semantics["global_rules"]).lower()
        self.assertIn("never invent currency", rules)

    def test_official_mpstats_source_index_has_scope_and_token_rules(self):
        document = (ROOT / "docs" / "MPSTATS_OFFICIAL_KNOWLEDGE.md").read_text(encoding="utf-8")
        self.assertIn("https://mpstats.io/instruments/ai/mcp", document)
        self.assertIn("https://github.com/mpstats-io/claude-code-skills", document)
        self.assertIn("https://wiki.mpstats.io", document)
        self.assertIn("do not use that option", document)
        self.assertIn("purchase", document)
        evidence = self.metric_semantics["official_reference"]
        self.assertEqual(evidence["knowledge_index"], "docs/MPSTATS_OFFICIAL_KNOWLEDGE.md")
        self.assertEqual(evidence["provider_mcp"], "https://mpstats.io/instruments/ai/mcp")

    def test_internal_source_precedence_is_explicit(self):
        rules = self.routing["precedence_rules"]
        text = json.dumps(rules, ensure_ascii=False)
        self.assertIn("msp_data.v_product_catalog", text)
        self.assertIn("msp_data.v_self_purchase", text)
        self.assertIn("msp_data.v_price_history", text)

if __name__ == "__main__":
    unittest.main()
