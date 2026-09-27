"""Tests de la politique d'arbitrage du portefeuille Flow Scout."""

from __future__ import annotations

import json
import re
import unittest

from app.flow_scout.alignment_dashboard import render_alignment_dashboard
from app.flow_scout.portfolio_decision import (
    build_alignment_dashboard,
    evaluate_portfolio,
    evaluate_portfolio_item,
    load_decision_policy,
)


def _item(item_id: str, *, score: float = 75) -> dict[str, object]:
    return {
        "item_id": item_id,
        "metrics": {
            "strategic_alignment": score,
            "value_evidence": score,
            "feasibility": score,
            "adoption": score,
            "skills_readiness": score,
            "data_quality": score,
            "control_readiness": score,
            "cost_efficiency": score,
        },
        "signals": [],
        "evidence_refs": ["Flow_Scout_Assureur_Demo_Donnees.xlsx#IA!G7"],
        "evidence_coverage_percent": 100,
        "open_blocking_questions": 0,
        "confidence": 90,
    }


class FlowScoutPortfolioDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_decision_policy()

    def test_policy_is_versioned_and_balanced(self) -> None:
        self.assertEqual(
            self.policy["schema_version"],
            "flow-scout-portfolio-decision-policy-v1",
        )
        self.assertEqual(
            sum(self.policy["score_model"]["weights_percent"].values()), 100
        )
        self.assertEqual(len(self.policy["_meta"]["sha256"]), 64)

    def test_ai_002_is_suspended_even_when_its_score_is_high(self) -> None:
        item = _item("AI-002", score=95)
        item["signals"] = ["delegation_overrun"]
        result = evaluate_portfolio_item(item, policy=self.policy)
        self.assertEqual(result["recommended_option"], "SUSPEND")
        self.assertEqual(result["triggered_rules"][0]["rule_id"], "GATE-001")
        self.assertFalse(result["agent_action"]["can_execute_external_action"])
        self.assertTrue(result["human_approval"]["required"])
        self.assertEqual(result["human_approval"]["status"], "PENDING")

    def test_act_012_requires_skills_remediation(self) -> None:
        item = _item("ACT-012", score=80)
        item["signals"] = ["critical_skill_gap"]
        result = evaluate_portfolio_item(item, policy=self.policy)
        self.assertEqual(result["recommended_option"], "REMEDIATE")
        self.assertIn("ressources_humaines", result["human_approval"]["required_reviewers"])

    def test_time_saved_is_not_automatically_a_budget_saving(self) -> None:
        item = _item("VALUE-TIME-ONLY", score=85)
        item["signals"] = ["time_without_budget_savings"]
        result = evaluate_portfolio_item(item, policy=self.policy)
        self.assertEqual(result["recommended_option"], "PILOT")
        self.assertIn("finance", result["human_approval"]["required_reviewers"])

    def test_a_complete_high_score_prepares_scaling_but_never_finalizes_it(self) -> None:
        result = evaluate_portfolio_item(_item("AI-READY", score=90), policy=self.policy)
        self.assertEqual(result["recommended_option"], "SCALE")
        self.assertEqual(result["portfolio_score"], 90)
        self.assertEqual(result["agent_action"]["status"], "STAGED_BLOCKED")
        self.assertFalse(result["agent_action"]["automatic_finalization"])

    def test_missing_information_blocks_the_recommendation(self) -> None:
        item = _item("AI-INCOMPLETE", score=90)
        del item["metrics"]["value_evidence"]
        item["evidence_refs"] = []
        item["evidence_coverage_percent"] = 0
        result = evaluate_portfolio_item(item, policy=self.policy)
        self.assertEqual(result["recommended_option"], "REQUEST_INFORMATION")
        self.assertIn("value_evidence", result["missing_metrics"])
        self.assertIsNone(result["portfolio_score"])

    def test_portfolio_queue_places_immediate_risk_first(self) -> None:
        safe = _item("AI-SAFE", score=90)
        risky = _item("AI-RISKY", score=90)
        risky["signals"] = ["uncontrolled_payment"]
        portfolio = evaluate_portfolio([safe, risky], policy=self.policy)
        self.assertEqual(portfolio["item_count"], 2)
        self.assertEqual(portfolio["review_queue"][0]["item_id"], "AI-RISKY")
        self.assertEqual(portfolio["review_queue"][0]["recommended_option"], "SUSPEND")
        self.assertTrue(portfolio["human_approval_required"])
        self.assertFalse(portfolio["automatic_finalization"])

    def test_alignment_dashboard_proposes_the_priority_action(self) -> None:
        ready = _item("AI-READY", score=90)
        misaligned = _item("AI-DATA-GAP", score=90)
        misaligned["metrics"]["data_quality"] = 30
        dashboard = build_alignment_dashboard(
            [ready, misaligned], policy=self.policy
        )
        self.assertEqual(dashboard["overall_status"], "RED")
        self.assertEqual(dashboard["priority_actions"][0]["dimension"], "data_quality")
        self.assertIn("AI-DATA-GAP", dashboard["priority_actions"][0]["affected_items"])
        self.assertEqual(
            dashboard["priority_actions"][0]["agent_action"],
            "STAGE_FOR_HUMAN_APPROVAL",
        )
        self.assertTrue(dashboard["human_approval_required"])
        self.assertFalse(dashboard["automatic_finalization"])

    def test_fully_aligned_dashboard_is_green(self) -> None:
        dashboard = build_alignment_dashboard(
            [_item("AI-ALIGNED", score=90)], policy=self.policy
        )
        self.assertEqual(dashboard["overall_status"], "GREEN")
        self.assertEqual(dashboard["portfolio_alignment_score"], 90)
        self.assertEqual(dashboard["priority_actions"], [])
        self.assertEqual(dashboard["publication_status"], "STAGED_BLOCKED")

    def test_visual_dashboard_is_local_and_contains_its_source_data(self) -> None:
        dashboard = build_alignment_dashboard(
            [_item("AI-ALIGNED", score=90)], policy=self.policy
        )
        page = render_alignment_dashboard(dashboard)
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)
        self.assertIn("Dashboard d'alignement", page)
        self.assertIn("AI-ALIGNED", page)
        match = re.search(
            r'<script type="application/json" id="flow-scout-dashboard-data">(.*?)</script>',
            page,
            flags=re.S,
        )
        self.assertIsNotNone(match)
        embedded = json.loads(match.group(1))
        self.assertEqual(embedded["portfolio_alignment_score"], 90)


if __name__ == "__main__":
    unittest.main()
