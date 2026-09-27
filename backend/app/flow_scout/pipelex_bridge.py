"""Contrat local entre Flow Scout et une relecture optionnelle Pipelex.

Ce module ne fait aucun appel reseau. Il produit un paquet minimise a partir des
resultats deterministes de Flow Scout et controle qu'une reponse externe ne cite
ni objet ni preuve absents du paquet source.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PipelexBridgeError(ValueError):
    """Le paquet ou la reponse Pipelex ne respecte pas le contrat Flow Scout."""


def build_pipelex_packet(preview: dict[str, object]) -> dict[str, object]:
    """Minimise une preview Flow Scout pour la relecture maieutique."""
    if preview.get("schema_version") != "flow-scout-operator-preview-v1":
        raise PipelexBridgeError("La preview Flow Scout n'est pas reconnue.")
    source = _mapping(preview.get("source"), "source")
    summary = _mapping(preview.get("summary"), "summary")
    report = _mapping(preview.get("report"), "report")

    findings = [
        _finding(item)
        for item in _rows(report.get("findings"), "report.findings")
    ]
    questions = [
        _question(item)
        for item in _rows(summary.get("questions"), "summary.questions")
    ]
    questions.sort(
        key=lambda item: (
            0 if item.get("priority") == "P0" else 1,
            str(item.get("question_id", "")),
        )
    )
    questions = questions[:3]
    source_role = str(source.get("role", ""))
    return {
        "schema_version": "flow-scout-pipelex-packet-v1",
        "purpose": "Explication factuelle et questions maieutiques sous supervision humaine",
        "source": {
            "name": str(source.get("name", "")),
            "sha256": str(source.get("sha256", "")),
            "role": source_role,
            "synthetic": source_role == "synthetic_demo_collection",
        },
        "policy": {
            "authoritative_engine": "Flow Scout deterministic rules",
            "assistant_role": "explain_and_question_only",
            "forbidden_actions": [
                "invent_missing_information",
                "alter_source_evidence",
                "classify_ai_act_without_evidence",
                "approve_blocking_decision",
                "finalize_atlas_import",
            ],
        },
        "atlas_state": {
            "status": str(summary.get("atlas_load_status", "STAGED_BLOCKED")),
            "human_approval_required": bool(
                summary.get("human_approval_required", True)
            ),
            "open_blocking_question_count": int(
                summary.get("open_blocking_question_count", 0) or 0
            ),
            "control_counts": summary.get("control_counts", {}),
        },
        "findings": findings,
        "questions": questions,
    }


def build_pipelex_inputs(preview: dict[str, object]) -> dict[str, str]:
    """Construit le fichier inputs.json attendu par la methode MTHDS."""
    packet = build_pipelex_packet(preview)
    return {
        "flow_scout_packet": json.dumps(
            packet,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    }


def write_pipelex_inputs(preview: dict[str, object], output: str | Path) -> Path:
    """Ecrit un input Pipelex local sans secret ni appel externe."""
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(build_pipelex_inputs(preview), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return destination


def validate_pipelex_review(
    review: dict[str, object], packet: dict[str, object]
) -> dict[str, object]:
    """Refuse tout ecart au schema ainsi que les references inventees."""
    errors = _contract_errors(review)
    allowed_objects: set[str] = set()
    allowed_evidence: set[str] = set()
    allowed_findings: set[str] = set()
    for finding in _rows(packet.get("findings"), "packet.findings"):
        finding_id = str(finding.get("finding_id", "")).strip()
        if finding_id:
            allowed_findings.add(finding_id)
        allowed_objects.update(_strings(finding.get("objects")))
        for evidence in _rows(finding.get("evidence"), "finding.evidence"):
            locator = str(evidence.get("locator", "")).strip()
            if locator:
                allowed_evidence.add(locator)
    for question in _rows(packet.get("questions"), "packet.questions"):
        target = str(question.get("target_object_id", "")).strip()
        if target:
            allowed_objects.add(target)
        allowed_evidence.update(_strings(question.get("evidence_refs")))

    for index, finding in enumerate(_rows(review.get("findings"), "review.findings")):
        _check_values(
            errors,
            f"findings[{index}].finding_id",
            [str(finding.get("finding_id", "")).strip()],
            allowed_findings,
        )
        _check_values(
            errors,
            f"findings[{index}].target_object_ids",
            _strings(finding.get("target_object_ids")),
            allowed_objects,
        )
        _check_values(
            errors,
            f"findings[{index}].evidence_refs",
            _strings(finding.get("evidence_refs")),
            allowed_evidence,
        )
    for index, question in enumerate(_rows(review.get("questions"), "review.questions")):
        _check_values(
            errors,
            f"questions[{index}].target_object_id",
            [str(question.get("target_object_id", "")).strip()],
            allowed_objects,
        )
        _check_values(
            errors,
            f"questions[{index}].evidence_refs",
            _strings(question.get("evidence_refs")),
            allowed_evidence,
        )

    recommendation = str(review.get("atlas_recommendation", ""))
    if recommendation not in {"STAGED_BLOCKED", "READY_FOR_HUMAN_REVIEW"}:
        errors.append(
            "atlas_recommendation: valeur interdite; aucune publication automatique n'est permise"
        )
    return {
        "schema_version": "flow-scout-pipelex-validation-v1",
        "accepted": not errors,
        "error_count": len(errors),
        "errors": errors,
    }


def _contract_errors(review: dict[str, object]) -> list[str]:
    errors: list[str] = []
    _check_exact_keys(
        errors,
        "review",
        review,
        {
            "executive_summary",
            "findings",
            "questions",
            "atlas_recommendation",
            "refused_claims",
            "limitations",
        },
    )
    _check_text(errors, "executive_summary", review.get("executive_summary"))
    _check_text_list(errors, "refused_claims", review.get("refused_claims"))
    _check_text_list(errors, "limitations", review.get("limitations"))

    findings = _rows_for_contract(errors, review.get("findings"), "findings")
    for index, finding in enumerate(findings):
        prefix = f"findings[{index}]"
        _check_exact_keys(
            errors,
            prefix,
            finding,
            {
                "finding_id",
                "target_object_ids",
                "plain_language_title",
                "plain_language_explanation",
                "proposed_action",
                "evidence_refs",
                "confidence",
                "needs_human_validation",
            },
        )
        for field in (
            "finding_id",
            "plain_language_title",
            "plain_language_explanation",
            "proposed_action",
        ):
            _check_text(errors, f"{prefix}.{field}", finding.get(field))
        _check_text_list(
            errors,
            f"{prefix}.target_object_ids",
            finding.get("target_object_ids"),
            require_non_empty=True,
        )
        _check_text_list(
            errors,
            f"{prefix}.evidence_refs",
            finding.get("evidence_refs"),
            require_non_empty=True,
        )
        if finding.get("confidence") not in {
            "elevee",
            "moyenne",
            "faible",
            "information_insuffisante",
        }:
            errors.append(f"{prefix}.confidence: valeur interdite")
        if not isinstance(finding.get("needs_human_validation"), bool):
            errors.append(f"{prefix}.needs_human_validation: booleen requis")

    questions = _rows_for_contract(errors, review.get("questions"), "questions")
    if len(questions) > 3:
        errors.append("questions: trois questions maximum")
    for index, question in enumerate(questions):
        prefix = f"questions[{index}]"
        _check_exact_keys(
            errors,
            prefix,
            question,
            {
                "target_object_id",
                "question",
                "why_asked",
                "decision_blocked",
                "evidence_refs",
            },
        )
        for field in ("target_object_id", "question", "why_asked"):
            _check_text(errors, f"{prefix}.{field}", question.get(field))
        if not isinstance(question.get("decision_blocked"), bool):
            errors.append(f"{prefix}.decision_blocked: booleen requis")
        _check_text_list(
            errors,
            f"{prefix}.evidence_refs",
            question.get("evidence_refs"),
            require_non_empty=True,
        )
    return errors


def _check_exact_keys(
    errors: list[str], name: str, value: dict[str, object], expected: set[str]
) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{name}: champs manquants: {', '.join(missing)}")
    if extra:
        errors.append(f"{name}: champs interdits: {', '.join(extra)}")


def _check_text(errors: list[str], name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{name}: texte non vide requis")


def _check_text_list(
    errors: list[str], name: str, value: object, *, require_non_empty: bool = False
) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        errors.append(f"{name}: liste de textes requise")
    elif require_non_empty and not value:
        errors.append(f"{name}: au moins une reference prouvee est requise")


def _rows_for_contract(
    errors: list[str], value: object, name: str
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        errors.append(f"{name}: liste d'objets requise")
        return []
    return value


def _finding(item: dict[str, Any]) -> dict[str, object]:
    return {
        "finding_id": str(item.get("id", "")),
        "type": str(item.get("type", "")),
        "map_id": str(item.get("map_id", "")),
        "title": str(item.get("title", "")),
        "severity": str(item.get("severity", "")),
        "objects": _strings(item.get("objects")),
        "statement": str(item.get("statement", "")),
        "recommended_action": str(item.get("recommended_action", "")),
        "conditions": _strings(item.get("conditions")),
        "confidence": str(item.get("confidence", "")),
        "evidence": [
            {
                "locator": str(evidence.get("locator", "")),
                "quote": evidence.get("quote"),
            }
            for evidence in _rows(item.get("evidence"), "finding.evidence")
            if str(evidence.get("locator", "")).strip()
        ],
    }


def _question(item: dict[str, Any]) -> dict[str, object]:
    return {
        "question_id": str(item.get("question_id", "")),
        "journey_stage": str(item.get("journey_stage", "")),
        "rule_id": str(item.get("rule_id", "")),
        "map_id": str(item.get("map_id", "")),
        "target_object_id": str(item.get("target_object_id", "")),
        "question": str(item.get("question", "")),
        "why_asked": str(item.get("why_asked", "")),
        "decision_blocked": str(item.get("decision_blocked", "")) == "Oui",
        "priority": str(item.get("priority", "")),
        "evidence_refs": [
            value.strip()
            for value in str(item.get("evidence_ids", "")).split(";")
            if value.strip()
        ],
    }


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipelexBridgeError(f"{name} doit etre un objet.")
    return value


def _rows(value: object, name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise PipelexBridgeError(f"{name} doit etre une liste d'objets.")
    return value


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _check_values(
    errors: list[str], name: str, values: list[str], allowed: set[str]
) -> None:
    unknown = sorted({value for value in values if value and value not in allowed})
    if unknown:
        errors.append(f"{name}: references inconnues: {', '.join(unknown)}")
