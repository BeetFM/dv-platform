import unittest
from dataclasses import replace

from dv_platform.verification.coverage_intent import (
    CoverageIntent,
    CoverageObservation,
    canonical_coverage_intent_id,
    reconcile_coverage_intent,
)


class CoverageIntentTests(unittest.TestCase):
    def _bin(self, name: str = " LOW   address ") -> CoverageIntent:
        return CoverageIntent("rtl/top.sv:10", "top.u_ram", "WIDTH=8", "bin", name, "rev-1")

    def test_bin_identity_is_normalized_and_cross_members_are_canonical(self) -> None:
        low = self._bin()
        same = self._bin("low address")
        self.assertEqual(low.point_id, same.point_id)
        high = self._bin("high address")
        cross = CoverageIntent(
            "rtl/top.sv:12",
            "top.u_ram",
            "WIDTH=8",
            "cross",
            "address extremes",
            "rev-1",
            (high.point_id, low.point_id),
        )
        reverse = replace(cross, members=(low.point_id, high.point_id))
        self.assertEqual(cross.point_id, reverse.point_id)
        with self.assertRaises(ValueError):
            canonical_coverage_intent_id(
                source_locator="rtl/top.sv:12",
                hierarchy="top",
                specialization="WIDTH=8",
                kind="cross",
                name="invalid",
                members=(low.point_id,),
            )

    def test_all_non_closing_states_remain_explicit(self) -> None:
        intents = tuple(self._bin(name) for name in ("missing", "stale", "excluded", "missed", "zero", "uncovered"))
        intents = tuple(replace(intent, intentionally_missed=intent.name == "missed") for intent in intents)
        observations = (
            CoverageObservation(intents[1].point_id, "old", 1),
            CoverageObservation(intents[2].point_id, "rev-1", 1, excluded=True),
            CoverageObservation(intents[3].point_id, "rev-1", 1),
            CoverageObservation(intents[4].point_id, "rev-1", 0, denominator=0),
            CoverageObservation(intents[5].point_id, "rev-1", 0),
            CoverageObservation("orphan", "rev-1", 99),
        )
        records = reconcile_coverage_intent(intents, observations)
        states = {str(record["status"]) for record in records}
        self.assertEqual(
            states,
            {
                "missing",
                "stale",
                "excluded_only",
                "intentionally_missed",
                "zero_denominator",
                "uncovered",
                "orphaned",
            },
        )
        self.assertFalse(any(bool(record["closing"]) for record in records))

    def test_only_current_included_nonzero_observation_closes(self) -> None:
        intent = self._bin()
        records = reconcile_coverage_intent(
            (intent,),
            (CoverageObservation(intent.point_id, "rev-1", 2, denominator=4),),
        )
        self.assertEqual(records[0]["status"], "covered")
        self.assertTrue(records[0]["closing"])


if __name__ == "__main__":
    unittest.main()
