"""Construction déterministe des sept cartes Flow Scout depuis le jeu assureur.

Le moteur travaille uniquement à partir des tables de collecte. L'onglet
``Résultats attendus`` est volontairement exclu : il sert d'oracle de test et ne
doit jamais alimenter les constats lors d'une évaluation à l'aveugle.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from app.flow_scout.ingestion import ingest_file
from app.flow_scout.models import SourceKind, SourceRow, SourceTable

_REQUIRED_KINDS = (
    SourceKind.DEMO_COLLECTION,
    SourceKind.DEMO_EXTRACTS,
    SourceKind.DEMO_ORGANIZATION,
    SourceKind.DEMO_ACTIVITIES,
    SourceKind.DEMO_DECISIONS,
    SourceKind.DEMO_APPLICATIONS,
    SourceKind.DEMO_AI,
    SourceKind.DEMO_COSTS,
    SourceKind.DEMO_VALUE,
    SourceKind.DEMO_METRICS,
    SourceKind.DEMO_EVENTS,
    SourceKind.DEMO_RELATIONS,
)

_MAP_DEFINITIONS = (
    (
        "human_work",
        "Le travail humain",
        "Qui fait quoi et où se concentre l’effort ?",
    ),
    (
        "decisions_responsibilities",
        "Les décisions et responsabilités",
        "Qui peut décider quoi, et que peut-on déléguer ?",
    ),
    (
        "knowledge_data",
        "Les connaissances et données",
        "De quoi faut-il disposer pour bien travailler et décider ?",
    ),
    (
        "tools_dependencies",
        "Les outils et dépendances",
        "Par quels systèmes passe le travail ?",
    ),
    (
        "actual_ai_use",
        "L’usage réel de l’IA",
        "Que fait réellement l’IA aujourd’hui ?",
    ),
    (
        "value_cost",
        "La valeur et le coût",
        "Où l’IA consomme-t-elle des ressources et que produit-elle en retour ?",
    ),
    (
        "transformation_opportunities",
        "Les possibilités de transformation",
        "Que devrait-on changer, et à quelles conditions ?",
    ),
)


class EnterpriseMapError(ValueError):
    """Le classeur ne respecte pas le contrat de démonstration assureur."""


def build_enterprise_maps(path: str | Path) -> dict[str, object]:
    """Produit les sept cartes, leurs liens et les constats sourcés."""
    source = Path(path)
    tables = ingest_file(source)
    by_kind = {table.kind: table for table in tables}
    missing = [kind.value for kind in _REQUIRED_KINDS if kind not in by_kind]
    if missing:
        raise EnterpriseMapError(
            "Le classeur assureur est incomplet. Tables manquantes : "
            + ", ".join(missing)
        )

    collection = _rows(by_kind[SourceKind.DEMO_COLLECTION], "source_id")
    extracts = _rows(by_kind[SourceKind.DEMO_EXTRACTS], "extrait_id")
    organization = _rows(by_kind[SourceKind.DEMO_ORGANIZATION], "team_id")
    activities = _rows(by_kind[SourceKind.DEMO_ACTIVITIES], "activity_id")
    decisions = _rows(by_kind[SourceKind.DEMO_DECISIONS], "decision_id")
    applications = _rows(by_kind[SourceKind.DEMO_APPLICATIONS], "application_id")
    ais = _rows(by_kind[SourceKind.DEMO_AI], "ai_id")
    costs = _rows(by_kind[SourceKind.DEMO_COSTS], "cost_id")
    values = _rows(by_kind[SourceKind.DEMO_VALUE], "value_id")
    metrics = _rows(by_kind[SourceKind.DEMO_METRICS], "metric_id")
    events = _rows(by_kind[SourceKind.DEMO_EVENTS], "event_id")
    relations = _rows(by_kind[SourceKind.DEMO_RELATIONS], "relation_id")

    activity_by_id = _index(activities, "activity_id")
    decision_by_id = _index(decisions, "decision_id")
    application_by_id = _index(applications, "application_id")
    ai_by_id = _index(ais, "ai_id")
    value_by_ai = _index(values, "ai_id")
    metrics_by_activity = _group(metrics, "activity_id")
    costs_by_ai = _group(costs, "ai_id")

    ai_records = [
        _ai_record(
            row,
            activity_by_id=activity_by_id,
            application_by_id=application_by_id,
            value_by_ai=value_by_ai,
            costs_by_ai=costs_by_ai,
        )
        for row in ais
    ]
    findings = _build_findings(
        ais=ais,
        ai_by_id=ai_by_id,
        activities=activities,
        activity_by_id=activity_by_id,
        decisions=decisions,
        decision_by_id=decision_by_id,
        values=values,
        value_by_ai=value_by_ai,
        metrics_by_activity=metrics_by_activity,
        costs_by_ai=costs_by_ai,
        extracts=extracts,
    )
    findings_by_map = _group_dicts(findings, "map_id")
    strategic_depth = _strategic_depth(relations)

    maps = [
        _human_work_map(organization, activities, findings_by_map),
        _decisions_map(decisions, ais, activity_by_id, findings_by_map),
        _knowledge_map(collection, relations, findings_by_map),
        _tools_map(applications, ai_records, relations, findings_by_map),
        _ai_use_map(ai_records, findings_by_map),
        _value_cost_map(ai_records, findings_by_map),
        _transformation_map(findings, strategic_depth),
    ]

    relation_records = [_relation_record(row) for row in relations]
    return {
        "schema_version": "flow-scout-enterprise-maps-v1",
        "dataset": {
            "file": source.name,
            "role": "synthetic_demo_collection",
            "period": "2026-08",
            "as_of": "2026-09-20",
            "event_count": len(events),
            "warning": (
                "Données entièrement synthétiques. Les constats valent uniquement "
                "dans le scénario de démonstration."
            ),
            "expected_results_sheet_used": False,
            "expected_results_sheet_reason": (
                "Onglet réservé à la comparaison des tests, exclu de la détection."
            ),
        },
        "map_count": len(maps),
        "maps": maps,
        "cross_map_links": {
            "count": len(relation_records),
            "items": relation_records,
        },
        "findings": findings,
        "finding_count": len(findings),
        "strategic_depth": strategic_depth,
        "atlas_readiness": {
            "status": "projection_ready_contract_to_confirm",
            "ready_objects": [
                "teams",
                "personas",
                "activities",
                "decisions",
                "applications",
                "ai_usages",
                "costs",
                "values",
                "evidence",
                "relations",
            ],
            "open_condition": (
                "Adapter la projection au contrat d'import réel de Flow Atlas et "
                "valider les identifiants métier."
            ),
        },
    }


def _human_work_map(
    organization: list[SourceRow],
    activities: list[SourceRow],
    findings_by_map: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    activity_items = []
    total_minutes = 0.0
    for row in activities:
        volume = _number(row, "Volume mensuel")
        minutes = _number(row, "Minutes / tâche avant")
        workload = volume * minutes
        total_minutes += workload
        activity_items.append(
            {
                "id": _text(row, "activity_id"),
                "name": _text(row, "Activité"),
                "persona_id": _text(row, "persona_id"),
                "team_id": _text(row, "team_id"),
                "process_id": _text(row, "process_id"),
                "category": _text(row, "Catégorie"),
                "monthly_volume": volume,
                "minutes_per_task_before": minutes,
                "monthly_workload_hours": round(workload / 60, 2),
                "application_id": _text(row, "application_id"),
                "source_id": _text(row, "source_id"),
                "evidence": _evidence(
                    row, "Activité", "Volume mensuel", "Minutes / tâche avant"
                ),
            }
        )
    teams = [
        {
            "id": _text(row, "team_id"),
            "name": _text(row, "Équipe"),
            "persona_id": _text(row, "persona_id"),
            "persona": _text(row, "Persona représentatif"),
            "headcount_fte": _number(row, "ETP équipe"),
            "source_id": _text(row, "source_id"),
            "evidence": _evidence(row, "Équipe", "Persona représentatif", "ETP équipe"),
        }
        for row in organization
    ]
    return _map_payload(
        "human_work",
        summary={
            "teams": len(teams),
            "representative_personas": len(teams),
            "activities": len(activity_items),
            "headcount_fte": _clean(sum(item["headcount_fte"] for item in teams)),
            "monthly_workload_hours_before": round(total_minutes / 60, 2),
        },
        content={"teams": teams, "activities": activity_items},
        findings=findings_by_map.get("human_work", []),
    )


def _decisions_map(
    decisions: list[SourceRow],
    ais: list[SourceRow],
    activity_by_id: dict[str, SourceRow],
    findings_by_map: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    decision_items = []
    for row in decisions:
        activity_id = _text(row, "activity_id")
        activity = activity_by_id.get(activity_id)
        decision_items.append(
            {
                "id": _text(row, "decision_id"),
                "activity_id": activity_id,
                "activity": _text(activity, "Activité") if activity else "",
                "decision": _text(row, "Décision"),
                "responsible_persona_id": _text(row, "Responsable"),
                "rule": _text(row, "Règle"),
                "threshold": _optional_number(row, "Seuil"),
                "unit": _text(row, "Unité"),
                "source_id": _text(row, "source_id"),
                "evidence": _evidence(row, "Décision", "Responsable", "Règle", "Seuil"),
            }
        )
    delegations = [
        {
            "ai_id": _text(row, "ai_id"),
            "activity_id": _text(row, "activity_id"),
            "observed_level": _number(row, "D observé"),
            "authorized_level": _number(row, "D autorisé"),
            "proposed_target_level": _number(row, "D cible proposé"),
            "within_authority": _number(row, "D observé") <= _number(row, "D autorisé"),
            "evidence": _evidence(row, "D observé", "D autorisé", "D cible proposé"),
        }
        for row in ais
    ]
    return _map_payload(
        "decisions_responsibilities",
        summary={
            "decisions": len(decision_items),
            "delegations_observed": len(delegations),
            "delegation_overruns": sum(
                not item["within_authority"] for item in delegations
            ),
        },
        content={"decisions": decision_items, "delegations": delegations},
        findings=findings_by_map.get("decisions_responsibilities", []),
    )


def _knowledge_map(
    collection: list[SourceRow],
    relations: list[SourceRow],
    findings_by_map: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    families: dict[str, int] = defaultdict(int)
    sources = []
    for row in collection:
        family = _text(row, "Famille")
        families[family] += 1
        sources.append(
            {
                "id": _text(row, "source_id"),
                "family": family,
                "name": _text(row, "Source"),
                "collection_mode": _text(row, "Mode prévu"),
                "owner": _text(row, "Propriétaire métier"),
                "priority": _text(row, "Priorité"),
                "status": _text(row, "État de collecte"),
                "evidence": _evidence(row, "Source", "Propriétaire métier", "Priorité"),
            }
        )
    document_links = [
        _relation_record(row)
        for row in relations
        if _text(row, "Relation") == "DOCUMENTS"
    ]
    return _map_payload(
        "knowledge_data",
        summary={
            "source_types": len(sources),
            "families": len(families),
            "documented_activity_links": len(document_links),
        },
        content={
            "sources": sources,
            "families": dict(sorted(families.items())),
            "documented_activity_links": document_links,
        },
        findings=findings_by_map.get("knowledge_data", []),
    )


def _tools_map(
    applications: list[SourceRow],
    ai_records: list[dict[str, object]],
    relations: list[SourceRow],
    findings_by_map: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    app_items = [
        {
            "id": _text(row, "application_id"),
            "name": _text(row, "Application fictive"),
            "domain": _text(row, "Domaine"),
            "vendor": _text(row, "Éditeur"),
            "hosting": _text(row, "Hébergement déclaré"),
            "status": _text(row, "Statut"),
            "source_id": _text(row, "source_id"),
            "evidence": _evidence(
                row, "Application fictive", "Hébergement déclaré", "Statut"
            ),
        }
        for row in applications
    ]
    dependency_links = [
        _relation_record(row)
        for row in relations
        if _text(row, "Relation") in {"RUNS_IN", "SUPPORTS"}
    ]
    return _map_payload(
        "tools_dependencies",
        summary={
            "applications": len(app_items),
            "ai_usages": len(ai_records),
            "dependency_links": len(dependency_links),
        },
        content={
            "applications": app_items,
            "ai_application_links": [
                {"ai_id": item["id"], "application_id": item["application_id"]}
                for item in ai_records
            ],
            "dependency_links": dependency_links,
        },
        findings=findings_by_map.get("tools_dependencies", []),
    )


def _ai_use_map(
    ai_records: list[dict[str, object]],
    findings_by_map: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    categories: dict[str, int] = defaultdict(int)
    for item in ai_records:
        categories[str(item["category"])] += 1
    return _map_payload(
        "actual_ai_use",
        summary={
            "ai_usages": len(ai_records),
            "categories": dict(sorted(categories.items())),
            "confirmed_or_observed": sum(
                (
                    "observ" in _normalize(str(item["usage_evidence"]))
                    or (
                        "confirm" in _normalize(str(item["usage_evidence"]))
                        and "non confirm" not in _normalize(str(item["usage_evidence"]))
                    )
                )
                for item in ai_records
            ),
        },
        content={"ai_usages": ai_records},
        findings=findings_by_map.get("actual_ai_use", []),
    )


def _value_cost_map(
    ai_records: list[dict[str, object]],
    findings_by_map: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    return _map_payload(
        "value_cost",
        summary={
            "monthly_ai_cost_eur": _clean(
                sum(float(item["monthly_cost_eur"]) for item in ai_records)
            ),
            "budget_savings_eur": _clean(
                sum(float(item["budget_savings_eur"]) for item in ai_records)
            ),
            "avoided_loss_estimate_eur": _clean(
                sum(float(item["avoided_loss_estimate_eur"]) for item in ai_records)
            ),
            "attributed_revenue_estimate_eur": _clean(
                sum(
                    float(item["attributed_revenue_estimate_eur"])
                    for item in ai_records
                )
            ),
            "hours_released_raw_sum": _clean(
                sum(float(item["hours_released_simulated"]) for item in ai_records)
            ),
            "aggregation_warning": (
                "Les heures peuvent se chevaucher. Les économies, pertes évitées et "
                "revenus attribués restent séparés et ne forment pas un bénéfice net."
            ),
        },
        content={"by_ai": ai_records},
        findings=findings_by_map.get("value_cost", []),
    )


def _transformation_map(
    findings: list[dict[str, object]], strategic_depth: dict[str, object]
) -> dict[str, object]:
    opportunities = [
        {
            "id": f"OPP-{index:03d}",
            "finding_id": finding["id"],
            "priority": _priority_from_severity(str(finding["severity"])),
            "title": finding["title"],
            "action": finding["recommended_action"],
            "conditions": finding["conditions"],
            "objects": finding["objects"],
            "evidence": finding["evidence"],
        }
        for index, finding in enumerate(findings, start=1)
    ]
    return _map_payload(
        "transformation_opportunities",
        summary={
            "opportunities": len(opportunities),
            "priority_now": sum(item["priority"] == "P0" for item in opportunities),
            "strategic_depth": strategic_depth["status"],
        },
        content={"opportunities": opportunities, "strategic_depth": strategic_depth},
        findings=findings,
    )


def _build_findings(
    *,
    ais: list[SourceRow],
    ai_by_id: dict[str, SourceRow],
    activities: list[SourceRow],
    activity_by_id: dict[str, SourceRow],
    decisions: list[SourceRow],
    decision_by_id: dict[str, SourceRow],
    values: list[SourceRow],
    value_by_ai: dict[str, SourceRow],
    metrics_by_activity: dict[str, list[SourceRow]],
    costs_by_ai: dict[str, list[SourceRow]],
    extracts: list[SourceRow],
) -> list[dict[str, object]]:
    del activities, decisions
    findings: list[dict[str, object]] = []

    for ai in ais:
        ai_id = _text(ai, "ai_id")
        observed = _number(ai, "D observé")
        authorized = _number(ai, "D autorisé")
        if observed > authorized:
            activity_id = _text(ai, "activity_id")
            activity = activity_by_id.get(activity_id)
            decision = (
                decision_by_id.get(_text(activity, "decision_id")) if activity else None
            )
            no_validation = _metric_matching(
                metrics_by_activity.get(activity_id, []), "sans validation"
            )
            unvalidated_count = (
                _clean(_number(no_validation, "Valeur")) if no_validation else None
            )
            if unvalidated_count is not None:
                finding_title = "Paiement exécuté sans validation humaine"
                statement = (
                    f"{_text(ai, 'IA / fonction fictive')} peut déclencher des paiements "
                    f"sans accord humain. {unvalidated_count} paiements tests ont été "
                    "réalisés sans validation, alors que la règle de l'entreprise impose "
                    "une validation humaine avant tout paiement."
                )
            else:
                finding_title = "Action exécutée au-delà de l'autorisation donnée"
                statement = (
                    f"{_text(ai, 'IA / fonction fictive')} agit avec plus d'autonomie "
                    "que l'entreprise ne l'autorise. Une personne doit valider l'action "
                    "avant son exécution."
                )
            findings.append(
                _finding(
                    "delegation_overrun",
                    "decisions_responsibilities",
                    finding_title,
                    "critical",
                    [
                        ai_id,
                        activity_id,
                        _text(activity, "decision_id") if activity else "",
                    ],
                    statement,
                    {
                        "observed_level": _clean(observed),
                        "authorized_level": _clean(authorized),
                        "payments_without_validation": unvalidated_count,
                    },
                    "Retirer le périmètre de paiement autonome et rétablir la validation humaine.",
                    [
                        "Contrôle humain actif",
                        "Scopes techniques alignés sur la délégation",
                    ],
                    _combine_evidence(
                        _evidence(ai, "D observé", "D autorisé"),
                        _evidence(decision, "Règle", "Seuil") if decision else [],
                        (
                            _evidence(no_validation, "Mesure", "Valeur")
                            if no_validation
                            else []
                        ),
                    ),
                )
            )

    by_activity = _group(ais, "activity_id")
    for activity_id, linked_ais in by_activity.items():
        if len(linked_ais) < 2:
            continue
        combined_cost = sum(
            _number(cost, "Montant EUR")
            for ai in linked_ais
            for cost in costs_by_ai.get(_text(ai, "ai_id"), [])
        )
        ai_ids = [_text(ai, "ai_id") for ai in linked_ais]
        findings.append(
            _finding(
                "functional_overlap",
                "tools_dependencies",
                "Recouvrement fonctionnel",
                "warning",
                [activity_id, *ai_ids],
                f"{len(ai_ids)} IA soutiennent la même activité {activity_id}.",
                {
                    "ai_count": len(ai_ids),
                    "combined_monthly_cost_eur": _clean(combined_cost),
                },
                "Comparer la couverture, les usages et les coûts avant tout arbitrage.",
                ["Mesure d'usage comparable", "Périmètres fonctionnels confirmés"],
                _combine_evidence(
                    *[
                        _evidence(ai, "activity_id", "application_id")
                        for ai in linked_ais
                    ],
                    *[
                        _evidence(cost, "Poste", "Montant EUR")
                        for ai in linked_ais
                        for cost in costs_by_ai.get(_text(ai, "ai_id"), [])
                    ],
                ),
            )
        )

    for value in values:
        ai_id = _text(value, "ai_id")
        hours = _number(value, "Heures libérées simulées")
        savings = _number(value, "Économie budgétaire EUR")
        if hours > 0 and savings == 0:
            ai = ai_by_id.get(ai_id)
            if ai_id == "AI-001":
                findings.append(
                    _finding(
                        "time_without_budget_savings",
                        "value_cost",
                        "Temps libéré sans économie budgétaire",
                        "info",
                        [ai_id, _text(ai, "activity_id") if ai else ""],
                        (
                            f"{_clean(hours)} heures sont libérées dans la simulation, "
                            "sans économie budgétaire démontrée."
                        ),
                        {"hours_released": _clean(hours), "budget_savings_eur": 0},
                        "Documenter le redéploiement du temps sans le monétiser automatiquement.",
                        [
                            "Usage du temps libéré validé",
                            "Impact budgétaire comptabilisé séparément",
                        ],
                        _combine_evidence(
                            _evidence(
                                value,
                                "Heures libérées simulées",
                                "Économie budgétaire EUR",
                            ),
                            _evidence(ai, "IA / fonction fictive") if ai else [],
                        ),
                    )
                )

    for ai in ais:
        licences = _number(ai, "Licences / comptes")
        active = _number(ai, "Actifs mensuels")
        if licences > 0 and active / licences < 0.5:
            rate = active / licences
            findings.append(
                _finding(
                    "low_adoption",
                    "actual_ai_use",
                    "Activation faible",
                    "warning",
                    [_text(ai, "ai_id")],
                    (
                        f"{_clean(active)} comptes actifs sur {_clean(licences)}, "
                        f"soit {round(rate * 100, 1)} %."
                    ),
                    {
                        "active_users": _clean(active),
                        "licensed_users": _clean(licences),
                        "activation_rate": round(rate, 4),
                    },
                    "Examiner l'utilité réelle, les populations ciblées et le besoin de formation.",
                    [
                        "Population éligible confirmée",
                        "Fréquence et profondeur d'usage mesurées",
                    ],
                    _evidence(ai, "Licences / comptes", "Actifs mensuels", "État"),
                )
            )

        usage_evidence = _normalize(_text(ai, "Preuve usage"))
        model = _normalize(_text(ai, "Modèle"))
        if "non confirme" in usage_evidence or "non communique" in model:
            findings.append(
                _finding(
                    "unqualified_usage",
                    "actual_ai_use",
                    "Usage non qualifié",
                    "high",
                    [_text(ai, "ai_id"), _text(ai, "application_id")],
                    "L'usage est déclaré mais son modèle ou ses conditions ne sont pas confirmés.",
                    {
                        "usage_evidence": _text(ai, "Preuve usage"),
                        "model": _text(ai, "Modèle"),
                        "authorized_level": _clean(_number(ai, "D autorisé")),
                    },
                    "Qualifier l'outil, les données traitées et les conditions contractuelles avant généralisation.",
                    [
                        "Contrat vérifié",
                        "Modèle identifié",
                        "Données et habilitations qualifiées",
                    ],
                    _evidence(ai, "Modèle", "Preuve usage", "D autorisé", "État"),
                )
            )

    for activity_id, activity_metrics in metrics_by_activity.items():
        missing = _metric_matching(activity_metrics, "sans date")
        population = _metric_matching(activity_metrics, "sinistres ouverts")
        if missing and population and _number(population, "Valeur") > 0:
            rate = _number(missing, "Valeur") / _number(population, "Valeur")
            findings.append(
                _finding(
                    "data_incompleteness",
                    "knowledge_data",
                    "Données incomplètes",
                    "high",
                    [activity_id],
                    f"{round(rate * 100, 1)} % des dossiers du périmètre ont une date attendue manquante.",
                    {
                        "missing_records": _clean(_number(missing, "Valeur")),
                        "population": _clean(_number(population, "Valeur")),
                        "missing_rate": round(rate, 4),
                    },
                    "Corriger la qualité des données et qualifier la fiabilité des délais calculés.",
                    [
                        "Champ obligatoire contrôlé",
                        "Couverture de la correction mesurée",
                    ],
                    _combine_evidence(
                        _evidence(missing, "Mesure", "Valeur"),
                        _evidence(population, "Mesure", "Valeur"),
                    ),
                )
            )

        invalid_citations = _metric_matching(activity_metrics, "sans citation valide")
        evaluations = _metric_matching(activity_metrics, "evaluations qualite")
        if invalid_citations and evaluations and _number(evaluations, "Valeur") > 0:
            rate = _number(invalid_citations, "Valeur") / _number(evaluations, "Valeur")
            linked_ai = next(
                (
                    _text(ai, "ai_id")
                    for ai in ais
                    if _text(ai, "activity_id") == activity_id
                ),
                "",
            )
            findings.append(
                _finding(
                    "citation_quality",
                    "actual_ai_use",
                    "Qualité des citations à renforcer",
                    "warning",
                    [linked_ai, activity_id],
                    f"{round(rate * 100, 1)} % des réponses évaluées sont sans citation valide.",
                    {
                        "invalid_citations": _clean(
                            _number(invalid_citations, "Valeur")
                        ),
                        "evaluations": _clean(_number(evaluations, "Valeur")),
                        "invalid_rate": round(rate, 4),
                    },
                    "Renforcer l'évaluation des réponses et le contrôle des sources.",
                    ["Seuil qualité validé", "Contrôle de citation instrumenté"],
                    _combine_evidence(
                        _evidence(invalid_citations, "Mesure", "Valeur"),
                        _evidence(evaluations, "Mesure", "Valeur"),
                    ),
                )
            )

    extracts_by_source = _group(extracts, "source_id")
    for source_id, source_extracts in extracts_by_source.items():
        pending = next(
            (
                row
                for row in source_extracts
                if _normalize(_text(row, "Champ")) == "qualification"
                and "attente" in _normalize(_text(row, "Valeur synthétique"))
            ),
            None,
        )
        if pending is None:
            continue
        joined_values = " ".join(
            _text(row, "Valeur synthétique") for row in source_extracts
        )
        ai_match = re.search(r"AI-\d{3}", joined_values)
        ai_id = ai_match.group(0) if ai_match else ""
        findings.append(
            _finding(
                "qualification_incomplete",
                "transformation_opportunities",
                "Qualification incomplète",
                "high",
                [ai_id],
                _text(pending, "Valeur synthétique"),
                {"source_id": source_id, "qualification_status": "pending"},
                "Conserver le point ouvert et ne déduire aucune conformité par défaut.",
                ["Revue juridique terminée", "Décision de conformité tracée"],
                _combine_evidence(
                    *[
                        _evidence(row, "Champ", "Valeur synthétique")
                        for row in source_extracts
                    ]
                ),
            )
        )

    return [
        {**finding, "id": f"FIND-{index:03d}"}
        for index, finding in enumerate(findings, start=1)
    ]


def _ai_record(
    row: SourceRow,
    *,
    activity_by_id: dict[str, SourceRow],
    application_by_id: dict[str, SourceRow],
    value_by_ai: dict[str, SourceRow],
    costs_by_ai: dict[str, list[SourceRow]],
) -> dict[str, object]:
    ai_id = _text(row, "ai_id")
    activity = activity_by_id.get(_text(row, "activity_id"))
    application = application_by_id.get(_text(row, "application_id"))
    value = value_by_ai.get(ai_id)
    licenses = _number(row, "Licences / comptes")
    active = _number(row, "Actifs mensuels")
    return {
        "id": ai_id,
        "name": _text(row, "IA / fonction fictive"),
        "activity_id": _text(row, "activity_id"),
        "activity": _text(activity, "Activité") if activity else "",
        "application_id": _text(row, "application_id"),
        "application": _text(application, "Application fictive") if application else "",
        "category": _text(row, "Catégorie"),
        "status": _text(row, "État"),
        "observed_delegation": _clean(_number(row, "D observé")),
        "authorized_delegation": _clean(_number(row, "D autorisé")),
        "proposed_target_delegation": _clean(_number(row, "D cible proposé")),
        "licensed_accounts": _clean(licenses),
        "monthly_active_accounts": _clean(active),
        "activation_rate": round(active / licenses, 4) if licenses else None,
        "model": _text(row, "Modèle"),
        "usage_evidence": _text(row, "Preuve usage"),
        "monthly_cost_eur": _clean(
            sum(_number(cost, "Montant EUR") for cost in costs_by_ai.get(ai_id, []))
        ),
        "hours_released_simulated": _clean(
            _number(value, "Heures libérées simulées") if value else 0
        ),
        "budget_savings_eur": _clean(
            _number(value, "Économie budgétaire EUR") if value else 0
        ),
        "avoided_loss_estimate_eur": _clean(
            _number(value, "Perte évitée estimée EUR") if value else 0
        ),
        "attributed_revenue_estimate_eur": _clean(
            _number(value, "Revenu attribué estimé EUR") if value else 0
        ),
        "value_method_limit": _text(value, "Méthode / limite") if value else "",
        "source_id": _text(row, "source_id"),
        "evidence": _combine_evidence(
            _evidence(
                row,
                "IA / fonction fictive",
                "activity_id",
                "application_id",
                "État",
                "D observé",
                "D autorisé",
                "Licences / comptes",
                "Actifs mensuels",
                "Modèle",
                "Preuve usage",
            ),
            (
                _evidence(
                    value,
                    "Heures libérées simulées",
                    "Économie budgétaire EUR",
                    "Perte évitée estimée EUR",
                    "Revenu attribué estimé EUR",
                )
                if value
                else []
            ),
            *[
                _evidence(cost, "Poste", "Montant EUR")
                for cost in costs_by_ai.get(ai_id, [])
            ],
        ),
    }


def _strategic_depth(relations: list[SourceRow]) -> dict[str, object]:
    relation_types = {_normalize(_text(row, "Relation")) for row in relations}
    expected = {
        "objective_to_capability": "aligns with objective",
        "capability_to_activity": "performed through capability",
        "customer_journey_to_activity": "part of customer journey",
        "ai_use_to_objective": "contributes to objective",
    }
    missing = [
        label for label, relation in expected.items() if relation not in relation_types
    ]
    return {
        "status": "esquissée" if missing else "documentée",
        "missing_links": missing,
        "assessment": (
            "Les activités et usages IA sont reliés, mais les objectifs, capacités "
            "métier et parcours clients ne disposent pas encore de liens explicites."
            if missing
            else "Les liens stratégiques attendus sont présents."
        ),
        "next_step": (
            "Collecter puis valider les objectifs de l'assureur, les capacités métier "
            "et les parcours clients avant de qualifier une transformation stratégique."
        ),
    }


def _map_payload(
    map_id: str,
    *,
    summary: dict[str, object],
    content: dict[str, object],
    findings: list[dict[str, object]],
) -> dict[str, object]:
    definition = next(item for item in _MAP_DEFINITIONS if item[0] == map_id)
    return {
        "id": map_id,
        "title": definition[1],
        "question": definition[2],
        "summary": summary,
        "content": content,
        "finding_ids": [finding.get("id") for finding in findings],
    }


def _relation_record(row: SourceRow) -> dict[str, object]:
    return {
        "id": _text(row, "relation_id"),
        "source": _text(row, "Objet source"),
        "relation": _text(row, "Relation"),
        "target": _text(row, "Objet cible"),
        "source_id": _text(row, "Preuve source_id"),
        "evidence": _evidence(
            row, "Objet source", "Relation", "Objet cible", "Preuve source_id"
        ),
    }


def _finding(
    finding_type: str,
    map_id: str,
    title: str,
    severity: str,
    objects: list[str],
    statement: str,
    measures: dict[str, object],
    recommended_action: str,
    conditions: list[str],
    evidence: list[dict[str, str]],
) -> dict[str, object]:
    return {
        "type": finding_type,
        "map_id": map_id,
        "title": title,
        "severity": severity,
        "objects": [item for item in objects if item],
        "statement": statement,
        "measures": measures,
        "recommended_action": recommended_action,
        "conditions": conditions,
        "confidence": "élevée" if evidence else "inconnue",
        "evidence": evidence,
    }


def _rows(table: SourceTable, required_id: str) -> list[SourceRow]:
    rows = [row for row in table.rows if _text(row, required_id)]
    if not rows:
        raise EnterpriseMapError(
            f"La feuille {table.sheet_name} ne contient aucune donnée utile."
        )
    return rows


def _index(rows: list[SourceRow], key: str) -> dict[str, SourceRow]:
    return {_text(row, key): row for row in rows if _text(row, key)}


def _group(rows: list[SourceRow], key: str) -> dict[str, list[SourceRow]]:
    result: dict[str, list[SourceRow]] = defaultdict(list)
    for row in rows:
        value = _text(row, key)
        if value:
            result[value].append(row)
    return dict(result)


def _group_dicts(
    rows: list[dict[str, object]], key: str
) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        result[str(row.get(key, ""))].append(row)
    return dict(result)


def _metric_matching(rows: list[SourceRow], pattern: str) -> SourceRow | None:
    normalized_pattern = _normalize(pattern)
    return next(
        (row for row in rows if normalized_pattern in _normalize(_text(row, "Mesure"))),
        None,
    )


def _text(row: SourceRow | None, key: str) -> str:
    if row is None:
        return ""
    value = row.values.get(key)
    return "" if value is None else str(value).strip()


def _number(row: SourceRow | None, key: str) -> float:
    if row is None:
        return 0.0
    value = row.values.get(key)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if value is None or not str(value).strip():
        return 0.0
    normalized = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return 0.0


def _optional_number(row: SourceRow | None, key: str) -> int | float | None:
    if row is None or row.values.get(key) in (None, ""):
        return None
    return _clean(_number(row, key))


def _clean(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(float(value), 4)


def _evidence(row: SourceRow | None, *keys: str) -> list[dict[str, str]]:
    if row is None:
        return []
    return [
        evidence.to_dict()
        for key in keys
        if (evidence := row.evidence.get(key)) is not None
    ]


def _combine_evidence(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for evidence in (item for group in groups for item in group):
        key = (evidence.get("file", ""), evidence.get("locator", ""))
        if key not in seen:
            seen.add(key)
            result.append(evidence)
    return result


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())


def _priority_from_severity(severity: str) -> str:
    return {"critical": "P0", "high": "P0", "warning": "P1", "info": "P2"}.get(
        severity, "P2"
    )
