"""Check exact attribute provenance gate; no automatic competitor certification."""
import unittest
from apps.msp_self_analytics.peer_evidence import evaluate_peer_evidence, FIELDS


def listing(ident, *, name="Урна", use="общественные места",
            size=(400, 300, 800), material="сталь", units=1,
            observed_on="2026-10-20"):
    values = {"id": ident, "subject": name, "intended_use": use,
              "dimensions_mm": size, "material": material,
              "package_units": units}
    values["evidence"] = {
        key: {"source_type": "supplier_specification",
              "source_ref": "internal-source-record",
              "observed_on": observed_on} for key in FIELDS}
    return values


class PeerEvidenceTest(unittest.TestCase):
    def test_complete_equal_metadata_still_not_verified(self):
        r = evaluate_peer_evidence(listing(111222333), [listing(222333444)],
                                   as_of="2026-10-22")
        self.assertEqual(r["matched_field_candidate_count"], 1)
        self.assertEqual(r["verified_comparator_count"], 0)
        self.assertEqual(r["candidates"][0]["status"], "MATCHED_FIELDS_REVIEW_REQUIRED")
        self.assertFalse(r["may_use_as_causal_control"])
        self.assertFalse(r["marketplace_actions_allowed"])

    def test_dimensions_and_pack_size_differences_are_explicit(self):
        r = evaluate_peer_evidence(listing(111222333), [
            listing(222333444, size=(400, 250, 800), units=2)],
            as_of="2026-10-22")
        self.assertEqual(r["candidates"][0]["status"], "STRUCTURED_FIELDS_DIFFER")
        self.assertEqual(set(r["candidates"][0]["field_names_to_review"]),
                         {"dimensions_mm", "package_units"})

    def test_unknown_purpose_rejected_even_with_subject_match(self):
        c = listing(222333444)
        c.pop("intended_use")
        r = evaluate_peer_evidence(listing(111222333), [c], as_of="2026-10-22")
        self.assertEqual(r["candidates"][0]["status"], "PEER_EVIDENCE_INCOMPLETE")
        self.assertIn("intended_use", r["candidates"][0]["field_names_to_review"])

    def test_old_stale_or_future_provenance_not_evidence(self):
        r = evaluate_peer_evidence(listing(111222333), [
            listing(222333444, observed_on="2026-05-01"),
            listing(222333445, observed_on="2026-10-23")],
            as_of="2026-10-22")
        self.assertEqual(r["counts"]["PEER_EVIDENCE_INCOMPLETE"], 2)

    def test_provenance_is_not_automatically_independent_approval(self):
        peer = listing(222333444)
        peer["evidence"]["material"].pop("source_ref")
        r = evaluate_peer_evidence(listing(111222333), [peer], as_of="2026-10-22")
        self.assertEqual(r["matched_field_candidate_count"], 0)
        self.assertIn("material", r["candidates"][0]["field_names_to_review"])

    def test_own_incomplete_cannot_certify_peers(self):
        own = listing(111222333)
        own["material"] = None
        r = evaluate_peer_evidence(own, [listing(222333444)], as_of="2026-10-22")
        self.assertEqual(r["candidates"][0]["status"], "OWN_EVIDENCE_INCOMPLETE")

    def test_duplicate_and_own_excluded(self):
        r = evaluate_peer_evidence(listing(111222333),
            [listing(111222333), listing(222333444), listing(222333444)],
            as_of="2026-10-22")
        self.assertEqual(r["counts"]["OWN_LISTING_EXCLUDED"], 1)
        self.assertEqual(r["counts"]["DUPLICATE_LISTING_EXCLUDED"], 1)
        self.assertEqual(r["matched_field_candidate_count"], 1)

    def test_private_values_never_exported(self):
        r = evaluate_peer_evidence(listing(111222333),
            [listing(222333444)], as_of="2026-10-22")
        self.assertNotIn("111222333", str(r))
        self.assertNotIn("222333444", str(r))
        self.assertNotIn("internal-source-record", str(r))
        self.assertNotIn("общественные места", str(r))
        self.assertNotIn("сталь", str(r))

    def test_hard_card_limit(self):
        with self.assertRaisesRegex(ValueError, "CANDIDATE_LIMIT_EXCEEDED"):
            evaluate_peer_evidence(listing(111222333),
                 [listing(222333444)]*21, as_of="2026-10-22")

    def test_invalid_timestamp_and_dimension_units_are_unknown(self):
        c = listing(222333444)
        c["dimensions_mm"] = "400x300x800"
        c["evidence"]["material"]["observed_on"] = "not-a-date"
        r = evaluate_peer_evidence(listing(111222333), [c], as_of="2026-10-22")
        self.assertEqual(r["candidates"][0]["status"], "PEER_EVIDENCE_INCOMPLETE")
        self.assertIn("dimensions_mm", r["candidates"][0]["field_names_to_review"])
        self.assertIn("material", r["candidates"][0]["field_names_to_review"])

    def test_no_source_evidence_from_provider_only_similarity(self):
        c = {"id": 222333444, "subject": "Урна",
             "intended_use": "общественные места", "dimensions_mm": [400, 300, 800],
             "material": "сталь", "package_units": 1}
        r = evaluate_peer_evidence(listing(111222333), [c], as_of="2026-10-22")
        self.assertEqual(r["verified_comparator_count"], 0)
        self.assertEqual(r["candidates"][0]["status"], "PEER_EVIDENCE_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
