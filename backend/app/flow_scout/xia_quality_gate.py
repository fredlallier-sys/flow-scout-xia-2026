"""Contrôle de préparation X-IA fondé uniquement sur des preuves observables.

Ce module ne prédit pas la note du jury. Il transforme le barème communiqué en
une grille de préparation reproductible et conserve les lacunes au lieu de les
masquer derrière une auto-évaluation optimiste.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

XIA_CRITERIA = (
    ("impact", "Impact et utilité réelle", 0.30),
    ("innovation", "Innovation et originalité", 0.20),
    ("quality", "Qualité de réalisation", 0.20),
    ("ux", "Expérience utilisateur", 0.15),
    ("clarity", "Clarté de la démonstration", 0.15),
)


@dataclass(frozen=True)
class ReadinessCheck:
    check_id: str
    label: str
    evidence: str
    recommendation: str
    test: Callable[[dict[str, object], Path | None], bool]


def evaluate_xia_readiness(
    result: dict[str, object], *, project_root: str | Path | None = None
) -> dict[str, object]:
    """Construit une scorecard de préparation, jamais une note officielle."""
    root = Path(project_root) if project_root is not None else None
    criteria: dict[str, object] = {}
    gaps: list[dict[str, object]] = []
    weighted_total = 0.0

    for criterion_id, label, weight in XIA_CRITERIA:
        checks = _checks()[criterion_id]
        results = []
        for check in checks:
            passed = bool(check.test(result, root))
            item = {
                "check_id": check.check_id,
                "label": check.label,
                "passed": passed,
                "evidence": check.evidence if passed else None,
                "recommendation": None if passed else check.recommendation,
            }
            results.append(item)
            if not passed:
                gaps.append(
                    {
                        "criterion_id": criterion_id,
                        "check_id": check.check_id,
                        "weighted_loss": round(10 * weight / len(checks), 3),
                        "recommendation": check.recommendation,
                    }
                )
        score = round(10 * sum(item["passed"] for item in results) / len(results), 1)
        contribution = round(score * weight, 3)
        weighted_total += contribution
        criteria[criterion_id] = {
            "label": label,
            "weight_percent": round(weight * 100),
            "score_out_of_10": score,
            "weighted_contribution": contribution,
            "checks": results,
        }

    gaps.sort(key=lambda item: (-float(item["weighted_loss"]), str(item["check_id"])))
    return {
        "schema_version": "flow-scout-xia-readiness-v1",
        "status": "READY" if not gaps else "READY_WITH_GAPS",
        "score_out_of_10": round(weighted_total, 2),
        "score_percent": round(weighted_total * 10),
        "is_official_jury_score": False,
        "rubric_status": "official_rules_verified_2026-09-27",
        "criteria": criteria,
        "top_gap": gaps[0] if gaps else None,
        "gaps": gaps,
        "guardrail": (
            "La scorecard mesure la présence de preuves dans le livrable ; "
            "elle ne prédit pas la décision du jury."
        ),
    }


def _check_passed(result: dict[str, object], check_id: str) -> bool:
    evaluation = result.get("evaluation", {})
    if not isinstance(evaluation, dict):
        return False
    checks = evaluation.get("checks", [])
    return any(
        isinstance(item, dict)
        and item.get("check_id") == check_id
        and item.get("passed") is True
        for item in checks
    )


def _exists(root: Path | None, relative: str) -> bool:
    return bool(root and (root / relative).is_file())


def _has_statement_kind(result: dict[str, object], kind: str) -> bool:
    timeline = result.get("timeline", [])
    return any(
        isinstance(item, dict) and item.get("statement_kind") == kind
        for item in timeline
    )


def _checks() -> dict[str, tuple[ReadinessCheck, ...]]:
    return {
        "impact": (
            ReadinessCheck(
                "business_risk_detected",
                "Un risque métier concret est détecté",
                "Le scénario retrouve l'écart de délégation AI-002.",
                "Ajouter un risque métier démontré et relié à une preuve.",
                lambda r, _p: _check_passed(r, "ai_002_detected"),
            ),
            ReadinessCheck(
                "human_capability_aligned",
                "L'alignement des compétences est contrôlé",
                "ACT-012 relie activité, compétence et action de développement.",
                "Montrer un écart de compétences et sa remédiation.",
                lambda r, _p: _check_passed(r, "act_012_skill_gap"),
            ),
            ReadinessCheck(
                "value_not_overclaimed",
                "La valeur est mesurée sans surpromesse",
                "Le temps libéré reste distinct d'une économie budgétaire.",
                "Séparer explicitement gain de temps, valeur et économie constatée.",
                lambda r, _p: _check_passed(r, "time_budget_separated"),
            ),
            ReadinessCheck(
                "atlas_output_usable",
                "Le résultat alimente un outil de décision",
                "Le pont Atlas charge sept cartes dans un espace versionné.",
                "Produire un résultat Atlas exploitable et versionné.",
                lambda r, _p: _check_passed(r, "atlas_bridge_loaded"),
            ),
        ),
        "innovation": (
            ReadinessCheck(
                "seven_linked_maps",
                "Le diagnostic dépasse l'inventaire d'IA",
                "Sept cartes relient travail, décisions, données, systèmes, IA et valeur.",
                "Relier l'inventaire IA au travail et aux décisions.",
                lambda r, _p: _check_passed(r, "atlas_bridge_loaded"),
            ),
            ReadinessCheck(
                "maieutic_loop",
                "L'agent provoque une décision humaine",
                "La chronologie contient question, réponse ambiguë, validation et recalcul.",
                "Montrer une boucle question, validation et adaptation.",
                lambda r, _p: _has_statement_kind(r, "question")
                and _has_statement_kind(r, "human_validation"),
            ),
            ReadinessCheck(
                "epistemic_refusal",
                "L'agent sait ne pas conclure",
                "AI-008 renvoie information insuffisante.",
                "Ajouter un cas où l'agent refuse une conclusion sans preuve.",
                lambda r, _p: _check_passed(r, "insufficient_information_refusal"),
            ),
            ReadinessCheck(
                "live_llm_orchestration_evidence",
                "Une orchestration LLM est démontrée et bornée",
                "Un reçu Asteria horodaté prouve au moins un appel LLM contrôlé.",
                "Exécuter le test Asteria borné puis conserver le reçu sans secret.",
                lambda _r, p: _exists(
                    p, "outputs/winner-demo/external-orchestration-evidence.json"
                ),
            ),
        ),
        "quality": (
            ReadinessCheck(
                "acceptance_suite_passes",
                "Tous les contrôles d'acceptation passent",
                "La suite Winner est au vert.",
                "Corriger tout contrôle d'acceptation en échec.",
                lambda r, _p: bool(r.get("evaluation", {}).get("passed")),
            ),
            ReadinessCheck(
                "five_replays_consistent",
                "Cinq exécutions sont cohérentes",
                "Les empreintes sémantiques sont identiques.",
                "Stabiliser cinq rejeux consécutifs.",
                lambda r, _p: _check_passed(r, "replay_consistency"),
            ),
            ReadinessCheck(
                "all_findings_sourced",
                "Chaque constat présenté est sourcé",
                "Le contrôle de traçabilité atteint 100 %.",
                "Relier chaque constat à un fichier, une feuille et une cellule.",
                lambda r, _p: _check_passed(r, "all_findings_sourced")
                and _check_passed(r, "cell_traceability"),
            ),
            ReadinessCheck(
                "human_gate_enforced",
                "Aucune décision bloquante n'est finalisée seule",
                "L'espace reste en staging avec validation humaine obligatoire.",
                "Bloquer la publication tant qu'une validation humaine manque.",
                lambda r, _p: _check_passed(r, "no_automatic_finalization"),
            ),
        ),
        "ux": (
            ReadinessCheck(
                "under_five_minutes",
                "Le parcours respecte le temps disponible",
                "Le moteur passe le contrôle des cinq minutes.",
                "Raccourcir le parcours de démonstration.",
                lambda r, _p: _check_passed(r, "execution_under_five_minutes"),
            ),
            ReadinessCheck(
                "one_click_launcher",
                "La démonstration se lance en un clic",
                "Un lanceur Jury Mode est livré.",
                "Ajouter un lanceur de démonstration en un clic.",
                lambda _r, p: _exists(p, "Lancer_Flow_Scout_Jury.command"),
            ),
            ReadinessCheck(
                "offline_fallback",
                "Un scénario de secours hors ligne existe",
                "Le Jury Mode autonome est générable localement.",
                "Fournir une démo locale autonome et réinitialisable.",
                lambda _r, p: _exists(p, "scripts/build_jury_mode.py"),
            ),
            ReadinessCheck(
                "public_testable_demo",
                "Une URL publique testable est attestée",
                "Un reçu de déploiement vérifié est livré sans secret.",
                "Vérifier le déploiement public puis conserver son URL et son statut.",
                lambda _r, p: _exists(p, "docs/jury/PUBLIC-DEMO-VERIFIED.md"),
            ),
        ),
        "clarity": (
            ReadinessCheck(
                "clear_promise",
                "La promesse tient en une phrase",
                "Le résultat Winner contient une promesse explicite.",
                "Écrire une promesse problème, action et résultat en une phrase.",
                lambda r, _p: len(str(r.get("promise", "")).strip()) >= 40,
            ),
            ReadinessCheck(
                "two_minute_video",
                "Une vidéo autonome de deux minutes est livrée",
                "Le MP4 officiel est présent dans les livrables.",
                "Produire une vidéo autonome de deux minutes.",
                lambda _r, p: _exists(
                    p, "outputs/winner-demo/Flow_Scout_2min_sexy_pro.mp4"
                ),
            ),
            ReadinessCheck(
                "proofs_visible",
                "Les preuves sont visibles dans le récit",
                "La chronologie AI-002 contient des localisateurs de preuve.",
                "Afficher les preuves et leurs localisateurs dans la démo.",
                lambda r, _p: _check_passed(r, "cell_traceability"),
            ),
            ReadinessCheck(
                "submission_documented",
                "La procédure de soumission est explicite",
                "Une checklist dédiée accompagne le livrable.",
                "Ajouter une checklist de soumission reproductible.",
                lambda _r, p: _exists(p, "docs/jury/SUBMISSION-CHECKLIST.md"),
            ),
        ),
    }
