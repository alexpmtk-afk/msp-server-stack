"""Static contract for the opt-in Hermes self-purchases orientation package."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestSelfPurchasesOrientation(unittest.TestCase):
    def test_compass_and_skill_entry_points(self):
        compass = (ROOT / "docs/self-purchases/PROJECT_COMPASS.md").read_text(encoding="utf-8")
        skill = (ROOT / "apps/hermes/msp_self_purchases_skill/SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("первоначальн", compass.lower())
        self.assertIn("MEETING_TRANSCRIPT_2026-10-21.md", compass)
        self.assertIn("PROJECT_COMPASS.md", skill)
        self.assertIn("INITIAL_VISION_V1_2026-10-21.md", skill)
        self.assertIn("DECISIONS_AND_DEVIATIONS.md", skill)
        self.assertIn("MSP_SELF_01_SOURCE_MATRIX.md", skill)
        self.assertIn("PRICE_JOURNAL_MISSING_DATE_POLICY.md", skill)
        self.assertIn("PRICE_JOURNAL_MISSING_DATE_POLICY.md", agents)
        policy = (ROOT / "docs/PRICE_JOURNAL_MISSING_DATE_POLICY.md").read_text(encoding="utf-8")
        self.assertIn("price_journal_current", policy)
        self.assertIn("price_journal_archive", policy)
        self.assertTrue((ROOT / "docs/self-purchases/DECISION_PRICE_NO_DATE_20261022.md").is_file())
        self.assertIn("MSP_SELF_01_SOURCE_MATRIX.md", compass)
        self.assertIn("PROJECT_COMPASS.md", agents)
        self.assertIn("SOURCE_NOT_AVAILABLE", skill)
        self.assertIn("FACT", skill)

    def test_isolated_install_requires_both_pins_and_never_modifies_canonical_checkout(self):
        script = (ROOT / "scripts/deploy/install-msp-self-purchases-skill.sh").read_text(encoding="utf-8")
        for value in ("MSP_COMPASS_PUBLIC_PIN", "MSP_COMPASS_PRIVATE_PIN",
                      "GITHUB_WORKSPACE", "sha256sum", "private_commit",
                      "public_commit", "DECISIONS_AND_DEVIATIONS.md"):
            self.assertIn(value, script)
        self.assertIn("STOP: existing skill", script)
        self.assertIn("STOP: source checkout is dirty", script)
        self.assertNotIn("git -C \"$public_root\" merge", script)
        self.assertNotIn("systemctl restart", script)


if __name__ == "__main__":
    unittest.main()
