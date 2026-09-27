"""Règles déterministes de persistance d'un espace Flow Scout."""

from __future__ import annotations

import json

MAX_GRAPH_BYTES = 5 * 1024 * 1024


class WorkspaceGraphError(ValueError):
    """Le graphe ne respecte pas le contrat minimal Flow Scout."""


class WorkspaceGraphTooLarge(WorkspaceGraphError):
    """Le graphe dépasse la taille autorisée pour une sauvegarde."""


def validate_workspace_graph(graph: dict[str, object]) -> None:
    metadata = graph.get("_flow_scout")
    if not isinstance(metadata, dict) or not metadata.get("schema_version"):
        raise WorkspaceGraphError(
            "Le graphe ne contient pas les métadonnées Flow Scout attendues."
        )
    size = len(
        json.dumps(graph, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    if size > MAX_GRAPH_BYTES:
        raise WorkspaceGraphTooLarge("Le graphe Flow Scout dépasse la limite de 5 Mo.")


def qualification_status(graph: dict[str, object]) -> str:
    metadata = graph.get("_flow_scout")
    assessments = (
        metadata.get("use_case_assessments") if isinstance(metadata, dict) else None
    )
    if not isinstance(assessments, list) or not assessments:
        return "qualification_in_progress"
    statuses = []
    for assessment in assessments:
        confirmation = (
            assessment.get("confirmation") if isinstance(assessment, dict) else None
        )
        statuses.append(
            confirmation.get("status") if isinstance(confirmation, dict) else None
        )
    return (
        "validated"
        if all(item == "Validé" for item in statuses)
        else "qualification_in_progress"
    )
