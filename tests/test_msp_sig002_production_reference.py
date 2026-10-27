from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/"apps/hermes/msp_signals_skill/SKILL.md"
REFERENCE=ROOT/"apps/hermes/msp_signals_skill/references/production-orders.md"

class Sig002ProductionReference(unittest.TestCase):
    def test_skill_calls_for_two_source_lookup_before_old_rule(self):
        s=SKILL.read_text(encoding="utf-8")
        a=s.index("## Дополнение SIG-002 от 27.10.2026")
        b=s.index("## Обязательное правило SIG-002 «Поднять цену» (09.10.2026)")
        self.assertLess(a,b)
        self.assertIn("references/production-orders.md",s[a:b])
        self.assertIn("product_listing",s[a:b])
        self.assertIn("production_sewing_order",s[a:b])
        self.assertIn("production_metal_order",s[a:b])
        self.assertIn("Отсутствие даты",s[a:b])
    def test_semantics_all_source_columns_and_no_automatic_price(self):
        t=REFERENCE.read_text(encoding="utf-8")
        for col in ("requester","internal_article","requested_qty_raw","delivered_qty_raw",
                    "remainder_qty_raw","placed_at_iso","desired_at_iso","confirmed_at_iso",
                    "comment_text","responsible","data_quality","issues_json",
                    "is_current","source_row"):
            self.assertIn(col,t)
        self.assertIn("не является разрешением изменять цены",t)
        self.assertIn("Отдельной колонки «Осталось» в швейке НЕТ",t)

if __name__=="__main__":unittest.main()
