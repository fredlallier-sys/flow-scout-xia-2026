"""Cycle de réponse, validation humaine et recalcul du contrat Atlas v3."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from typing import Any


class AtlasV3LifecycleError(ValueError):
    """Le payload ou la transition demandée ne respecte pas le contrat v3."""


def summarize_atlas_v3(payload: dict[str, object]) -> dict[str, object]:
    """Résume l'état décisionnel sans confondre chargement et validation."""
    sheets = _sheets(payload)
    questions = _rows(sheets, "Atlas Questions")
    controls = _rows(sheets, "Import Control")
    rules = {
        str(row.get("rule_id", "")): str(row.get("severity", ""))
        for row in _rows(sheets, "Atlas Rules")
    }
    blocking_questions = [
        row
        for row in questions
        if row.get("decision_blocked") == "Oui"
        and row.get("status") != "Validated"
    ]
    blocking_controls = [
        row
        for row in controls
        if row.get("rule_id") != "R-014"
        and rules.get(str(row.get("rule_id", ""))) == "Bloquant"
        and row.get("status") in {"OPEN", "FAIL"}
    ]
    control_counts = {
        status: sum(row.get("status") == status for row in controls)
        for status in ("PASS", "WARN", "OPEN", "FAIL")
    }
    blocked = bool(blocking_questions or blocking_controls)
    return {
        "schema_version": "flow-scout-agent-summary-v1",
        "status": (
            "AWAITING_HUMAN_VALIDATION"
            if blocked
            else "READY_FOR_ATLAS_HUMAN_APPROVAL"
        ),
        "atlas_load_status": (
            "STAGED_BLOCKED" if blocked else "STAGED_AWAITING_APPROVAL"
        ),
        "automatic_finalization": False,
        "human_approval_required": True,
        "question_count": len(questions),
        "open_blocking_question_count": len(blocking_questions),
        "blocking_control_count": len(blocking_controls),
        "control_counts": control_counts,
        "questions": questions,
        "controls": controls,
    }


def answer_atlas_v3_question(
    payload: dict[str, object],
    *,
    question_id: str,
    answer: object,
    answered_by: str,
    evidence_note: str = "",
    answered_at: str | None = None,
) -> dict[str, object]:
    """Enregistre une réponse déclarée sans valider le contrôle associé."""
    if not answered_by.strip():
        raise AtlasV3LifecycleError("L'auteur de la réponse est obligatoire.")
    rendered_answer = _render_answer(answer)
    if not rendered_answer.strip():
        raise AtlasV3LifecycleError("La réponse ne peut pas être vide.")
    updated = copy.deepcopy(payload)
    sheets = _sheets(updated)
    question = _find_question(sheets, question_id)
    if question.get("status") == "Validated":
        raise AtlasV3LifecycleError("Cette question est déjà validée.")
    timestamp = answered_at or _now()
    question["answer"] = rendered_answer
    question["answered_by"] = answered_by.strip()
    question["answered_at"] = timestamp
    question["status"] = "Answered"
    evidence_id = _append_human_evidence(
        sheets,
        object_id=str(question.get("target_object_id", "")),
        quote=evidence_note.strip() or rendered_answer,
        evidence_type="human_declared_answer",
        captured_at=timestamp,
    )
    question["evidence_ids"] = _append_id(question.get("evidence_ids"), evidence_id)
    for control in _linked_controls(sheets, question_id):
        if control.get("status") != "FAIL":
            control["status"] = "OPEN"
        control["issue"] = "Réponse reçue, validation humaine requise"
        control["evidence_ids"] = _append_id(control.get("evidence_ids"), evidence_id)
    _refresh_global_maieutic_control(sheets)
    return updated


def validate_atlas_v3_question(
    payload: dict[str, object],
    *,
    question_id: str,
    validator: str,
    accepted: bool,
    resolution_confirmed: bool,
    validation_note: str = "",
    validated_at: str | None = None,
) -> dict[str, object]:
    """Valide une réponse et ne passe un contrôle à PASS qu'après résolution."""
    if not validator.strip():
        raise AtlasV3LifecycleError("Le validateur est obligatoire.")
    updated = copy.deepcopy(payload)
    sheets = _sheets(updated)
    question = _find_question(sheets, question_id)
    if question.get("status") != "Answered":
        raise AtlasV3LifecycleError(
            "La question doit recevoir une réponse avant sa validation."
        )
    timestamp = validated_at or _now()
    question["status"] = "Validated" if accepted else "Rejected"
    evidence_id = _append_human_evidence(
        sheets,
        object_id=str(question.get("target_object_id", "")),
        quote=(
            validation_note.strip()
            or (
                f"Réponse validée par {validator.strip()}"
                if accepted
                else f"Réponse rejetée par {validator.strip()}"
            )
        ),
        evidence_type="human_validation",
        captured_at=timestamp,
    )
    question["evidence_ids"] = _append_id(question.get("evidence_ids"), evidence_id)
    if accepted and resolution_confirmed:
        _apply_validated_answer(sheets, question, evidence_id)
    for control in _linked_controls(sheets, question_id):
        control["evidence_ids"] = _append_id(control.get("evidence_ids"), evidence_id)
        if not accepted:
            control["status"] = "FAIL"
            control["issue"] = "Réponse rejetée par le validateur humain"
            control["required_action"] = "Reprendre la question avec le responsable métier"
        elif resolution_confirmed:
            control["status"] = "PASS"
            control["observed"] = f"Résolution confirmée par {validator.strip()}"
            control["issue"] = "Condition traitée et validation humaine tracée"
            control["required_action"] = "Aucune action"
        else:
            control["status"] = "OPEN"
            control["issue"] = "Réponse validée, remédiation non encore confirmée"
            control["required_action"] = "Confirmer l'application de la remédiation"
    _refresh_global_maieutic_control(sheets)
    return updated


def _apply_validated_answer(
    sheets: dict[str, Any], question: dict[str, object], evidence_id: str
) -> None:
    answer = _parse_answer(question.get("answer"))
    target = str(question.get("target_object_id", ""))
    rule_id = str(question.get("rule_id", ""))
    if rule_id == "R-004" and isinstance(answer, dict):
        observed_level = answer.get("observed_level")
        if observed_level is not None:
            for row in _rows(sheets, "Atlas Measures"):
                if (
                    row.get("object_id") == target
                    and row.get("name") == "Délégation observée"
                ):
                    row["value"] = observed_level
                    row["status"] = "confirmed"
                    row["evidence_ids"] = _append_id(
                        row.get("evidence_ids"), evidence_id
                    )
    if rule_id == "R-008" and isinstance(answer, dict):
        for row in _rows(sheets, "Tasks_Roles_Skills"):
            if row.get("task_id") != target:
                continue
            row["competences_actuelles"] = answer.get("current_skills", "")
            row["competences_a_developper"] = answer.get("required_skills", "")
            row["niveau_ecart"] = answer.get("gap", "")
            row["formation_recommandee"] = answer.get("development_action", "")
        for row in _rows(sheets, "Atlas Objects"):
            if row.get("object_id") != target:
                continue
            attributes = _parse_answer(row.get("attributes_json"))
            if not isinstance(attributes, dict):
                attributes = {}
            attributes["skills"] = {
                "current": answer.get("current_skills", ""),
                "required": answer.get("required_skills", ""),
                "gap": answer.get("gap", ""),
                "development_action": answer.get("development_action", ""),
                "source": "human_validated",
            }
            row["attributes_json"] = json.dumps(
                attributes,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            row["evidence_ids"] = _append_id(row.get("evidence_ids"), evidence_id)


def _refresh_global_maieutic_control(sheets: dict[str, Any]) -> None:
    questions = _rows(sheets, "Atlas Questions")
    remaining = sum(
        row.get("decision_blocked") == "Oui"
        and row.get("status") != "Validated"
        for row in questions
    )
    for control in _rows(sheets, "Import Control"):
        if control.get("rule_id") == "R-014" and control.get("target_object_id") == "MAIEUTIC":
            control["status"] = "OPEN" if remaining else "PASS"
            control["observed"] = f"{remaining} questions bloquantes ouvertes"
            control["issue"] = (
                "Qualification incomplète" if remaining else "Qualification complète"
            )
            control["required_action"] = (
                "Répondre et valider les questions bloquantes"
                if remaining
                else "Aucune action"
            )


def _append_human_evidence(
    sheets: dict[str, Any],
    *,
    object_id: str,
    quote: str,
    evidence_type: str,
    captured_at: str,
) -> str:
    rows = _rows(sheets, "Atlas Evidence")
    evidence_id = f"EVID-HUMAN-{len(rows) + 1:05d}"
    rows.append(
        {
            "evidence_id": evidence_id,
            "object_id": object_id,
            "file": "",
            "sheet": "",
            "cell": "",
            "locator": "human://validation",
            "quote": quote,
            "evidence_type": evidence_type,
            "captured_at": captured_at,
        }
    )
    return evidence_id


def _linked_controls(
    sheets: dict[str, Any], question_id: str
) -> list[dict[str, object]]:
    return [
        row
        for row in _rows(sheets, "Import Control")
        if row.get("question_id") == question_id
    ]


def _find_question(
    sheets: dict[str, Any], question_id: str
) -> dict[str, object]:
    question = next(
        (
            row
            for row in _rows(sheets, "Atlas Questions")
            if row.get("question_id") == question_id
        ),
        None,
    )
    if question is None:
        raise AtlasV3LifecycleError(f"Question Atlas inconnue : {question_id}")
    return question


def _sheets(payload: dict[str, object]) -> dict[str, Any]:
    if payload.get("schema_version") != "flow-atlas-import-v3":
        raise AtlasV3LifecycleError("Le payload n'est pas un import Flow Atlas v3.")
    sheets = payload.get("sheets")
    if not isinstance(sheets, dict):
        raise AtlasV3LifecycleError("Les feuilles Atlas v3 sont absentes.")
    return sheets


def _rows(sheets: dict[str, Any], sheet_name: str) -> list[dict[str, object]]:
    sheet = sheets.get(sheet_name)
    if not isinstance(sheet, dict) or not isinstance(sheet.get("rows"), list):
        raise AtlasV3LifecycleError(f"Feuille Atlas v3 absente : {sheet_name}")
    rows = sheet["rows"]
    if not all(isinstance(row, dict) for row in rows):
        raise AtlasV3LifecycleError(
            f"La feuille Atlas v3 {sheet_name} contient une ligne invalide."
        )
    return rows


def _append_id(existing: object, value: str) -> str:
    values = [item for item in str(existing or "").split(";") if item]
    if value not in values:
        values.append(value)
    return ";".join(values)


def _render_answer(answer: object) -> str:
    if isinstance(answer, str):
        return answer
    return json.dumps(
        answer, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _parse_answer(answer: object) -> object:
    if not isinstance(answer, str):
        return answer
    try:
        return json.loads(answer)
    except json.JSONDecodeError:
        return answer


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
