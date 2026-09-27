"""Pont transactionnel entre le contrat Flow Scout v3 et un espace Flow Atlas.

Le pont ne publie jamais une décision. Il charge un instantané contrôlé dans un
espace Atlas local, conserve les versions précédentes et expose un cockpit
calculé uniquement à partir des contrôles et mesures du contrat v3.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.flow_scout.atlas_v3_lifecycle import summarize_atlas_v3


class AtlasBridgeError(ValueError):
    """Le contrat ne peut pas être chargé dans un espace Atlas."""


_REQUIRED_SHEETS = {
    "Atlas Objects": "object_id",
    "Atlas Relations": "relation_id",
    "Atlas Measures": "measure_id",
    "Atlas Findings": "finding_id",
    "Atlas Evidence": "evidence_id",
    "Atlas Questions": "question_id",
    "Atlas Rules": "rule_id",
    "Import Control": "control_id",
}

_SCORE_RULES = {
    "coverage": {"R-002", "R-003", "R-011", "R-015"},
    "skills": {"R-008"},
    "systems": {"R-003", "R-013"},
    "value": {"R-006", "R-007", "R-009", "R-012"},
    "governance": {"R-001", "R-004", "R-005", "R-010", "R-014"},
}

_STATUS_POINTS = {"PASS": 100, "WARN": 50, "OPEN": 0, "FAIL": 0}

_DECISION_OPTIONS = {
    "delegation_overrun": [
        "Suspendre l'action autonome concernée",
        "Ramener la délégation au niveau autorisé avec contrôle humain",
        "Réexaminer formellement la délégation après analyse de risque",
    ],
    "functional_overlap": [
        "Mutualiser les usages sur une solution commune",
        "Différencier explicitement les périmètres",
        "Arrêter un usage après comparaison de l'adoption et du coût complet",
    ],
    "time_without_budget_savings": [
        "Redéployer le temps libéré vers une activité prioritaire",
        "Mesurer le bénéfice opérationnel avant toute valorisation",
        "Ne déclarer aucune économie budgétaire",
    ],
    "low_adoption": [
        "Cibler un plan d'accompagnement",
        "Renégocier le périmètre de licences",
        "Arrêter l'usage si la valeur reste non démontrée",
    ],
    "unqualified_usage": [
        "Suspendre l'usage hors périmètre contrôlé",
        "Limiter l'usage à un bac à sable",
        "Qualifier le fournisseur, le modèle et les données avant décision",
    ],
    "data_incompleteness": [
        "Corriger les données à la source",
        "Limiter l'analyse au périmètre fiable",
        "Reporter la décision tant que le seuil de qualité n'est pas atteint",
    ],
    "citation_quality": [
        "Renforcer le contrôle des citations",
        "Restreindre l'usage aux réponses vérifiables",
        "Définir un seuil qualité et suivre les écarts",
    ],
    "qualification_incomplete": [
        "Maintenir la décision en attente",
        "Obtenir l'avis du responsable compétent",
        "Limiter temporairement le périmètre d'usage",
    ],
}


def inspect_atlas_v3_payload(payload: dict[str, object]) -> dict[str, object]:
    """Contrôle le contrat avant import et mesure sa traçabilité."""
    errors: list[str] = []
    warnings: list[str] = []
    if payload.get("schema_version") != "flow-atlas-import-v3":
        errors.append("Le contrat doit utiliser le schéma flow-atlas-import-v3.")
    sheets = payload.get("sheets")
    if not isinstance(sheets, dict):
        return _inspection_result(
            payload, errors + ["Les feuilles Atlas sont absentes."], warnings
        )

    for sheet_name, id_field in _REQUIRED_SHEETS.items():
        rows = _safe_rows(sheets, sheet_name, errors)
        if rows is None:
            continue
        identifiers = [str(row.get(id_field, "")).strip() for row in rows]
        if any(not identifier for identifier in identifiers):
            errors.append(f"{sheet_name} contient un identifiant vide ({id_field}).")
        seen: set[str] = set()
        duplicates: set[str] = set()
        for identifier in identifiers:
            if identifier in seen:
                duplicates.add(identifier)
            seen.add(identifier)
        if duplicates:
            errors.append(
                f"{sheet_name} contient des identifiants dupliqués : "
                + ", ".join(sorted(duplicates)[:5])
                + "."
            )

    if errors:
        return _inspection_result(payload, errors, warnings)

    objects = _rows(sheets, "Atlas Objects")
    relations = _rows(sheets, "Atlas Relations")
    findings = _rows(sheets, "Atlas Findings")
    evidence = _rows(sheets, "Atlas Evidence")
    object_ids = {str(row["object_id"]) for row in objects}
    evidence_by_id = {str(row["evidence_id"]): row for row in evidence}

    for relation in relations:
        source = str(relation.get("source_object_id", ""))
        target = str(relation.get("target_object_id", ""))
        if source not in object_ids or target not in object_ids:
            errors.append(
                f"La relation {relation.get('relation_id')} référence un objet absent."
            )

    traceable_findings = 0
    for finding in findings:
        ids = _ids(finding.get("evidence_ids"))
        resolved = [evidence_by_id[item] for item in ids if item in evidence_by_id]
        if resolved:
            traceable_findings += 1
        else:
            errors.append(
                f"Le constat {finding.get('finding_id')} ne possède aucune preuve résolue."
            )

    source_evidence = [
        row for row in evidence if row.get("evidence_type") == "source_cell"
    ]
    localized_source_evidence = [
        row
        for row in source_evidence
        if row.get("file") and row.get("sheet") and row.get("cell") and row.get("locator")
    ]
    if source_evidence and len(localized_source_evidence) != len(source_evidence):
        warnings.append("Certaines preuves source ne sont pas localisées jusqu'à la cellule.")

    unresolved_evidence_ids = sorted(
        {
            evidence_id
            for sheet_name in (
                "Atlas Objects",
                "Atlas Relations",
                "Atlas Measures",
                "Atlas Findings",
            )
            for row in _rows(sheets, sheet_name)
            for evidence_id in _ids(row.get("evidence_ids"))
            if evidence_id not in evidence_by_id
        }
    )
    if unresolved_evidence_ids:
        errors.append(
            "Des références de preuve sont introuvables : "
            + ", ".join(unresolved_evidence_ids[:10])
            + "."
        )

    summary = summarize_atlas_v3(payload)
    return {
        "schema_version": "flow-atlas-bridge-inspection-v1",
        "can_import": not errors,
        "errors": errors,
        "warnings": warnings,
        "semantic_fingerprint": semantic_fingerprint(payload),
        "counts": {
            "objects": len(objects),
            "relations": len(relations),
            "measures": len(_rows(sheets, "Atlas Measures")),
            "findings": len(findings),
            "evidence": len(evidence),
            "questions": len(_rows(sheets, "Atlas Questions")),
            "controls": len(_rows(sheets, "Import Control")),
        },
        "traceability": {
            "findings_with_evidence": traceable_findings,
            "finding_count": len(findings),
            "finding_rate_percent": _percent(traceable_findings, len(findings)),
            "localized_source_evidence": len(localized_source_evidence),
            "source_evidence_count": len(source_evidence),
            "source_localization_rate_percent": _percent(
                len(localized_source_evidence), len(source_evidence)
            ),
        },
        "decision_state": {
            "status": summary["status"],
            "atlas_load_status": summary["atlas_load_status"],
            "open_blocking_question_count": summary[
                "open_blocking_question_count"
            ],
            "automatic_finalization": False,
            "human_approval_required": True,
        },
    }


def build_atlas_workspace(payload: dict[str, object]) -> dict[str, object]:
    """Projette un contrat valide dans un espace de consultation Atlas."""
    inspection = inspect_atlas_v3_payload(payload)
    if not inspection["can_import"]:
        raise AtlasBridgeError("Import Atlas refusé : " + " ".join(inspection["errors"]))
    payload_copy = copy.deepcopy(payload)
    sheets = payload_copy["sheets"]
    summary = summarize_atlas_v3(payload_copy)
    controls = _rows(sheets, "Import Control")
    findings = _rows(sheets, "Atlas Findings")
    evidence_by_id = {
        str(row["evidence_id"]): row for row in _rows(sheets, "Atlas Evidence")
    }
    scorecard = _scorecard(controls, summary)
    enriched_findings = [_enrich_finding(row, evidence_by_id) for row in findings]
    measures = _rows(sheets, "Atlas Measures")
    return {
        "schema_version": "flow-atlas-workspace-v1",
        "workspace_status": summary["atlas_load_status"],
        "status": summary["atlas_load_status"],
        "publication_status": (
            "BLOCKED"
            if summary["open_blocking_question_count"]
            else "AWAITING_HUMAN_APPROVAL"
        ),
        "published": False,
        "finalized": False,
        "human_approval_required": True,
        "automatic_finalization": False,
        "source": {
            "dataset": payload_copy.get("dataset", {}),
            "semantic_fingerprint": inspection["semantic_fingerprint"],
            "inspection": inspection,
        },
        "cockpit": {
            "scorecard": scorecard,
            "counts": inspection["counts"],
            "traceability": inspection["traceability"],
            "value": _value_summary(measures),
            "top_findings": enriched_findings,
        },
        "maps": _map_index(payload_copy),
        "payload": payload_copy,
    }


def stage_atlas_workspace(
    payload: dict[str, object],
    workspace_directory: str | Path,
    *,
    imported_by: str,
    imported_at: str | None = None,
) -> dict[str, object]:
    """Charge réellement un instantané versionné et rend cet état actif."""
    if not imported_by.strip():
        raise AtlasBridgeError("L'acteur de l'import Atlas est obligatoire.")
    workspace = build_atlas_workspace(payload)
    timestamp = imported_at or _now()
    fingerprint = str(workspace["source"]["semantic_fingerprint"])
    import_id = f"ATLAS-{fingerprint[:12].upper()}"
    workspace["import"] = {
        "import_id": import_id,
        "imported_by": imported_by.strip(),
        "imported_at": timestamp,
        "mode": "transactional_staging",
    }

    root = Path(workspace_directory)
    versions = root / "versions"
    events = root / "events.ndjson"
    versions.mkdir(parents=True, exist_ok=True)
    snapshot = versions / f"{import_id}.json"
    _atomic_json(snapshot, workspace)

    active = root / "active.json"
    previous_import_id = None
    if active.is_file():
        try:
            previous = json.loads(active.read_text(encoding="utf-8"))
            previous_import_id = previous.get("import", {}).get("import_id")
        except (json.JSONDecodeError, OSError):
            previous_import_id = None
    _atomic_json(active, workspace)
    event = {
        "occurred_at": timestamp,
        "actor": imported_by.strip(),
        "action": "atlas_workspace_staged",
        "import_id": import_id,
        "previous_import_id": previous_import_id,
        "status": workspace["workspace_status"],
        "published": False,
        "semantic_fingerprint": fingerprint,
    }
    with events.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "workspace": workspace,
        "paths": {
            "active": str(active.resolve()),
            "snapshot": str(snapshot.resolve()),
            "events": str(events.resolve()),
        },
    }


def rollback_atlas_workspace(
    workspace_directory: str | Path,
    *,
    import_id: str,
    rolled_back_by: str,
    rolled_back_at: str | None = None,
) -> dict[str, object]:
    """Réactive une version existante sans supprimer l'historique."""
    if not re.fullmatch(r"ATLAS-[A-F0-9]{12}", import_id):
        raise AtlasBridgeError("Identifiant d'import Atlas invalide.")
    if not rolled_back_by.strip():
        raise AtlasBridgeError("L'acteur du retour arrière est obligatoire.")
    root = Path(workspace_directory)
    snapshot = root / "versions" / f"{import_id}.json"
    if not snapshot.is_file():
        raise AtlasBridgeError(f"Version Atlas introuvable : {import_id}")
    workspace = json.loads(snapshot.read_text(encoding="utf-8"))
    active = root / "active.json"
    _atomic_json(active, workspace)
    timestamp = rolled_back_at or _now()
    with (root / "events.ndjson").open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "occurred_at": timestamp,
                    "actor": rolled_back_by.strip(),
                    "action": "atlas_workspace_rollback",
                    "import_id": import_id,
                    "published": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
    return workspace


def semantic_fingerprint(payload: dict[str, object]) -> str:
    """Empreinte stable excluant uniquement les horodatages d'exécution."""
    canonical = _without_volatile_fields(payload)
    rendered = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def information_answer(
    payload: dict[str, object], *, target_object_id: str, question: str
) -> dict[str, object]:
    """Répond uniquement quand une preuve explicite couvre l'objet demandé."""
    sheets = payload.get("sheets")
    if not isinstance(sheets, dict):
        raise AtlasBridgeError("Les feuilles Atlas sont absentes.")
    findings = [
        row
        for row in _rows(sheets, "Atlas Findings")
        if target_object_id in _ids(row.get("object_ids"))
    ]
    evidence_by_id = {
        str(row["evidence_id"]): row for row in _rows(sheets, "Atlas Evidence")
    }
    resolved = [
        evidence_by_id[evidence_id]
        for finding in findings
        for evidence_id in _ids(finding.get("evidence_ids"))
        if evidence_id in evidence_by_id
    ]
    pending = any(
        row.get("target_object_id") == target_object_id
        and row.get("status") != "Validated"
        for row in _rows(sheets, "Atlas Questions")
    )
    if not findings or not resolved or pending:
        return {
            "question": question,
            "target_object_id": target_object_id,
            "answer": "Information insuffisante",
            "decision_allowed": False,
            "reason": "Une qualification ou une validation humaine reste nécessaire.",
            "evidence": resolved,
        }
    return {
        "question": question,
        "target_object_id": target_object_id,
        "answer": "Constat disponible, sans décision automatique.",
        "decision_allowed": False,
        "findings": [_enrich_finding(row, evidence_by_id) for row in findings],
        "evidence": resolved,
    }


def _scorecard(
    controls: list[dict[str, object]], summary: dict[str, object]
) -> dict[str, object]:
    dimensions: dict[str, dict[str, object]] = {}
    for name, rule_ids in _SCORE_RULES.items():
        selected = [row for row in controls if row.get("rule_id") in rule_ids]
        score = (
            round(
                sum(_STATUS_POINTS.get(str(row.get("status")), 0) for row in selected)
                / len(selected)
            )
            if selected
            else None
        )
        dimensions[name] = {
            "score": score,
            "control_count": len(selected),
            "method": "PASS=100, WARN=50, OPEN ou FAIL=0; moyenne des contrôles documentés.",
        }
    available = [
        int(item["score"])
        for item in dimensions.values()
        if item["score"] is not None
    ]
    overall = min(available) if available else None
    blocking = int(summary["open_blocking_question_count"])
    if overall is None:
        verdict = "Information insuffisante"
    elif blocking:
        verdict = "Décision bloquée"
    elif overall >= 80:
        verdict = "Alignement robuste"
    elif overall >= 60:
        verdict = "Alignement à renforcer"
    elif overall >= 40:
        verdict = "Alignement fragile"
    else:
        verdict = "Alignement critique"
    return {
        "overall": overall,
        "verdict": verdict,
        "dimensions": dimensions,
        "method": "Le score global est le plus faible sous-score disponible; il reste bloqué tant qu'une question bloquante est ouverte.",
        "bounded_0_100": overall is None or 0 <= overall <= 100,
    }


def _value_summary(measures: list[dict[str, object]]) -> dict[str, object]:
    wanted = {
        "time": "time_released_hours_per_month",
        "budget_saving": "budget_savings_eur_per_month",
        "cost": "cost_eur_per_month",
        "avoided_loss": "avoided_loss_eur_per_month",
        "attributed_revenue": "attributed_revenue_eur_per_month",
    }
    totals = {value: 0.0 for value in wanted.values()}
    evidence = {value: [] for value in wanted.values()}
    for row in measures:
        output = wanted.get(str(row.get("measure_type", "")))
        if output is None:
            continue
        number = _number(row.get("value"))
        if number is None:
            continue
        totals[output] += number
        evidence[output].extend(_ids(row.get("evidence_ids")))
    return {
        **{key: _clean_number(value) for key, value in totals.items()},
        "separation_rule": "Le temps libéré n'est jamais converti automatiquement en économie budgétaire.",
        "evidence_ids": {
            key: sorted(set(value)) for key, value in evidence.items()
        },
    }


def _enrich_finding(
    finding: dict[str, object], evidence_by_id: dict[str, dict[str, object]]
) -> dict[str, object]:
    evidence = [
        evidence_by_id[item]
        for item in _ids(finding.get("evidence_ids"))
        if item in evidence_by_id
    ]
    confidence_label = str(finding.get("confidence") or "inconnue")
    confidence_score = {"élevée": 0.9, "moyenne": 0.65, "faible": 0.35}.get(
        confidence_label, 0.0
    )
    return {
        **copy.deepcopy(finding),
        "statement_kind": "déduction",
        "confidence_label": confidence_label,
        "confidence_score": confidence_score,
        "proof_status": "sourcé" if evidence else "information insuffisante",
        "evidence": evidence,
        "decision_options": _DECISION_OPTIONS.get(
            str(finding.get("finding_type", "")),
            [
                "Conserver le point ouvert",
                "Demander une preuve complémentaire",
                "Faire arbitrer par le responsable compétent",
            ],
        ),
        "selected_option": None,
        "human_decision_required": True,
    }


def _map_index(payload: dict[str, object]) -> list[dict[str, object]]:
    sheets = payload["sheets"]
    findings = _rows(sheets, "Atlas Findings")
    titles = {
        "human_work": "Le travail humain",
        "decisions_responsibilities": "Les décisions et responsabilités",
        "knowledge_data": "Les connaissances et données",
        "tools_dependencies": "Les outils et dépendances",
        "actual_ai_use": "L'usage réel de l'IA",
        "value_cost": "La valeur et le coût",
        "transformation_opportunities": "Les possibilités de transformation",
    }
    return [
        {
            "map_id": map_id,
            "title": title,
            "finding_count": sum(row.get("map_id") == map_id for row in findings),
        }
        for map_id, title in titles.items()
    ]


def _inspection_result(
    payload: dict[str, object], errors: list[str], warnings: list[str]
) -> dict[str, object]:
    return {
        "schema_version": "flow-atlas-bridge-inspection-v1",
        "can_import": False,
        "errors": errors,
        "warnings": warnings,
        "semantic_fingerprint": semantic_fingerprint(payload),
        "counts": {},
        "traceability": {},
        "decision_state": {
            "automatic_finalization": False,
            "human_approval_required": True,
        },
    }


def _safe_rows(
    sheets: dict[str, Any], sheet_name: str, errors: list[str]
) -> list[dict[str, object]] | None:
    sheet = sheets.get(sheet_name)
    if not isinstance(sheet, dict) or not isinstance(sheet.get("rows"), list):
        errors.append(f"Feuille obligatoire absente : {sheet_name}.")
        return None
    if not all(isinstance(row, dict) for row in sheet["rows"]):
        errors.append(f"La feuille {sheet_name} contient une ligne invalide.")
        return None
    return sheet["rows"]


def _rows(sheets: dict[str, Any], sheet_name: str) -> list[dict[str, object]]:
    sheet = sheets.get(sheet_name)
    if not isinstance(sheet, dict) or not isinstance(sheet.get("rows"), list):
        raise AtlasBridgeError(f"Feuille Atlas absente : {sheet_name}")
    return sheet["rows"]


def _ids(value: object) -> list[str]:
    return [item for item in str(value or "").split(";") if item]


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _clean_number(value: float) -> int | float:
    return int(value) if value.is_integer() else round(value, 2)


def _percent(numerator: int, denominator: int) -> int:
    return round(100 * numerator / denominator) if denominator else 0


def _without_volatile_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_volatile_fields(item)
            for key, item in value.items()
            if key
            not in {"checked_at", "captured_at", "answered_at", "validated_at"}
        }
    if isinstance(value, list):
        return [_without_volatile_fields(item) for item in value]
    return value


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
