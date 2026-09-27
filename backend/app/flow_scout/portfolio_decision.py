"""Moteur déterministe d'arbitrage du portefeuille Flow Scout.

Le moteur choisit une option, explique les règles appliquées et prépare une action
dans Atlas. Il ne publie jamais une décision finale : l'approbation humaine reste
obligatoire pour chaque arbitrage.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "flow-scout-portfolio-decision-policy.v1.json"
)

_OPTION_PRIORITY = {
    "SUSPEND": 100,
    "REQUEST_INFORMATION": 90,
    "REMEDIATE": 80,
    "CONSOLIDATE": 75,
    "STOP": 70,
    "PILOT": 50,
    "MAINTAIN": 30,
    "SCALE": 20,
}

_ALTERNATIVES = {
    "REQUEST_INFORMATION": ("REMEDIATE", "PILOT"),
    "SUSPEND": ("REMEDIATE", "REQUEST_INFORMATION"),
    "REMEDIATE": ("PILOT", "STOP"),
    "CONSOLIDATE": ("MAINTAIN", "STOP"),
    "STOP": ("REMEDIATE", "PILOT"),
    "PILOT": ("REMEDIATE", "MAINTAIN"),
    "MAINTAIN": ("PILOT", "SCALE"),
    "SCALE": ("MAINTAIN", "PILOT"),
}


class DecisionPolicyError(ValueError):
    """La politique ou une entrée du portefeuille n'est pas exploitable."""


def load_decision_policy(path: str | Path | None = None) -> dict[str, Any]:
    """Charge et contrôle la politique d'arbitrage versionnée."""
    policy_path = Path(path) if path is not None else DEFAULT_POLICY_PATH
    try:
        raw = policy_path.read_bytes()
        policy = json.loads(raw)
    except FileNotFoundError as exc:
        raise DecisionPolicyError(f"Politique introuvable : {policy_path}") from exc
    except json.JSONDecodeError as exc:
        raise DecisionPolicyError(f"Politique JSON invalide : {exc}") from exc
    if not isinstance(policy, dict):
        raise DecisionPolicyError("La politique doit être un objet JSON.")
    if policy.get("schema_version") != "flow-scout-portfolio-decision-policy-v1":
        raise DecisionPolicyError("Version de politique non prise en charge.")

    weights = _dict(policy.get("score_model"), "score_model").get("weights_percent")
    weights = _dict(weights, "score_model.weights_percent")
    if not weights or round(sum(_number(value, name) for name, value in weights.items()), 6) != 100:
        raise DecisionPolicyError("La somme des poids de décision doit être égale à 100.")

    options = _dict(policy.get("decision_options"), "decision_options")
    if set(_OPTION_PRIORITY) - set(options):
        missing = ", ".join(sorted(set(_OPTION_PRIORITY) - set(options)))
        raise DecisionPolicyError(f"Options de décision absentes : {missing}.")

    for gate in _list(policy.get("hard_gates"), "hard_gates"):
        if not isinstance(gate, dict) or gate.get("decision") not in options:
            raise DecisionPolicyError("Une règle bloquante référence une option inconnue.")
    for band in _list(policy.get("score_bands"), "score_bands"):
        if not isinstance(band, dict) or band.get("decision") not in options:
            raise DecisionPolicyError("Une bande de score référence une option inconnue.")

    policy["_meta"] = {
        "path": str(policy_path),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    return policy


def evaluate_portfolio_item(
    item: dict[str, Any], *, policy: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Choisit et met en attente la meilleure option pour un élément du portefeuille."""
    if not isinstance(item, dict):
        raise DecisionPolicyError("L'élément du portefeuille doit être un objet.")
    active_policy = policy or load_decision_policy()
    item_id = str(item.get("item_id", "")).strip()
    if not item_id:
        raise DecisionPolicyError("item_id est obligatoire.")

    metrics = _dict(item.get("metrics"), "metrics")
    weights = _dict(
        _dict(active_policy.get("score_model"), "score_model").get(
            "weights_percent"
        ),
        "score_model.weights_percent",
    )
    cleaned_metrics: dict[str, float] = {}
    missing_metrics: list[str] = []
    for name in weights:
        if name not in metrics or metrics[name] is None:
            missing_metrics.append(name)
            continue
        value = _number(metrics[name], f"metrics.{name}")
        if not 0 <= value <= 100:
            raise DecisionPolicyError(f"metrics.{name} doit être compris entre 0 et 100.")
        cleaned_metrics[name] = value

    signals = sorted({str(value).strip() for value in _as_list(item.get("signals")) if str(value).strip()})
    evidence_refs = [
        str(value).strip()
        for value in _as_list(item.get("evidence_refs"))
        if str(value).strip()
    ]
    confidence = _bounded_number(item.get("confidence", 0), "confidence")
    open_questions = int(_number(item.get("open_blocking_questions", 0), "open_blocking_questions"))
    evidence_coverage = _bounded_number(
        item.get("evidence_coverage_percent", 100 if evidence_refs else 0),
        "evidence_coverage_percent",
    )

    context = {
        **item,
        "signals": signals,
        "confidence": confidence,
        "open_blocking_questions": open_questions,
        "evidence_coverage_percent": evidence_coverage,
    }

    candidates: list[dict[str, Any]] = []
    for gate in sorted(
        _list(active_policy.get("hard_gates"), "hard_gates"),
        key=lambda value: int(value.get("priority", 0)) if isinstance(value, dict) else 0,
        reverse=True,
    ):
        if isinstance(gate, dict) and _gate_matches(gate, context):
            candidates.append(gate)

    score_model = _dict(active_policy.get("score_model"), "score_model")
    metric_coverage = round(len(cleaned_metrics) * 100 / len(weights), 1)
    minimum_metric_coverage = _bounded_number(
        score_model.get("minimum_metric_coverage_percent", 100),
        "score_model.minimum_metric_coverage_percent",
    )
    if metric_coverage < minimum_metric_coverage:
        candidates.append(
            {
                "id": "GATE-SYSTEM-METRICS",
                "priority": 95,
                "name": "Métriques obligatoires manquantes",
                "decision": "REQUEST_INFORMATION",
                "rationale": "Toutes les dimensions du score doivent être renseignées avant arbitrage.",
                "required_reviewers": ["responsable_metier"],
            }
        )

    portfolio_score = None
    if metric_coverage >= minimum_metric_coverage:
        used_weight = sum(_number(weights[name], name) for name in cleaned_metrics)
        if not used_weight:
            raise DecisionPolicyError("Le score ne possède aucun poids exploitable.")
        portfolio_score = round(
            sum(
                cleaned_metrics[name] * _number(weights[name], name)
                for name in cleaned_metrics
            )
            / used_weight,
            int(score_model.get("rounding_decimals", 1)),
        )

    if candidates:
        selected_rule = max(candidates, key=lambda value: int(value.get("priority", 0)))
        option = str(selected_rule["decision"])
        rationale = str(selected_rule["rationale"])
        triggered_rules = [
            {
                "rule_id": str(rule.get("id", "")),
                "name": str(rule.get("name", "")),
                "priority": int(rule.get("priority", 0)),
                "effect": str(rule.get("decision", "")),
            }
            for rule in sorted(
                candidates,
                key=lambda value: int(value.get("priority", 0)),
                reverse=True,
            )
        ]
        reviewers = list(selected_rule.get("required_reviewers", []))
    else:
        if portfolio_score is None:
            raise DecisionPolicyError("Le score n'a pas pu être calculé.")
        selected_band = _select_band(active_policy, portfolio_score)
        option = str(selected_band["decision"])
        rationale = str(selected_band["rationale"])
        triggered_rules = [
            {
                "rule_id": "SCORE-BAND",
                "name": f"Score {selected_band['minimum']}–{selected_band['maximum']}",
                "priority": 0,
                "effect": option,
            }
        ]
        reviewers = ["responsable_portefeuille", "responsable_metier"]

    options = _dict(active_policy.get("decision_options"), "decision_options")
    selected = _dict(options.get(option), f"decision_options.{option}")
    supervision = _dict(active_policy.get("human_supervision"), "human_supervision")
    alternatives = [
        {
            "option": candidate,
            "label": _dict(options[candidate], f"decision_options.{candidate}").get("label"),
        }
        for candidate in _ALTERNATIVES[option]
    ]
    policy_meta = _dict(active_policy.get("_meta", {}), "_meta")

    return {
        "schema_version": "flow-scout-portfolio-recommendation-v1",
        "item_id": item_id,
        "policy_id": active_policy.get("policy_id"),
        "policy_version": active_policy.get("schema_version"),
        "policy_sha256": policy_meta.get("sha256"),
        "portfolio_score": portfolio_score,
        "metric_coverage_percent": metric_coverage,
        "missing_metrics": missing_metrics,
        "recommended_option": option,
        "recommended_label": selected.get("label"),
        "rationale": rationale,
        "alternatives": alternatives,
        "triggered_rules": triggered_rules,
        "signals": signals,
        "evidence_refs": evidence_refs,
        "evidence_coverage_percent": evidence_coverage,
        "confidence": confidence,
        "agent_action": {
            "mode": "STAGE_FOR_HUMAN_APPROVAL",
            "status": supervision.get("effect_before_approval", "STAGED_BLOCKED"),
            "instruction": selected.get("agent_action"),
            "can_execute_external_action": False,
            "automatic_finalization": False,
        },
        "human_approval": {
            "required": True,
            "status": "PENDING",
            "required_reviewers": reviewers,
            "allowed_responses": supervision.get("allowed_responses", []),
            "required_fields": supervision.get("required_fields", []),
        },
        "traceability": {
            "input_snapshot": {
                "metrics": cleaned_metrics,
                "signals": signals,
                "open_blocking_questions": open_questions,
            },
            "tie_breakers": active_policy.get("tie_breakers", []),
        },
    }


def evaluate_portfolio(
    items: Iterable[dict[str, Any]], *, policy: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Évalue, compte et ordonne un portefeuille complet pour la revue humaine."""
    active_policy = policy or load_decision_policy()
    recommendations = [
        evaluate_portfolio_item(item, policy=active_policy) for item in items
    ]
    recommendations.sort(
        key=lambda item: (
            -_OPTION_PRIORITY[str(item["recommended_option"])],
            -(float(item["portfolio_score"]) if item["portfolio_score"] is not None else -1),
            str(item["item_id"]),
        )
    )
    counts = Counter(str(item["recommended_option"]) for item in recommendations)
    return {
        "schema_version": "flow-scout-portfolio-review-v1",
        "policy_id": active_policy.get("policy_id"),
        "item_count": len(recommendations),
        "recommendation_counts": dict(sorted(counts.items())),
        "human_approval_required": bool(recommendations),
        "automatic_finalization": False,
        "review_queue": recommendations,
    }


def build_alignment_dashboard(
    items: Iterable[dict[str, Any]], *, policy: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Construit le dashboard d'alignement et sa file d'actions supervisées."""
    active_policy = policy or load_decision_policy()
    materialized_items = list(items)
    portfolio = evaluate_portfolio(materialized_items, policy=active_policy)
    rules = _dict(active_policy.get("alignment_dashboard"), "alignment_dashboard")
    dimension_rules = _dict(rules.get("dimensions"), "alignment_dashboard.dimensions")
    target = _bounded_number(rules.get("target_score", 80), "alignment_dashboard.target_score")
    critical = {str(value) for value in _as_list(rules.get("critical_dimensions"))}

    metric_snapshots = {
        str(item["item_id"]): _dict(
            _dict(item.get("traceability"), "traceability").get("input_snapshot"),
            "traceability.input_snapshot",
        ).get("metrics", {})
        for item in portfolio["review_queue"]
    }
    dimensions: list[dict[str, Any]] = []
    for metric_name, raw_rule in dimension_rules.items():
        rule = _dict(raw_rule, f"alignment_dashboard.dimensions.{metric_name}")
        values = [
            (item_id, float(metrics[metric_name]))
            for item_id, metrics in metric_snapshots.items()
            if isinstance(metrics, dict) and metric_name in metrics
        ]
        average = round(sum(value for _, value in values) / len(values), 1) if values else None
        item_statuses = [
            (item_id, _alignment_status(active_policy, value))
            for item_id, value in values
        ]
        status = (
            min(
                (value for _, value in item_statuses),
                key=lambda value: {"RED": 0, "AMBER": 1, "GREEN": 2}[value],
            )
            if item_statuses
            else "UNKNOWN"
        )
        below_target = [item_id for item_id, value in values if value < target]
        red_items = [
            item_id for item_id, item_status in item_statuses if item_status == "RED"
        ]
        dimensions.append(
            {
                "dimension": metric_name,
                "label": rule.get("label", metric_name),
                "question": rule.get("question", ""),
                "score": average,
                "target": target,
                "gap_to_target": round(target - average, 1) if average is not None and average < target else 0,
                "status": status,
                "critical": metric_name in critical,
                "coverage_percent": round(len(values) * 100 / len(materialized_items), 1)
                if materialized_items
                else 0,
                "items_below_target": below_target,
                "red_items": red_items,
                "recommended_action": rule.get("recommended_action_below_target", "")
                if below_target
                else "Maintenir la mesure et vérifier la stabilité dans le temps.",
                "reviewers": rule.get("reviewers", []),
                "human_approval_required": bool(below_target),
            }
        )

    weights = _dict(
        _dict(active_policy.get("score_model"), "score_model").get("weights_percent"),
        "score_model.weights_percent",
    )
    scored_dimensions = [item for item in dimensions if item["score"] is not None]
    used_weight = sum(float(weights[item["dimension"]]) for item in scored_dimensions)
    alignment_score = (
        round(
            sum(float(item["score"]) * float(weights[item["dimension"]]) for item in scored_dimensions)
            / used_weight,
            1,
        )
        if used_weight
        else None
    )
    overall_status = _alignment_status(active_policy, alignment_score)
    if any(item["critical"] and item["status"] == "RED" for item in dimensions):
        overall_status = "RED"

    status_priority = {"RED": 0, "AMBER": 1, "GREEN": 2, "UNKNOWN": 3}
    priority_actions = [
        {
            "priority": index,
            "dimension": item["dimension"],
            "status": item["status"],
            "action": item["recommended_action"],
            "affected_items": item["items_below_target"],
            "reviewers": item["reviewers"],
            "agent_action": "STAGE_FOR_HUMAN_APPROVAL",
            "human_approval_required": True,
        }
        for index, item in enumerate(
            sorted(
                (item for item in dimensions if item["items_below_target"]),
                key=lambda item: (
                    status_priority[item["status"]],
                    0 if item["critical"] else 1,
                    -float(item["gap_to_target"]),
                    str(item["dimension"]),
                ),
            ),
            start=1,
        )
    ]

    return {
        "schema_version": rules.get(
            "schema_version", "flow-scout-alignment-dashboard-rules-v1"
        ),
        "policy_id": active_policy.get("policy_id"),
        "policy_sha256": _dict(active_policy.get("_meta", {}), "_meta").get(
            "sha256"
        ),
        "portfolio_alignment_score": alignment_score,
        "overall_status": overall_status,
        "target_score": target,
        "item_count": len(materialized_items),
        "dimensions": dimensions,
        "priority_actions": priority_actions,
        "portfolio_decisions": portfolio,
        "human_approval_required": bool(materialized_items),
        "automatic_finalization": False,
        "publication_status": "STAGED_BLOCKED" if materialized_items else "EMPTY",
    }


def _gate_matches(gate: dict[str, Any], context: dict[str, Any]) -> bool:
    if "when" in gate:
        return _condition_matches(_dict(gate["when"], "hard_gate.when"), context)
    if "when_any" in gate:
        conditions = _list(gate["when_any"], "hard_gate.when_any")
        return any(
            isinstance(condition, dict) and _condition_matches(condition, context)
            for condition in conditions
        )
    raise DecisionPolicyError(f"La règle {gate.get('id')} ne contient aucune condition.")


def _condition_matches(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    if "signals_any" in condition:
        expected = {str(value) for value in _as_list(condition["signals_any"])}
        actual = {str(value) for value in _as_list(context.get("signals"))}
        return bool(expected & actual)
    field = str(condition.get("field", ""))
    operator = str(condition.get("operator", ""))
    if not field or field not in context:
        return False
    left = _number(context[field], field)
    right = _number(condition.get("value"), f"{field}.threshold")
    comparisons = {
        "<": left < right,
        "<=": left <= right,
        ">": left > right,
        ">=": left >= right,
        "==": left == right,
        "!=": left != right,
    }
    if operator not in comparisons:
        raise DecisionPolicyError(f"Opérateur de règle inconnu : {operator}.")
    return comparisons[operator]


def _select_band(policy: dict[str, Any], score: float) -> dict[str, Any]:
    for band in _list(policy.get("score_bands"), "score_bands"):
        if not isinstance(band, dict):
            continue
        minimum = _number(band.get("minimum"), "score_band.minimum")
        maximum = _number(band.get("maximum"), "score_band.maximum")
        if minimum <= score <= maximum:
            return band
    raise DecisionPolicyError(f"Aucune règle ne couvre le score {score}.")


def _alignment_status(policy: dict[str, Any], score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    rules = _dict(policy.get("alignment_dashboard"), "alignment_dashboard")
    thresholds = _dict(rules.get("status_thresholds"), "status_thresholds")
    for status in ("GREEN", "AMBER", "RED"):
        band = _dict(thresholds.get(status), f"status_thresholds.{status}")
        if _number(band.get("minimum"), f"{status}.minimum") <= score <= _number(
            band.get("maximum"), f"{status}.maximum"
        ):
            return status
    raise DecisionPolicyError(f"Aucun statut d'alignement ne couvre le score {score}.")


def _bounded_number(value: Any, field: str) -> float:
    number = _number(value, field)
    if not 0 <= number <= 100:
        raise DecisionPolicyError(f"{field} doit être compris entre 0 et 100.")
    return number


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise DecisionPolicyError(f"{field} doit être numérique.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise DecisionPolicyError(f"{field} doit être numérique.") from exc


def _dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DecisionPolicyError(f"{field} doit être un objet.")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise DecisionPolicyError(f"{field} doit être une liste.")
    return value


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
