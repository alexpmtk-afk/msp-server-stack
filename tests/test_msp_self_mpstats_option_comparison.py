"""Unit tests for value-private comparison of MPSTATS card option snapshots."""
import unittest
from apps.msp_self_analytics.mpstats_option_comparison import compare_option_snapshots


def card(*items):
    rows=[{"name":name,"value":value} for name,value in items]
    return {"data":{"options":rows,"groups":[{"options":list(rows)}]}}


class MpstatsOptionComparisonTest(unittest.TestCase):
    def test_exact_values_and_different_values(self):
        own=card(("Материал изделия","Сталь"),("Высота предмета","80"),
                 ("Ширина предмета","30"),("Объем (л)","45"),
                 ("Ширина упаковки","31"))
        peer=card(("Материал изделия"," сталь "),("Высота предмета","75"),
                  ("Ширина предмета","30"),("Объём (л)","45"),
                  ("Ширина упаковки","31"))
        x=compare_option_snapshots(own,peer)
        self.assertEqual(x["fields"]["material"]["status"],"MATCH")
        self.assertEqual(x["fields"]["item_height"]["status"],"DIFFERENT")
        self.assertEqual(x["fields"]["item_width"]["status"],"MATCH")
        self.assertEqual(x["fields"]["volume_l"]["status"],"MATCH")
        self.assertEqual(x["fields"]["package_width"]["status"],"MATCH")
        self.assertTrue(x["fields"]["package_width"]["is_packaging_not_item_dimension"])
        self.assertFalse(x["fields"]["item_width"]["item_dimension_unit_explicit"])
        self.assertEqual(x["status"],"OBSERVED_OPTIONS_SNAPSHOT_ONLY")
        self.assertEqual(x["verified_comparable_competitors"],0)

    def test_peer_only_fields_and_both_missing(self):
        x=compare_option_snapshots(card(("Материал изделия","ткань")),
            card(("Материал изделия","ткань"),("Форма","квадрат")))
        self.assertEqual(x["fields"]["shape"]["status"],"ONLY_PEER")
        self.assertEqual(x["fields"]["mounting"]["status"],"BOTH_MISSING")

    def test_conflicting_duplicate_options_do_not_silently_overwrite(self):
        own={"options":[{"name":"Материал изделия","value":"сталь"},
                        {"name":"Материал изделия","value":"пластик"}]}
        peer=card(("Материал изделия","сталь"))
        x=compare_option_snapshots(own,peer)
        self.assertEqual(x["fields"]["material"]["status"],"AMBIGUOUS")

    def test_unreadable_values_are_not_guessed(self):
        own=card(("Комплектация",{"free":"text"}))
        peer=card(("Комплектация","одна урна"))
        x=compare_option_snapshots(own,peer)
        self.assertEqual(x["fields"]["kit"]["status"],"AMBIGUOUS")

    def test_non_structured_payload_rejected(self):
        with self.assertRaisesRegex(ValueError,"STRUCTURED_CARD_PAYLOADS_REQUIRED"):
            compare_option_snapshots(None,card(("Цвет","серый")))
        with self.assertRaisesRegex(ValueError,"STRUCTURED_CARD_PAYLOADS_REQUIRED"):
            compare_option_snapshots({},[])

    def test_private_values_never_in_public_result(self):
        own=card(("Материал изделия","SecretMarkI"),
                 ("Ширина предмета","98765"))
        peer=card(("Материал изделия","SecretMarkII"),
                  ("Ширина предмета","98766"))
        x=compare_option_snapshots(own,peer)
        self.assertNotIn("SecretMark",str(x))
        self.assertNotIn("98765",str(x))
        self.assertNotIn("98766",str(x))
        self.assertEqual(x["fields"]["material"]["status"],"DIFFERENT")

    def test_unknown_labels_not_fabricated(self):
        x=compare_option_snapshots(
          card(("Срок службы","4 года")),card(("Срок службы","4 года")))
        self.assertEqual(x["counts"]["MATCH"],0)
        self.assertEqual(x["counts"]["BOTH_MISSING"],15)

    def test_no_causal_or_historical_claims(self):
        x=compare_option_snapshots(card(("Материал изделия","сталь")),
                                   card(("Материал изделия","сталь")))
        self.assertFalse(x["historic_attributes_verified"])
        self.assertFalse(x["safe_for_causal_control_group"])
        self.assertFalse(x["automated_marketplace_actions"])


if __name__=="__main__":
    unittest.main()
