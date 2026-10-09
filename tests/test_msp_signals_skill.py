"""Static, no-network Hermes MSP signal skill contract tests."""
import re
import unittest
from pathlib import Path
from datetime import date
from apps.msp_signal_notify.notify import identify, price_advice

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'apps/hermes/msp_signals_skill/SKILL.md'
RULES = ROOT / 'docs/signals/REVIEWED_RULES_2026-10-05.md'
SIM = ROOT / 'docs/signals/SIMULATED_NOTIFICATIONS.md'
INSTALLER = ROOT / 'scripts/deploy/install-msp-signals-skill.sh'

class SignalSkillContractTests(unittest.TestCase):
    def test_skill_frontmatter_and_manual_dispatch_terms(self):
        skill = SKILL.read_text(encoding='utf-8')
        self.assertTrue(skill.startswith('---\nname: msp-signals\n'))
        self.assertIn('обработай сигналы', skill)
        self.assertIn('Поднять цену', skill)
        self.assertIn('references/reviewed-rules.md', skill)
        self.assertIn('НЕ поднимать', skill)

    def test_missing_production_date_contract_matches_notifier(self):
        skill = SKILL.read_text(encoding='utf-8')
        rules = RULES.read_text(encoding='utf-8')
        sim = SIM.read_text(encoding='utf-8')
        for title in (skill, rules, sim):
            self.assertIn('production', title.lower())
        self.assertIn('не заказан на производство', skill)
        self.assertIn('recommend raising the price', rules)
        self.assertIn('no production/inbound date', sim)
        sample = 'Поднять цену\nТовар (123456789) _6 '
        self.assertEqual(identify(sample)[0], 'SIG-002')
        a = price_advice(sample, date(2026,10,9))
        self.assertEqual(len(a),1)
        self.assertIn('РЕКОМЕНДУЕТСЯ поднять цену', a[0])
        self.assertIn('не заказан на производство', a[0])

    def test_valid_and_invalid_dates_keep_original_semantics(self):
        text = 'товар (123456789) _3 12.10.2026\nтовар (987654321) _3 11.10.2026\nтовар (112233445) _3 32.10.2026'
        out=price_advice(text,date(2026,10,8))
        self.assertIn('РЕКОМЕНДУЕТСЯ поднять цену', out[0])
        self.assertIn('НЕ поднимать цену', out[1])
        self.assertIn('недостаточно данных', out[2])

    def test_all_six_reviewed_types_covered_and_no_real_action(self):
        skill=SKILL.read_text(encoding='utf-8')
        for sig in ('SIG-002','SIG-016','SIG-015','SIG-021','SIG-022','SIG-032'):
            self.assertIn(sig,skill)
            self.assertIn(sig,RULES.read_text(encoding='utf-8'))
        self.assertIn('Фактические действия на маркетплейсах отключены',skill)
        self.assertIn('Не отправляй повторные уведомления',skill)

    def test_installer_does_not_restart_services_or_read_secrets(self):
        txt=INSTALLER.read_text(encoding='utf-8')
        self.assertIn('--check',txt)
        self.assertIn('/home/hermes/.hermes/skills/productivity',txt)
        self.assertNotIn('systemctl restart',txt)
        self.assertNotIn('getUpdates',txt)
        self.assertNotIn('TELEGRAM_BOT_TOKEN',txt)

if __name__ == '__main__':
    unittest.main()
