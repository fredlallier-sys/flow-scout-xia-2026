"""Contrats de données de la couche d'ingestion Flow Scout.

Cette couche ne déduit rien. Elle transforme seulement un tableau source en lignes
structurées et conserve, pour chaque valeur, son emplacement exact dans le fichier.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

Scalar: TypeAlias = str | int | float | bool | None


class SourceKind(StrEnum):
    SUBSCRIPTIONS = "subscriptions"
    APPLICATIONS = "applications"
    WORKFORCE = "workforce"
    AI_INVENTORY = "ai_inventory"
    COLLECTION_CATALOG = "collection_catalog"
    DEMO_GUIDE = "demo_guide"
    DEMO_COLLECTION = "demo_collection"
    DEMO_EXTRACTS = "demo_extracts"
    DEMO_ORGANIZATION = "demo_organization"
    DEMO_ACTIVITIES = "demo_activities"
    DEMO_DECISIONS = "demo_decisions"
    DEMO_APPLICATIONS = "demo_applications"
    DEMO_AI = "demo_ai"
    DEMO_COSTS = "demo_costs"
    DEMO_VALUE = "demo_value"
    DEMO_METRICS = "demo_metrics"
    DEMO_EVENTS = "demo_events"
    DEMO_RELATIONS = "demo_relations"
    DEMO_EXPECTED_RESULTS = "demo_expected_results"
    DEMO_SUMMARY = "demo_summary"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CellEvidence:
    """Preuve minimale permettant de revenir à la cellule source."""

    file: str
    sheet: str
    cell: str
    quote: str

    @property
    def locator(self) -> str:
        return f"{self.sheet}!{self.cell}"

    def to_dict(self) -> dict[str, str]:
        return {
            "file": self.file,
            "sheet": self.sheet,
            "cell": self.cell,
            "locator": self.locator,
            "quote": self.quote,
        }


@dataclass(frozen=True)
class SourceRow:
    row_number: int
    values: dict[str, Scalar]
    evidence: dict[str, CellEvidence]

    def to_dict(self) -> dict[str, object]:
        return {
            "row_number": self.row_number,
            "values": self.values,
            "evidence": {key: value.to_dict() for key, value in self.evidence.items()},
        }


@dataclass(frozen=True)
class SourceTable:
    file_name: str
    sheet_name: str
    kind: SourceKind
    headers: tuple[str, ...]
    rows: tuple[SourceRow, ...]
    ignored_empty_rows: int = 0
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "file_name": self.file_name,
            "sheet_name": self.sheet_name,
            "kind": self.kind.value,
            "headers": list(self.headers),
            "row_count": len(self.rows),
            "ignored_empty_rows": self.ignored_empty_rows,
            "warnings": list(self.warnings),
            "rows": [row.to_dict() for row in self.rows],
        }


@dataclass(frozen=True)
class IngestionBatch:
    tables: tuple[SourceTable, ...]
    skipped_mirrors: tuple[str, ...] = ()
    unsupported_files: tuple[str, ...] = ()

    @property
    def row_count(self) -> int:
        return sum(len(table.rows) for table in self.tables)

    def to_dict(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for table in self.tables:
            counts[table.kind.value] = counts.get(table.kind.value, 0) + len(table.rows)
        return {
            "schema_version": "flow-scout-ingestion-v1",
            "file_count": len({table.file_name for table in self.tables}),
            "table_count": len(self.tables),
            "row_count": self.row_count,
            "rows_by_kind": counts,
            "skipped_mirrors": list(self.skipped_mirrors),
            "unsupported_files": list(self.unsupported_files),
            "tables": [table.to_dict() for table in self.tables],
        }
