"""Peer screening does not create approved controls from marketplace 'similar'."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("msp_peer_prefilter",ROOT/"apps/msp_self_analytics/peer_prefilter.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestPeerPrefilter(unittest.TestCase):
    def test_subject_matches_are_only_candidates(self):
        own={"id":111222333,"subject":"  Тенты  "}
        rows=[
            {"id":222333444,"subject":"тенты"},
            {"id":222333445,"subject":"палатки"},
            {"id":222333446,"subject":None},
        ]
        r=m.prefilter(own,rows)
        self.assertEqual(r["candidate_count"],3)
        self.assertEqual(r["counts"]["SUBJECT_NAME_MATCH"],1)
        self.assertEqual(r["counts"]["SUBJECT_NAME_DIFFERENT"],1)
        self.assertEqual(r["counts"]["SUBJECT_UNKNOWN"],1)
        self.assertEqual(r["automatically_verified_competitors"],0)
        self.assertFalse(r["can_compute_peer_control_comparison"])

    def test_own_and_duplicate_skus_excluded(self):
        own={"id":111222333,"subject":{"name":"Пледы"}}
        rows=[{"id":111222333,"subject":"Пледы"},
              {"id":222333444,"subject":"Пледы"},
              {"id":222333444,"subject":"Пледы"}]
        r=m.prefilter(own,rows)
        self.assertEqual(r["counts"]["OWN_PRODUCT_EXCLUDED"],1)
        self.assertEqual(r["counts"]["DUPLICATE_EXCLUDED"],1)
        self.assertEqual(r["counts"]["SUBJECT_NAME_MATCH"],1)

    def test_unknown_subject_never_approved(self):
        r=m.prefilter({"id":111222333},[{"id":222333444,"subject":"Пледы"}])
        self.assertEqual(r["counts"]["SUBJECT_UNKNOWN"],1)
        self.assertFalse(r["subject_name_usable_on_own_card"])

    def test_subject_id_disagreement_blocks_name_match(self):
        r=m.prefilter({"id":111222333,"subject":"Пледы","subject_id":1},
                      [{"id":222333444,"subject":"Пледы","subject_id":2}])
        self.assertEqual(r["counts"]["SUBJECT_ID_DIFFERENT"],1)
        self.assertEqual(r["automatically_verified_competitors"],0)

    def test_ids_and_raw_product_details_not_returned(self):
        r=m.prefilter({"id":111222333,"subject":"Пледы"},
                      [{"id":222333444,"subject":"Пледы","name":"Мой коммерческий товар"}])
        self.assertNotIn("111222333",str(r))
        self.assertNotIn("222333444",str(r))
        self.assertNotIn("Мой коммерческий товар",str(r))

    def test_bounded_inputs(self):
        with self.assertRaisesRegex(ValueError,"CANDIDATE_LIMIT_EXCEEDED"):
            m.prefilter({"subject":"Пледы"},[{"id":111222333}]*9,max_candidates=8)
        with self.assertRaisesRegex(ValueError,"INVALID_PEER_INPUT"):
            m.prefilter("not an item",[])

if __name__=="__main__":
    unittest.main()
