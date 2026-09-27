"""Garde-fous du pont Codex harness."""

from __future__ import annotations

import unittest
from json import dumps
from pathlib import Path
from types import SimpleNamespace

from app.flow_scout.codex_gateway import (
    CodexHarnessError,
    review_with_codex,
    review_with_codex_local,
)
from app.flow_scout.operator import build_agent_preview
from app.flow_scout.pipelex_bridge import build_pipelex_packet

_REFERENCE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "references"
    / "Flow_Scout_Assureur_Demo_Donnees.xlsx"
)


class _Events:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self.events = events

    def __enter__(self) -> _Events:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __iter__(self):
        return iter(self.events)


class _Sessions:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self.events = events
        self.last_request: dict[str, object] | None = None

    def create(self, **kwargs: object) -> _Events:
        self.last_request = kwargs
        return _Events(self.events)


class _Client:
    def __init__(self, events: list[dict[str, object]]) -> None:
        sessions = _Sessions(events)
        self.sessions = sessions
        self.beta = type("Beta", (), {"agents": type("Agents", (), {"sessions": sessions})()})()

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *args: object) -> None:
        return None


@unittest.skipUnless(_REFERENCE.is_file(), "jeu assureur de demonstration absent")
class FlowScoutCodexGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.preview = build_agent_preview(_REFERENCE)
        cls.packet = build_pipelex_packet(cls.preview)

    def test_confirmation_is_mandatory(self) -> None:
        with self.assertRaisesRegex(CodexHarnessError, "Confirmation"):
            review_with_codex(
                self.preview,
                confirmed_existing_credits=False,
                client_factory=lambda: _Client([]),
            )

    def test_valid_review_returns_a_traceable_receipt(self) -> None:
        finding = self.packet["findings"][0]
        review = {
            "executive_summary": "Relecture sous controle humain.",
            "findings": [
                {
                    "finding_id": finding["finding_id"],
                    "target_object_ids": finding["objects"],
                    "plain_language_title": "Controle humain requis",
                    "plain_language_explanation": "La preuve indique un controle manquant.",
                    "proposed_action": "Faire valider le perimetre par le responsable.",
                    "evidence_refs": [finding["evidence"][0]["locator"]],
                    "confidence": "elevee",
                    "needs_human_validation": True,
                }
            ],
            "questions": [],
            "atlas_recommendation": "STAGED_BLOCKED",
            "refused_claims": [],
            "limitations": [],
        }
        events = [
            {
                "type": "agent.session.created",
                "session": {"id": "sess_test"},
            },
            {
                "type": "agent.session.turn.output_text.done",
                "text": __import__("json").dumps(review),
            },
            {
                "type": "agent.session.turn.completed",
                "turn": {
                    "subagent_id": None,
                    "usage": {"input_tokens": 120, "output_tokens": 80, "total_tokens": 200},
                },
            },
        ]
        receipt = review_with_codex(
            self.preview,
            confirmed_existing_credits=True,
            client_factory=lambda: _Client(events),
        )
        self.assertTrue(receipt["completed"])
        self.assertEqual(receipt["session_id"], "sess_test")
        self.assertEqual(receipt["usage"]["total_tokens"], 200)
        self.assertTrue(receipt["contract_validation"]["accepted"])

    def test_unknown_evidence_is_rejected(self) -> None:
        finding = self.packet["findings"][0]
        review = {
            "executive_summary": "Relecture.",
            "findings": [
                {
                    "finding_id": finding["finding_id"],
                    "target_object_ids": finding["objects"],
                    "plain_language_title": "Controle",
                    "plain_language_explanation": "Explication.",
                    "proposed_action": "Verifier.",
                    "evidence_refs": ["INVENTEE!A1"],
                    "confidence": "elevee",
                    "needs_human_validation": True,
                }
            ],
            "questions": [],
            "atlas_recommendation": "STAGED_BLOCKED",
            "refused_claims": [],
            "limitations": [],
        }
        events = [
            {"type": "agent.session.turn.output_text.done", "text": __import__("json").dumps(review)},
            {"type": "agent.session.turn.completed", "turn": {"subagent_id": None}},
        ]
        with self.assertRaisesRegex(CodexHarnessError, "references inconnues"):
            review_with_codex(
                self.preview,
                confirmed_existing_credits=True,
                client_factory=lambda: _Client(events),
            )

    def test_local_mode_requires_confirmation(self) -> None:
        with self.assertRaisesRegex(CodexHarnessError, "Confirmation"):
            review_with_codex_local(
                self.preview,
                confirmed_subscription_usage=False,
                project_root=_REFERENCE.parents[2],
                codex_binary="/fake/codex",
            )

    def test_local_mode_is_read_only_and_does_not_forward_api_keys(self) -> None:
        finding = self.packet["findings"][0]
        review = {
            "executive_summary": "Relecture locale bornee.",
            "findings": [
                {
                    "finding_id": finding["finding_id"],
                    "target_object_ids": finding["objects"],
                    "plain_language_title": "Controle humain requis",
                    "plain_language_explanation": "La preuve indique un controle manquant.",
                    "proposed_action": "Faire valider le perimetre par le responsable.",
                    "evidence_refs": [finding["evidence"][0]["locator"]],
                    "confidence": "elevee",
                    "needs_human_validation": True,
                }
            ],
            "questions": [],
            "atlas_recommendation": "STAGED_BLOCKED",
            "refused_claims": [],
            "limitations": [],
        }
        captured: dict[str, object] = {}

        def fake_runner(command, **kwargs):
            captured["command"] = command
            captured["environment"] = kwargs["env"]
            schema_flag = command.index("--output-schema")
            captured["schema"] = __import__("json").loads(
                Path(command[schema_flag + 1]).read_text(encoding="utf-8")
            )
            output_flag = command.index("--output-last-message")
            Path(command[output_flag + 1]).write_text(dumps(review), encoding="utf-8")
            return SimpleNamespace(
                returncode=0,
                stdout=dumps({"type": "thread.started", "thread_id": "local-test"}) + "\n",
                stderr="",
            )

        receipt = review_with_codex_local(
            self.preview,
            confirmed_subscription_usage=True,
            project_root=_REFERENCE.parents[2],
            codex_binary=Path(__file__),
            runner=fake_runner,
        )
        command = captured["command"]
        environment = captured["environment"]
        self.assertIn("read-only", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("CODEX_API_KEY", environment)
        self.assertFalse(receipt["api_key_forwarded"])
        self.assertEqual(receipt["session_id"], "local-test")
        self.assertTrue(receipt["contract_validation"]["accepted"])
        schema = captured["schema"]
        finding_properties = schema["properties"]["findings"]["items"]["properties"]
        self.assertIn(finding["finding_id"], finding_properties["finding_id"]["enum"])
        self.assertIn(
            finding["evidence"][0]["locator"],
            finding_properties["evidence_refs"]["items"]["enum"],
        )


if __name__ == "__main__":
    unittest.main()
