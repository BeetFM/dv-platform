import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from dv_platform.analysis.ai_planning import (
    AIPlanningError,
    LiteLLMModelClient,
    ModelRequest,
    validate_proposal,
)


def _proposal() -> dict[str, object]:
    return {
        "schema_version": 2,
        "module": "top",
        "requirements": [
            {
                "proposal_id": "req-1",
                "statement": "Reset clears the output.",
                "signals": ["rst_n", "data_o"],
                "condition": "rst_n == 0",
                "expected_value": "data_o == 0",
                "evidence_ids": ["E1"],
            }
        ],
        "checks": [
            {
                "proposal_id": "check-1",
                "statement": "Check reset output.",
                "requirement_ids": ["req-1"],
                "evidence_ids": ["E1"],
            }
        ],
        "scenarios": [
            {
                "proposal_id": "scenario-1",
                "kind": "reset_sequence",
                "requirement_ids": ["req-1"],
                "check_ids": ["check-1"],
                "evidence_ids": ["E1"],
                "parameters": {"cycles": 2, "active_low": True, "edge": "rising"},
            }
        ],
        "assumptions": [{"statement": "Clock is running.", "evidence_ids": ["E1"]}],
        "open_questions": [{"statement": "Is reset synchronous?", "evidence_ids": ["E1"]}],
    }


def _validate(value: object, *, max_chars: int = 524_288):
    return validate_proposal(
        value,
        module="top",
        evidence_ids={"E1"},
        known_signals={"rst_n", "data_o"},
        max_chars=max_chars,
    )


class ProposalValidationBranchTests(unittest.TestCase):
    def test_v2_scenario_accepts_scalar_parameters_from_bytes(self) -> None:
        proposal = _validate(json.dumps(_proposal()).encode())

        self.assertEqual(proposal.schema_version, 2)
        self.assertEqual(
            proposal.scenarios[0].parameters,
            (("active_low", "True"), ("cycles", "2"), ("edge", "rising")),
        )

    def test_root_and_encoding_failure_matrix(self) -> None:
        cases = (
            b"\xff",
            b"{}" * 100,
            "not-json",
            '{"value": NaN}',
            [],
            {"schema_version": 99},
            {**_proposal(), "extra": True},
        )
        for value in cases:
            with self.subTest(value=repr(value)[:80]), self.assertRaises(AIPlanningError):
                _validate(value, max_chars=64 if value == b"{}" * 100 else 524_288)

        missing = _proposal()
        del missing["scenarios"]
        with self.assertRaisesRegex(AIPlanningError, "missing fields"):
            _validate(missing)

    def test_requirement_check_and_note_failure_matrix(self) -> None:
        mutations = (
            lambda p: p["requirements"][0].update(proposal_id="not valid"),
            lambda p: p["requirements"][0].update(statement=" "),
            lambda p: p["requirements"][0].update(signals=["rst_n", "rst_n"]),
            lambda p: p["requirements"][0].update(condition=[]),
            lambda p: p["requirements"][0].update(evidence_ids=[]),
            lambda p: p["checks"][0].update(requirement_ids=[]),
            lambda p: p["checks"][0].update(evidence_ids=["missing"]),
            lambda p: p["assumptions"][0].update(extra=True),
            lambda p: p.update(open_questions="not-an-array"),
        )
        for mutate in mutations:
            candidate = deepcopy(_proposal())
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(AIPlanningError):
                _validate(candidate)

        duplicate = deepcopy(_proposal())
        duplicate["checks"][0]["proposal_id"] = "req-1"
        duplicate["scenarios"][0]["check_ids"] = ["req-1"]
        with self.assertRaisesRegex(AIPlanningError, "duplicate proposal IDs"):
            _validate(duplicate)

    def test_scenario_failure_matrix(self) -> None:
        mutations = (
            lambda s: s.update(extra=True),
            lambda s: s.pop("kind"),
            lambda s: s.update(kind="raw_python"),
            lambda s: s.update(requirement_ids=["missing"]),
            lambda s: s.update(check_ids=["missing"]),
            lambda s: s.update(check_ids=[]),
            lambda s: s.update(parameters=[]),
            lambda s: s.update(parameters={f"p{index}": index for index in range(33)}),
            lambda s: s.update(parameters={"nested": {"code": "no"}}),
            lambda s: s.update(evidence_ids=["missing"]),
        )
        for mutate in mutations:
            candidate = deepcopy(_proposal())
            mutate(candidate["scenarios"][0])
            with self.subTest(candidate=candidate["scenarios"][0]), self.assertRaises(AIPlanningError):
                _validate(candidate)


class LiteLLMClientBranchTests(unittest.TestCase):
    @staticmethod
    def _request() -> ModelRequest:
        return ModelRequest("provider/model", "system", "user", {}, None, None, None, 1, 0, 16)

    def test_missing_dependency_is_categorized(self) -> None:
        with patch("dv_platform.analysis.ai_planning.importlib.import_module", side_effect=ImportError):
            with self.assertRaisesRegex(AIPlanningError, "not installed"):
                LiteLLMModelClient().complete(self._request())

    def test_provider_error_categories(self) -> None:
        errors = (
            (TimeoutError("late"), "timeout"),
            (RuntimeError("unauthorized"), "authentication_failed"),
            (RuntimeError("too many requests"), "rate_limited"),
            (RuntimeError("broken"), "provider_error"),
        )
        for error, category in errors:

            class FakeLiteLLM:
                @staticmethod
                def completion(_error=error, **_kwargs):
                    raise _error

            with (
                self.subTest(category=category),
                patch("dv_platform.analysis.ai_planning.importlib.import_module", return_value=FakeLiteLLM),
            ):
                with self.assertRaises(AIPlanningError) as raised:
                    LiteLLMModelClient().complete(self._request())
                self.assertEqual(raised.exception.category, category)

    def test_content_parts_usage_conversion_and_cost_failures(self) -> None:
        class FakeLiteLLM:
            @staticmethod
            def supports_response_schema(*, model):
                raise RuntimeError(model)

            @staticmethod
            def completion(**_kwargs):
                return {
                    "choices": [{"message": {"content": [{"text": "{"}, {"ignored": True}, {"text": "}"}]}}],
                    "usage": {"prompt_tokens": "2", "completion_tokens": b"3", "total_tokens": "bad"},
                    "retry_count": 1.9,
                }

            @staticmethod
            def completion_cost(**_kwargs):
                raise RuntimeError("cost unavailable")

        with patch("dv_platform.analysis.ai_planning.importlib.import_module", return_value=FakeLiteLLM):
            response = LiteLLMModelClient().complete(self._request())

        self.assertEqual(response.content, "{}")
        self.assertEqual((response.prompt_tokens, response.completion_tokens), (2, 3))
        self.assertIsNone(response.total_tokens)
        self.assertEqual(response.retry_count, 1)
        self.assertIsNone(response.cost)
        self.assertFalse(response.structured_output)

    def test_missing_choices_and_non_text_content_are_rejected(self) -> None:
        responses = ({}, {"choices": []}, {"choices": [{"message": {"content": []}}]})
        for provider_response in responses:

            class FakeLiteLLM:
                @staticmethod
                def completion(_response=provider_response, **_kwargs):
                    return _response

            with (
                self.subTest(response=provider_response),
                patch("dv_platform.analysis.ai_planning.importlib.import_module", return_value=FakeLiteLLM),
            ):
                with self.assertRaises(AIPlanningError):
                    LiteLLMModelClient().complete(self._request())


if __name__ == "__main__":
    unittest.main()
