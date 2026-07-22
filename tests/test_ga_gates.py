import json
from copy import deepcopy
from unittest import TestCase

from scripts.check_ga_gates import LEDGER, enforce_through, validate_ledger


class GAGateLedgerTests(TestCase):
    def setUp(self) -> None:
        self.document = json.loads(LEDGER.read_text(encoding="utf-8"))

    def test_checked_in_ledger_is_valid_and_not_prematurely_ready(self) -> None:
        self.assertEqual(validate_ledger(self.document), [])
        self.assertEqual(enforce_through(self.document, 6), [])
        self.assertEqual(enforce_through(self.document, 7), [])
        self.assertEqual(enforce_through(self.document, 8), [])
        self.assertEqual(enforce_through(self.document, 9), [])
        self.assertEqual(enforce_through(self.document, 10), [])
        self.assertTrue(enforce_through(self.document, 11))

    def test_rejects_out_of_order_completion_missing_evidence_and_duplicate_profiles(self) -> None:
        document = deepcopy(self.document)
        document["stages"][6]["status"] = "complete"
        document["profiles"].append(deepcopy(document["profiles"][0]))
        document["profiles"][0]["state"] = "qualified"
        document["profiles"][0]["evidence"] = []

        errors = validate_ledger(document)

        self.assertTrue(any("before an earlier stage" in error for error in errors))
        self.assertTrue(any("without evidence" in error for error in errors))
        self.assertTrue(any("duplicated" in error for error in errors))
        self.assertTrue(any("accepted without evidence" in error for error in errors))
