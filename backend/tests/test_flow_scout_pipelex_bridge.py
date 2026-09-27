"""Contrat de securite de la relecture Pipelex optionnelle."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.flow_scout.operator import build_agent_preview
from app.flow_scout.pipelex_bridge import (
    build_pipelex_inputs,
    build_pipelex_packet,
    validate_pipelex_review,
)

_REFERENCE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "references"
    / "Flow_Scout_Assureur_Demo_Donnees.xlsx"
)


@unittest.skipUnless(_REFERENCE.is_file(), "jeu assureur de demonstration absent")
class FlowScoutPipelexBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet = build_pipelex_packet(build_agent_preview(_REFERENCE))

    def test_packet_is_minimized_and_marked_synthetic(self) -> None:
        packet = self.packet
        self.assertEqual(packet["schema_version"], "flow-scout-pipelex-packet-v1")
        self.assertTrue(packet["source"]["synthetic"])
        self.assertNotIn("report", packet)
        self.assertNotIn("atlas_payload", packet)
        self.assertEqual(len(packet["findings"]), 10)
        self.assertEqual(len(packet["questions"]), 3)
        self.assertTrue(all(item["priority"] == "P0" for item in packet["questions"]))

    def test_inputs_use_the_light_pipelex_shape(self) -> None:
        inputs = build_pipelex_inputs(build_agent_preview(_REFERENCE))
        self.assertEqual(list(inputs), ["flow_scout_packet"])
        decoded = json.loads(inputs["flow_scout_packet"])
        self.assertEqual(decoded["source"]["role"], "synthetic_demo_collection")

    def test_review_accepts_only_known_objects_and_evidence(self) -> None:
        finding = self.packet["findings"][0]
        review = {
            "executive_summary": "Relecture sous controle humain.",
            "atlas_recommendation": "STAGED_BLOCKED",
            "findings": [
                {
                    "finding_id": finding["finding_id"],
                    "target_object_ids": finding["objects"],
                    "plain_language_title": "Controle requis",
                    "plain_language_explanation": "Un controle humain est requis.",
                    "proposed_action": "Faire verifier la situation.",
                    "evidence_refs": [finding["evidence"][0]["locator"]],
                    "confidence": "elevee",
                    "needs_human_validation": True,
                }
            ],
            "questions": [],
            "refused_claims": [],
            "limitations": [],
        }
        self.assertTrue(validate_pipelex_review(review, self.packet)["accepted"])

        review["findings"][0]["evidence_refs"].append("Invented!A1")
        result = validate_pipelex_review(review, self.packet)
        self.assertFalse(result["accepted"])
        self.assertIn("Invented!A1", result["errors"][0])

    def test_review_can_never_request_automatic_publication(self) -> None:
        result = validate_pipelex_review(
            {
                "executive_summary": "Relecture sous controle humain.",
                "atlas_recommendation": "PUBLISHED",
                "findings": [],
                "questions": [],
                "refused_claims": [],
                "limitations": [],
            },
            self.packet,
        )
        self.assertFalse(result["accepted"])

    def test_review_rejects_aliases_instead_of_contract_field_names(self) -> None:
        result = validate_pipelex_review(
            {
                "executive_summary": "Relecture sous controle humain.",
                "atlas_recommendation": "STAGED_BLOCKED",
                "findings": [
                    {
                        "finding_id": "FIND-001",
                        "target_object_ids": ["AI-002"],
                        "constat": "Alias interdit.",
                        "confiance": "élevée",
                        "sources": ["IA!G7"],
                    }
                ],
                "questions": [],
                "refused_claims": [],
                "limitations": [],
            },
            self.packet,
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(any("champs interdits" in error for error in result["errors"]))

    def test_review_rejects_a_finding_without_evidence(self) -> None:
        finding = self.packet["findings"][0]
        result = validate_pipelex_review(
            {
                "executive_summary": "Relecture sous controle humain.",
                "atlas_recommendation": "STAGED_BLOCKED",
                "findings": [
                    {
                        "finding_id": finding["finding_id"],
                        "target_object_ids": finding["objects"],
                        "plain_language_title": "Controle requis",
                        "plain_language_explanation": "Un controle humain est requis.",
                        "proposed_action": "Faire verifier la situation.",
                        "evidence_refs": [],
                        "confidence": "elevee",
                        "needs_human_validation": True,
                    }
                ],
                "questions": [],
                "refused_claims": [],
                "limitations": [],
            },
            self.packet,
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(any("reference prouvee" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
