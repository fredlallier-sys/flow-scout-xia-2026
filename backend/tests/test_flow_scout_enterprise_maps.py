"""Contrat des sept cartes Flow Scout sur le jeu assureur synthétique."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.flow_scout.enterprise_maps import build_enterprise_maps
from app.flow_scout.ingestion import ingest_file
from app.flow_scout.models import SourceKind

_REFERENCE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "references"
    / "Flow_Scout_Assureur_Demo_Donnees.xlsx"
)


@unittest.skipUnless(_REFERENCE.is_file(), "jeu assureur de démonstration absent")
class FlowScoutEnterpriseMapsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tables = ingest_file(_REFERENCE)
        cls.report = build_enterprise_maps(_REFERENCE)

    def test_demo_workbook_headers_are_found_after_titles(self) -> None:
        by_kind = {table.kind: table for table in self.tables}
        self.assertEqual(len(self.tables), 15)
        self.assertEqual(len(by_kind[SourceKind.DEMO_COLLECTION].rows), 117)
        self.assertEqual(len(by_kind[SourceKind.DEMO_ACTIVITIES].rows), 40)
        self.assertEqual(len(by_kind[SourceKind.DEMO_RELATIONS].rows), 346)
        self.assertEqual(
            by_kind[SourceKind.DEMO_AI].rows[0].evidence["ai_id"].locator,
            "IA!A6",
        )

    def test_report_builds_seven_linked_maps(self) -> None:
        report = self.report
        self.assertEqual(report["map_count"], 7)
        self.assertEqual(
            [item["id"] for item in report["maps"]],
            [
                "human_work",
                "decisions_responsibilities",
                "knowledge_data",
                "tools_dependencies",
                "actual_ai_use",
                "value_cost",
                "transformation_opportunities",
            ],
        )
        self.assertEqual(report["cross_map_links"]["count"], 346)
        self.assertEqual(report["maps"][0]["summary"]["headcount_fte"], 1200)
        self.assertEqual(report["maps"][2]["summary"]["source_types"], 117)
        self.assertEqual(report["maps"][4]["summary"]["ai_usages"], 16)

    def test_blind_detection_does_not_read_expected_results(self) -> None:
        self.assertFalse(self.report["dataset"]["expected_results_sheet_used"])
        findings = {item["type"]: item for item in self.report["findings"]}
        expected_types = {
            "delegation_overrun",
            "functional_overlap",
            "time_without_budget_savings",
            "low_adoption",
            "data_incompleteness",
            "citation_quality",
            "unqualified_usage",
            "qualification_incomplete",
        }
        self.assertTrue(expected_types.issubset(findings))

        delegation = next(
            item
            for item in self.report["findings"]
            if item["type"] == "delegation_overrun" and "AI-002" in item["objects"]
        )
        self.assertEqual(delegation["measures"]["observed_level"], 4)
        self.assertEqual(delegation["measures"]["authorized_level"], 2)
        self.assertEqual(delegation["measures"]["payments_without_validation"], 12)

        overlap = next(
            item
            for item in self.report["findings"]
            if item["type"] == "functional_overlap" and "ACT-005" in item["objects"]
        )
        self.assertEqual(overlap["measures"]["combined_monthly_cost_eur"], 12000)

        time_value = findings["time_without_budget_savings"]
        self.assertEqual(time_value["measures"]["hours_released"], 180)
        self.assertEqual(time_value["measures"]["budget_savings_eur"], 0)

    def test_value_types_stay_separate_and_strategic_links_remain_open(self) -> None:
        value_summary = next(
            item["summary"]
            for item in self.report["maps"]
            if item["id"] == "value_cost"
        )
        self.assertEqual(value_summary["monthly_ai_cost_eur"], 84580)
        self.assertEqual(value_summary["budget_savings_eur"], 19000)
        self.assertEqual(value_summary["avoided_loss_estimate_eur"], 12000)
        self.assertEqual(value_summary["attributed_revenue_estimate_eur"], 13000)
        self.assertIn(
            "ne forment pas un bénéfice net", value_summary["aggregation_warning"]
        )
        self.assertEqual(self.report["strategic_depth"]["status"], "esquissée")
        self.assertIn(
            "objective_to_capability",
            self.report["strategic_depth"]["missing_links"],
        )

    def test_every_finding_is_traceable_to_cells(self) -> None:
        for finding in self.report["findings"]:
            self.assertTrue(finding["evidence"], finding["title"])
            for evidence in finding["evidence"]:
                self.assertEqual(evidence["file"], _REFERENCE.name)
                self.assertIn("!", evidence["locator"])


if __name__ == "__main__":
    unittest.main()
