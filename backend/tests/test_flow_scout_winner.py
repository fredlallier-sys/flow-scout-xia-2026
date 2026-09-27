"""Tests du scénario Winner et du pont transactionnel Flow Atlas."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.flow_scout.atlas_bridge import (
    AtlasBridgeError,
    build_atlas_workspace,
    information_answer,
    inspect_atlas_v3_payload,
    rollback_atlas_workspace,
    stage_atlas_workspace,
)
from app.flow_scout.atlas_v3_lifecycle import (
    answer_atlas_v3_question,
    validate_atlas_v3_question,
)
from app.flow_scout.operator import build_agent_preview
from app.flow_scout.winner_demo import run_winner_demo


_REFERENCE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "references"
    / "Flow_Scout_Assureur_Demo_Donnees.xlsx"
)


@unittest.skipUnless(_REFERENCE.is_file(), "jeu assureur de démonstration absent")
class FlowScoutWinnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.preview = build_agent_preview(_REFERENCE)
        cls.payload = cls.preview["atlas_payload"]

    def test_bridge_inspection_is_complete_and_traceable(self) -> None:
        inspection = inspect_atlas_v3_payload(self.payload)
        self.assertTrue(inspection["can_import"])
        self.assertEqual(inspection["traceability"]["finding_rate_percent"], 100)
        self.assertEqual(
            inspection["traceability"]["source_localization_rate_percent"], 100
        )
        self.assertEqual(inspection["counts"]["findings"], 10)

    def test_bridge_refuses_an_unresolved_relation(self) -> None:
        corrupted = copy.deepcopy(self.payload)
        corrupted["sheets"]["Atlas Relations"]["rows"][0][
            "target_object_id"
        ] = "MISSING-OBJECT"
        inspection = inspect_atlas_v3_payload(corrupted)
        self.assertFalse(inspection["can_import"])
        self.assertTrue(
            any("objet absent" in message for message in inspection["errors"])
        )
        with self.assertRaises(AtlasBridgeError):
            build_atlas_workspace(corrupted)

    def test_workspace_scores_are_bounded_and_never_published(self) -> None:
        workspace = build_atlas_workspace(self.payload)
        scorecard = workspace["cockpit"]["scorecard"]
        self.assertTrue(scorecard["bounded_0_100"])
        self.assertFalse(workspace["published"])
        self.assertTrue(workspace["human_approval_required"])
        self.assertEqual(len(workspace["maps"]), 7)
        for item in scorecard["dimensions"].values():
            if item["score"] is not None:
                self.assertGreaterEqual(item["score"], 0)
                self.assertLessEqual(item["score"], 100)

    def test_unknown_or_pending_fact_returns_information_insufficient(self) -> None:
        answer = information_answer(
            self.payload,
            target_object_id="AI-008",
            question="Cette IA est-elle conforme ?",
        )
        self.assertEqual(answer["answer"], "Information insuffisante")
        self.assertFalse(answer["decision_allowed"])

    def test_staging_is_versioned_and_rollback_is_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = stage_atlas_workspace(
                self.payload,
                directory,
                imported_by="Test",
                imported_at="2026-09-25T10:00:00Z",
            )
            question = next(
                row
                for row in self.payload["sheets"]["Atlas Questions"]["rows"]
                if row["rule_id"] == "R-004" and row["target_object_id"] == "AI-002"
            )
            answered = answer_atlas_v3_question(
                self.payload,
                question_id=question["question_id"],
                answer={"observed_level": 2},
                answered_by="Métier",
                answered_at="2026-09-25T10:01:00Z",
            )
            validated = validate_atlas_v3_question(
                answered,
                question_id=question["question_id"],
                validator="Contrôle interne",
                accepted=True,
                resolution_confirmed=True,
                validated_at="2026-09-25T10:02:00Z",
            )
            second = stage_atlas_workspace(
                validated,
                directory,
                imported_by="Test",
                imported_at="2026-09-25T10:03:00Z",
            )
            first_id = first["workspace"]["import"]["import_id"]
            second_id = second["workspace"]["import"]["import_id"]
            self.assertNotEqual(first_id, second_id)
            restored = rollback_atlas_workspace(
                directory,
                import_id=first_id,
                rolled_back_by="Test",
                rolled_back_at="2026-09-25T10:04:00Z",
            )
            self.assertEqual(restored["import"]["import_id"], first_id)
            active = json.loads(
                (Path(directory) / "active.json").read_text(encoding="utf-8")
            )
            self.assertEqual(active["import"]["import_id"], first_id)

    def test_winner_demo_passes_all_acceptance_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_winner_demo(
                _REFERENCE, output_directory=directory, replay_count=5
            )
            evaluation = result["evaluation"]
            self.assertTrue(evaluation["passed"])
            self.assertEqual(evaluation["success_rate_percent"], 100)
            self.assertEqual(evaluation["replay_count"], 5)
            self.assertEqual(len(set(evaluation["semantic_fingerprints"])), 1)
            self.assertEqual(
                result["information_insufficient_example"]["answer"],
                "Information insuffisante",
            )
            self.assertLess(result["timeline"][-1]["at_second"], 300)
            for path in result["artifacts"].values():
                self.assertTrue(Path(path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
