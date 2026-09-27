"""Scénario reproductible Flow Scout Winner pour le jury et les pilotes client."""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.flow_scout.atlas_bridge import (
    build_atlas_workspace,
    information_answer,
    inspect_atlas_v3_payload,
    semantic_fingerprint,
    stage_atlas_workspace,
)
from app.flow_scout.atlas_v3_lifecycle import (
    answer_atlas_v3_question,
    summarize_atlas_v3,
    validate_atlas_v3_question,
)
from app.flow_scout.nexus_xlsx import export_nexus_v3_xlsx
from app.flow_scout.operator import build_agent_preview
from app.flow_scout.xia_quality_gate import evaluate_xia_readiness


class WinnerDemoError(ValueError):
    """Le scénario de démonstration ne peut pas être exécuté."""


def run_winner_demo(
    source_file: str | Path,
    *,
    output_directory: str | Path | None = None,
    replay_count: int = 5,
) -> dict[str, object]:
    """Rejoue le scénario assureur, l'évalue et charge un espace Atlas."""
    if replay_count < 1:
        raise WinnerDemoError("Le nombre de relectures doit être supérieur à zéro.")
    started = time.perf_counter()
    source = Path(source_file)
    previews = [build_agent_preview(source) for _ in range(replay_count)]
    semantic_fingerprints = [
        semantic_fingerprint(item["atlas_payload"]) for item in previews
    ]
    preview = previews[0]
    initial_payload = preview["atlas_payload"]
    initial_inspection = inspect_atlas_v3_payload(initial_payload)

    ai_002_question = _question(initial_payload, "R-004", "AI-002")
    act_012_question = _question(initial_payload, "R-008", "ACT-012")

    ambiguous_payload = answer_atlas_v3_question(
        initial_payload,
        question_id=str(ai_002_question["question_id"]),
        answer={"observation": "Nous allons regarder ce point."},
        answered_by="Responsable sinistres",
        evidence_note="Réponse insuffisamment précise pour modifier la délégation.",
        answered_at="2026-09-25T09:02:00Z",
    )
    ambiguous_summary = summarize_atlas_v3(ambiguous_payload)
    ambiguous_control = _control(
        ambiguous_payload, str(ai_002_question["question_id"])
    )

    answered_ai_002 = answer_atlas_v3_question(
        ambiguous_payload,
        question_id=str(ai_002_question["question_id"]),
        answer={
            "observed_level": 2,
            "human_control": "Validation obligatoire avant paiement",
        },
        answered_by="Responsable sinistres",
        evidence_note="Le périmètre autonome est ramené à D2.",
        answered_at="2026-09-25T09:03:00Z",
    )
    validated_ai_002 = validate_atlas_v3_question(
        answered_ai_002,
        question_id=str(ai_002_question["question_id"]),
        validator="Responsable contrôle interne",
        accepted=True,
        resolution_confirmed=True,
        validation_note="Le périmètre D4 a été retiré et le contrôle humain rétabli.",
        validated_at="2026-09-25T09:04:00Z",
    )

    answered_act_012 = answer_atlas_v3_question(
        validated_ai_002,
        question_id=str(act_012_question["question_id"]),
        answer={
            "current_skills": "Instruction de sinistre",
            "required_skills": "Contrôle d'une proposition IA et maîtrise des règles de délégation",
            "gap": "Moyen",
            "development_action": "Atelier de validation des paiements assistés",
        },
        answered_by="Responsable métier",
        evidence_note="Écart et action de développement confirmés par le métier.",
        answered_at="2026-09-25T09:04:20Z",
    )
    final_payload = validate_atlas_v3_question(
        answered_act_012,
        question_id=str(act_012_question["question_id"]),
        validator="Responsable formation",
        accepted=True,
        resolution_confirmed=True,
        validation_note="L'atelier de validation est inscrit au plan d'action.",
        validated_at="2026-09-25T09:04:40Z",
    )
    final_summary = summarize_atlas_v3(final_payload)
    final_workspace = build_atlas_workspace(final_payload)
    insufficient = information_answer(
        final_payload,
        target_object_id="AI-008",
        question="AI-008 peut-elle être considérée comme conforme ?",
    )

    findings = preview["report"]["findings"]
    ai_002_finding = next(
        (
            row
            for row in findings
            if row.get("type") == "delegation_overrun"
            and "AI-002" in row.get("objects", [])
        ),
        None,
    )
    value_finding = next(
        (row for row in findings if row.get("type") == "time_without_budget_savings"),
        None,
    )
    final_ai_control = _control(final_payload, str(ai_002_question["question_id"]))
    final_skill_control = _control(final_payload, str(act_012_question["question_id"]))
    final_delegation = _measure(
        final_payload, "AI-002", "Délégation observée"
    )
    act_012_row = next(
        row
        for row in final_payload["sheets"]["Tasks_Roles_Skills"]["rows"]
        if row.get("task_id") == "ACT-012"
    )
    scorecard = final_workspace["cockpit"]["scorecard"]

    checks = [
        _check(
            "replay_consistency",
            len(set(semantic_fingerprints)) == 1,
            f"{replay_count} exécutions, {len(set(semantic_fingerprints))} empreinte sémantique",
        ),
        _check(
            "ai_002_detected",
            ai_002_finding is not None,
            "Dépassement de délégation AI-002 détecté",
        ),
        _check(
            "act_012_skill_gap",
            bool(act_012_row.get("niveau_ecart"))
            and final_skill_control.get("status") == "PASS",
            "Écart de compétences ACT-012 qualifié et validé",
        ),
        _check(
            "time_budget_separated",
            bool(value_finding)
            and value_finding.get("measures", {}).get("hours_released", 0) > 0
            and value_finding.get("measures", {}).get("budget_savings_eur") == 0,
            "Temps libéré et économie budgétaire restent distincts",
        ),
        _check(
            "cell_traceability",
            bool(ai_002_finding)
            and all(
                item.get("file") and item.get("sheet") and item.get("cell")
                for item in ai_002_finding.get("evidence", [])
            ),
            "Chaque preuve AI-002 remonte au fichier, à la feuille et à la cellule",
        ),
        _check(
            "ambiguous_answer_stays_blocked",
            ambiguous_control.get("status") != "PASS"
            and ambiguous_summary["atlas_load_status"] == "STAGED_BLOCKED",
            "La réponse ambiguë ne débloque pas le contrôle",
        ),
        _check(
            "human_validation_recalculates",
            final_ai_control.get("status") == "PASS"
            and final_delegation.get("value") == 2,
            "La validation humaine confirmée recalcule AI-002",
        ),
        _check(
            "insufficient_information_refusal",
            insufficient["answer"] == "Information insuffisante"
            and insufficient["decision_allowed"] is False,
            "AI-008 reste sans conclusion automatique",
        ),
        _check(
            "all_findings_sourced",
            initial_inspection.get("traceability", {}).get(
                "finding_rate_percent"
            )
            == 100,
            "100 % des constats sont reliés à une preuve",
        ),
        _check(
            "scores_bounded",
            scorecard.get("bounded_0_100") is True
            and all(
                item.get("score") is None or 0 <= item["score"] <= 100
                for item in scorecard.get("dimensions", {}).values()
            ),
            "Tous les scores disponibles restent entre 0 et 100",
        ),
        _check(
            "no_automatic_finalization",
            final_workspace["published"] is False
            and final_workspace["human_approval_required"] is True,
            "Aucune publication ni décision bloquante automatique",
        ),
        _check(
            "atlas_bridge_loaded",
            final_workspace["schema_version"] == "flow-atlas-workspace-v1"
            and len(final_workspace["maps"]) == 7,
            "Le paquet v3 alimente un espace Atlas à sept cartes",
        ),
    ]

    elapsed_seconds = round(time.perf_counter() - started, 3)
    checks.append(
        _check(
            "execution_under_five_minutes",
            elapsed_seconds < 300,
            f"Exécution technique en {elapsed_seconds} seconde(s)",
        )
    )
    passed = sum(item["passed"] for item in checks)
    evaluation = {
        "schema_version": "flow-scout-winner-evaluation-v1",
        "passed": passed == len(checks),
        "passed_checks": passed,
        "check_count": len(checks),
        "success_rate_percent": round(100 * passed / len(checks)),
        "checks": checks,
        "replay_count": replay_count,
        "semantic_fingerprints": semantic_fingerprints,
        "elapsed_seconds": elapsed_seconds,
        "zero_spend_mode": True,
        "external_service_calls": 0,
    }
    timeline = _timeline(
        ai_002_finding=ai_002_finding or {},
        ambiguous_control=ambiguous_control,
        final_ai_control=final_ai_control,
        final_skill_control=final_skill_control,
        workspace=final_workspace,
    )
    result = {
        "schema_version": "flow-scout-winner-demo-v1",
        "run_id": preview["run_id"],
        "source": preview["source"],
        "promise": (
            "Transformer un dossier client hétérogène en carte de gouvernance "
            "sourcée, questionner le bon responsable et alimenter Atlas sans "
            "décision automatique."
        ),
        "timeline": timeline,
        "initial_summary": preview["summary"],
        "ambiguous_answer_result": {
            "question_id": ai_002_question["question_id"],
            "control_status": ambiguous_control.get("status"),
            "atlas_load_status": ambiguous_summary["atlas_load_status"],
        },
        "final_summary": final_summary,
        "information_insufficient_example": insufficient,
        "atlas_workspace": final_workspace,
        "evaluation": evaluation,
        "artifacts": {},
    }

    project_root = Path(__file__).resolve().parents[3]
    result["xia_readiness"] = evaluate_xia_readiness(
        result, project_root=project_root
    )

    if output_directory is not None:
        artifacts = _write_artifacts(
            result=result,
            final_payload=final_payload,
            timeline=timeline,
            evaluation=evaluation,
            output_directory=Path(output_directory),
        )
        result["artifacts"] = artifacts
    return result


def _write_artifacts(
    *,
    result: dict[str, object],
    final_payload: dict[str, object],
    timeline: list[dict[str, object]],
    evaluation: dict[str, object],
    output_directory: Path,
) -> dict[str, str]:
    output_directory.mkdir(parents=True, exist_ok=True)
    atlas_result = stage_atlas_workspace(
        final_payload,
        output_directory / "atlas-workspace",
        imported_by="Flow Scout Winner Demo",
        imported_at="2026-09-25T09:04:50Z",
    )
    payload_path = output_directory / "flow-atlas-v3-validated.json"
    workbook_path = output_directory / "flow-atlas-v3-validated.xlsx"
    timeline_path = output_directory / "replay-events.ndjson"
    evaluation_path = output_directory / "evaluation-scorecard.json"
    xia_readiness_path = output_directory / "xia-readiness-scorecard.json"
    result_path = output_directory / "winner-demo-result.json"
    payload_path.write_text(_json(final_payload), encoding="utf-8")
    workbook_path.write_bytes(export_nexus_v3_xlsx(final_payload))
    timeline_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in timeline),
        encoding="utf-8",
    )
    evaluation_path.write_text(_json(evaluation), encoding="utf-8")
    xia_readiness_path.write_text(_json(result["xia_readiness"]), encoding="utf-8")
    artifacts = {
        "result": str(result_path.resolve()),
        "evaluation": str(evaluation_path.resolve()),
        "xia_readiness": str(xia_readiness_path.resolve()),
        "timeline": str(timeline_path.resolve()),
        "atlas_payload": str(payload_path.resolve()),
        "atlas_workbook": str(workbook_path.resolve()),
        "atlas_active_workspace": atlas_result["paths"]["active"],
        "atlas_snapshot": atlas_result["paths"]["snapshot"],
        "atlas_events": atlas_result["paths"]["events"],
    }
    public_result = {**result, "artifacts": artifacts}
    result_path.write_text(_json(public_result), encoding="utf-8")
    return artifacts


def _timeline(
    *,
    ai_002_finding: dict[str, object],
    ambiguous_control: dict[str, object],
    final_ai_control: dict[str, object],
    final_skill_control: dict[str, object],
    workspace: dict[str, object],
) -> list[dict[str, object]]:
    return [
        _step(0, "Dépôt client", "Le dossier assureur est détecté.", "fact"),
        _step(15, "Reconnaissance", "Les sources et leur provenance sont contrôlées.", "fact"),
        _step(35, "Cartographie", "Les sept cartes Flow Scout sont construites.", "deduction"),
        _step(
            65,
            "Paiement sans validation humaine",
            str(ai_002_finding.get("statement", "Dépassement détecté")),
            "deduction",
            evidence=ai_002_finding.get("evidence", []),
        ),
        _step(100, "Maïeutique", "L'agent demande de confirmer qu'une personne doit autoriser chaque paiement.", "question"),
        _step(135, "Réponse ambiguë", "La réponse ne contient aucune remédiation vérifiable.", "human_declaration"),
        _step(
            155,
            "Blocage maintenu",
            f"Le contrôle reste {ambiguous_control.get('status')}; Atlas reste bloqué.",
            "control",
        ),
        _step(185, "Validation humaine", "L'IA prépare le paiement ; une personne doit le vérifier et l'autoriser.", "human_validation"),
        _step(
            210,
            "Recalcul AI-002",
            f"Le contrôle passe à {final_ai_control.get('status')}.",
            "control",
        ),
        _step(
            235,
            "Compétences ACT-012",
            f"L'écart est qualifié; contrôle {final_skill_control.get('status')}.",
            "human_validation",
        ),
        _step(260, "Valeur", "Le temps libéré reste séparé de l'économie budgétaire.", "fact"),
        _step(
            280,
            "Atlas Bridge",
            f"L'espace Atlas est chargé en statut {workspace.get('workspace_status')}.",
            "control",
        ),
    ]


def _step(
    second: int,
    title: str,
    message: str,
    kind: str,
    *,
    evidence: object | None = None,
) -> dict[str, object]:
    return {
        "at_second": second,
        "title": title,
        "message": message,
        "statement_kind": kind,
        "evidence": evidence or [],
    }


def _question(
    payload: dict[str, object], rule_id: str, target_object_id: str
) -> dict[str, object]:
    question = next(
        (
            row
            for row in payload["sheets"]["Atlas Questions"]["rows"]
            if row.get("rule_id") == rule_id
            and row.get("target_object_id") == target_object_id
        ),
        None,
    )
    if question is None:
        raise WinnerDemoError(
            f"Question de démonstration absente : {rule_id}/{target_object_id}."
        )
    return question


def _control(payload: dict[str, object], question_id: str) -> dict[str, object]:
    control = next(
        (
            row
            for row in payload["sheets"]["Import Control"]["rows"]
            if row.get("question_id") == question_id
        ),
        None,
    )
    if control is None:
        raise WinnerDemoError(f"Contrôle absent pour la question {question_id}.")
    return control


def _measure(
    payload: dict[str, object], object_id: str, name: str
) -> dict[str, object]:
    measure = next(
        (
            row
            for row in payload["sheets"]["Atlas Measures"]["rows"]
            if row.get("object_id") == object_id and row.get("name") == name
        ),
        None,
    )
    if measure is None:
        raise WinnerDemoError(f"Mesure absente : {object_id}/{name}.")
    return measure


def _check(check_id: str, passed: bool, detail: str) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "detail": detail}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
