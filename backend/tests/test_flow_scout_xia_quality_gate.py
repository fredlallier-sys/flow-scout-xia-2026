from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.flow_scout.winner_demo import run_winner_demo
from app.flow_scout.xia_quality_gate import evaluate_xia_readiness

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE = PROJECT_ROOT / "docs/references/Flow_Scout_Assureur_Demo_Donnees.xlsx"


@unittest.skipUnless(SOURCE.is_file(), "jeu assureur de démonstration absent")
class FlowScoutXiaQualityGateTests(unittest.TestCase):
    def test_score_is_evidence_based_and_never_claimed_as_official(self) -> None:
        result = run_winner_demo(SOURCE, replay_count=5)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "Lancer_Flow_Scout_Jury.command",
                "scripts/build_jury_mode.py",
                "outputs/winner-demo/Flow_Scout_2min_sexy_pro.mp4",
                "docs/jury/SUBMISSION-CHECKLIST.md",
            ):
                marker = root / relative
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.touch()
            scorecard = evaluate_xia_readiness(result, project_root=root)
        self.assertFalse(scorecard["is_official_jury_score"])
        self.assertEqual(sum(c["weight_percent"] for c in scorecard["criteria"].values()), 100)
        self.assertGreaterEqual(scorecard["score_out_of_10"], 8)
        self.assertLessEqual(scorecard["score_out_of_10"], 10)
        self.assertEqual(
            scorecard["top_gap"]["check_id"],
            "live_llm_orchestration_evidence",
        )

    def test_a_bounded_orchestration_receipt_closes_the_main_gap(self) -> None:
        result = run_winner_demo(SOURCE, replay_count=1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = root / "outputs/winner-demo/external-orchestration-evidence.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text("{}\n", encoding="utf-8")
            scorecard = evaluate_xia_readiness(result, project_root=root)
        gaps = {item["check_id"] for item in scorecard["gaps"]}
        self.assertNotIn("live_llm_orchestration_evidence", gaps)


if __name__ == "__main__":
    unittest.main()
