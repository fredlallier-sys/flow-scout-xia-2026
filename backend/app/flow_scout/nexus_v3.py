"""Contrat d'alimentation Flow Scout vers Flow Atlas v3.

La version 3 conserve les tables NEXUS v2, puis ajoute un modèle canonique
objets-relations-mesures-preuves. Les inconnues restent vides et deviennent des
questions maïeutiques : le moteur ne complète jamais un fait absent.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Callable

from app.flow_scout.nexus import NEXUS_V2_HEADERS

STRATEGIC_CATEGORIES = (
    "Confort",
    "Productivité",
    "Sécurisation",
    "Go-to-market",
    "Produit",
    "Stratégique",
)

MAIEUTIC_JOURNEY = ("Situer", "Comprendre", "Évaluer", "Déléguer", "Prioriser")

NEXUS_V3_HEADERS: dict[str, tuple[str, ...]] = {
    "Atlas Objects": (
        "object_id",
        "object_type",
        "name",
        "status",
        "category",
        "owner_id",
        "parent_id",
        "source_system_id",
        "evidence_ids",
        "confidence",
        "attributes_json",
    ),
    "Atlas Relations": (
        "relation_id",
        "source_object_id",
        "relation_type",
        "target_object_id",
        "source_system_id",
        "evidence_ids",
        "confidence",
        "attributes_json",
    ),
    "Atlas Measures": (
        "measure_id",
        "object_id",
        "measure_type",
        "name",
        "value",
        "unit",
        "period",
        "method",
        "status",
        "evidence_ids",
        "confidence",
        "attributes_json",
    ),
    "Atlas Findings": (
        "finding_id",
        "map_id",
        "finding_type",
        "title",
        "statement",
        "severity",
        "confidence",
        "status",
        "object_ids",
        "measures_json",
        "conditions",
        "recommended_action",
        "evidence_ids",
        "question_ids",
    ),
    "Atlas Evidence": (
        "evidence_id",
        "object_id",
        "file",
        "sheet",
        "cell",
        "locator",
        "quote",
        "evidence_type",
        "captured_at",
    ),
    "Atlas Questions": (
        "question_id",
        "journey_stage",
        "rule_id",
        "map_id",
        "target_object_id",
        "question",
        "why_asked",
        "answer_type",
        "allowed_values",
        "decision_blocked",
        "evidence_required",
        "priority",
        "status",
        "answer",
        "answered_by",
        "answered_at",
        "evidence_ids",
    ),
    "Atlas Rules": (
        "rule_id",
        "name",
        "scope",
        "severity",
        "purpose",
        "success_condition",
        "journey_stage",
        "question_template",
        "remediation",
    ),
    "Import Control": (
        "control_id",
        "rule_id",
        "status",
        "target_object_id",
        "observed",
        "expected",
        "issue",
        "required_action",
        "question_id",
        "evidence_ids",
        "checked_at",
    ),
}

NEXUS_V3_SHEET_ORDER = (
    "Lisez-moi",
    "Use cases",
    "Agents",
    "Sources",
    "Briques",
    "Transition Board",
    "Tasks_Roles_Skills",
    "NEXUS V2 Readme",
    "NEXUS V3 Readme",
    "Atlas Objects",
    "Atlas Relations",
    "Atlas Measures",
    "Atlas Findings",
    "Atlas Evidence",
    "Atlas Questions",
    "Atlas Rules",
    "Import Control",
)

ATLAS_RULES = (
    ("R-001", "Identité stable", "Tous les objets", "Bloquant", "Éviter les doublons et permettre le suivi dans le temps.", "Chaque objet possède un identifiant stable et unique.", "Situer", "Quel identifiant métier stable doit être conservé ?", "Corriger ou confirmer l'identifiant avant import."),
    ("R-002", "Travail attribué", "Activités", "Bloquant", "Relier le travail réel à une équipe et à un persona.", "Chaque activité possède une équipe et un persona responsables.", "Situer", "Qui réalise réellement cette activité ?", "Confirmer l'équipe et le persona."),
    ("R-003", "Usage IA contextualisé", "Usages IA", "Bloquant", "Éviter une liste d'IA sans contexte de travail.", "Chaque usage IA est relié à une activité et à une application.", "Comprendre", "Dans quelle activité et quel système cet usage intervient-il ?", "Créer ou valider les liens manquants."),
    ("R-004", "Délégation autorisée", "Usages IA", "Bloquant", "Maintenir l'autonomie observée dans la délégation validée.", "Le niveau observé ne dépasse pas le niveau autorisé.", "Déléguer", "Quel niveau d'autonomie est acceptable et quel contrôle humain est requis ?", "Ramener l'autonomie au niveau autorisé ou faire valider une nouvelle délégation."),
    ("R-005", "Traçabilité des preuves", "Objets et constats", "Bloquant", "Rendre chaque constat vérifiable.", "Chaque constat et objet critique possède au moins une preuve localisable.", "Comprendre", "Quelle source permet de vérifier ce point ?", "Ajouter la source et son emplacement exact."),
    ("R-006", "Valeurs économiques séparées", "Mesures de valeur", "Bloquant", "Ne pas confondre temps libéré, économie, risque évité et revenu.", "Chaque type de valeur possède une mesure et une méthode distinctes.", "Évaluer", "Quelle valeur est démontrée et par quelle méthode ?", "Séparer les catégories de valeur et documenter leur méthode."),
    ("R-007", "Adoption mesurée", "Usages IA", "Important", "Distinguer licences achetées et usage réel.", "Les comptes actifs et licenciés sont mesurés sur une période explicite.", "Évaluer", "Quel est l'usage réel sur la période observée ?", "Mesurer l'activation et expliquer les écarts."),
    ("R-008", "Compétences alignées", "Activités assistées par IA", "Bloquant", "Vérifier que les personnes peuvent utiliser et contrôler l'IA.", "Compétences actuelles, attendues, écart et action de développement sont validés.", "Comprendre", "Quelles compétences faut-il pour utiliser et contrôler cet usage IA ?", "Faire qualifier l'écart par le métier et les RH."),
    ("R-009", "Recouvrements arbitrés", "Portefeuille IA", "Important", "Éviter les doublons fonctionnels et les coûts redondants.", "Chaque recouvrement possède un arbitrage documenté.", "Prioriser", "Faut-il consolider, différencier ou arrêter ces usages qui se recouvrent ?", "Documenter l'arbitrage de portefeuille."),
    ("R-010", "Qualité des données et réponses", "Sources et usages", "Bloquant", "Éviter des décisions fondées sur des données incomplètes ou des sorties non fiables.", "Les seuils de qualité sont définis, mesurés et acceptés.", "Évaluer", "Quel niveau de qualité est acceptable et comment est-il contrôlé ?", "Définir le seuil, le contrôle et le responsable."),
    ("R-011", "Alignement stratégique", "Transformation", "Important", "Relier l'IA aux objectifs, capacités métier et parcours clients.", "Les quatre liens stratégiques sont explicités et validés.", "Prioriser", "Quel objectif, quelle capacité ou quel parcours cet usage sert-il ?", "Collecter et valider les liens stratégiques manquants."),
    ("R-012", "Valeur démontrée", "Usages IA", "Important", "Séparer bénéfice observable et hypothèse de valeur.", "La valeur annoncée possède une mesure, une période, une méthode et une preuve.", "Évaluer", "Quel résultat mesuré justifie la poursuite de cet usage ?", "Mesurer avant d'industrialiser ou reformuler l'hypothèse."),
    ("R-013", "Qualification fournisseur et modèle", "Usages IA", "Bloquant", "Éviter un usage non maîtrisé du modèle ou du fournisseur.", "Modèle, fournisseur, statut et conditions d'usage sont confirmés.", "Situer", "Quel modèle, quel fournisseur et quelles conditions encadrent cet usage ?", "Qualifier le service et ses conditions avant import décisionnel."),
    ("R-014", "Qualification maïeutique", "Questions ouvertes", "Bloquant", "Faire confirmer les informations qui conditionnent les arbitrages.", "Toutes les questions bloquantes sont répondues et validées.", "Prioriser", "La compréhension proposée est-elle exacte et suffisante pour décider ?", "Résoudre les questions bloquantes puis confirmer la synthèse."),
    ("R-015", "Finalité qualifiée", "Activités et usages IA", "Important", "Conserver les six finalités Flow Scout.", "Chaque catégorie appartient à la grille Confort, Productivité, Sécurisation, Go-to-market, Produit ou Stratégique.", "Situer", "Quelle est la finalité principale et, si nécessaire, secondaire ?", "Choisir et confirmer une finalité de la grille Flow Scout."),
)


def build_nexus_v3_payload(report: dict[str, object]) -> dict[str, object]:
    """Construit le payload Atlas v3 à partir des sept cartes Flow Scout."""
    maps = {item["id"]: item for item in _dict_list(report.get("maps"))}
    human = _content(maps, "human_work")
    decisions_map = _content(maps, "decisions_responsibilities")
    knowledge = _content(maps, "knowledge_data")
    tools = _content(maps, "tools_dependencies")
    actual_ai = _content(maps, "actual_ai_use")
    transformation = _content(maps, "transformation_opportunities")

    teams = _dict_list(human.get("teams"))
    activities = _dict_list(human.get("activities"))
    decisions = _dict_list(decisions_map.get("decisions"))
    delegations = _dict_list(decisions_map.get("delegations"))
    sources = _dict_list(knowledge.get("sources"))
    applications = _dict_list(tools.get("applications"))
    ais = _dict_list(actual_ai.get("ai_usages"))
    opportunities = _dict_list(transformation.get("opportunities"))
    findings = _dict_list(report.get("findings"))
    relations = _dict_list(_as_dict(report.get("cross_map_links")).get("items"))
    dataset = _as_dict(report.get("dataset"))
    checked_at = str(dataset.get("as_of", ""))

    evidence_rows: list[dict[str, object]] = []
    evidence_counter = 0

    def register_evidence(object_id: str, evidence: object) -> str:
        nonlocal evidence_counter
        ids: list[str] = []
        for item in _dict_list(evidence):
            evidence_counter += 1
            evidence_id = f"EVID-{evidence_counter:05d}"
            ids.append(evidence_id)
            evidence_rows.append(
                _ordered(
                    "Atlas Evidence",
                    {
                        "evidence_id": evidence_id,
                        "object_id": object_id,
                        "file": item.get("file", dataset.get("file", "")),
                        "sheet": item.get("sheet", ""),
                        "cell": item.get("cell", ""),
                        "locator": item.get("locator", ""),
                        "quote": item.get("quote", ""),
                        "evidence_type": "source_cell",
                        "captured_at": checked_at,
                    },
                )
            )
        return ";".join(ids)

    object_rows: list[dict[str, object]] = []
    measure_rows: list[dict[str, object]] = []
    relation_rows: list[dict[str, object]] = []
    measure_counter = 0
    relation_counter = 0

    def add_object(
        item: dict[str, object],
        object_type: str,
        *,
        name_key: str = "name",
        status: object = "",
        category: object = "",
        owner_id: object = "",
        parent_id: object = "",
        source_system_id: object = "",
        attributes: dict[str, object] | None = None,
    ) -> None:
        object_id = str(item.get("id", ""))
        evidence_ids = register_evidence(object_id, item.get("evidence"))
        object_rows.append(
            _ordered(
                "Atlas Objects",
                {
                    "object_id": object_id,
                    "object_type": object_type,
                    "name": item.get(name_key, ""),
                    "status": status,
                    "category": category,
                    "owner_id": owner_id,
                    "parent_id": parent_id,
                    "source_system_id": source_system_id,
                    "evidence_ids": evidence_ids,
                    "confidence": "source",
                    "attributes_json": _json(attributes or {}),
                },
            )
        )

    def add_measure(
        object_id: str,
        measure_type: str,
        name: str,
        value: object,
        unit: str,
        *,
        method: str,
        evidence_ids: str,
        status: str = "observed",
        attributes: dict[str, object] | None = None,
    ) -> None:
        nonlocal measure_counter
        if value is None or value == "":
            return
        measure_counter += 1
        measure_rows.append(
            _ordered(
                "Atlas Measures",
                {
                    "measure_id": f"MEAS-{measure_counter:05d}",
                    "object_id": object_id,
                    "measure_type": measure_type,
                    "name": name,
                    "value": value,
                    "unit": unit,
                    "period": dataset.get("period", ""),
                    "method": method,
                    "status": status,
                    "evidence_ids": evidence_ids,
                    "confidence": "source" if evidence_ids else "derived",
                    "attributes_json": _json(attributes or {}),
                },
            )
        )

    personas: dict[str, dict[str, object]] = {}
    for team in teams:
        add_object(
            team,
            "team",
            parent_id="",
            attributes={"persona_id": team.get("persona_id", "")},
        )
        persona_id = str(team.get("persona_id", ""))
        if persona_id and persona_id not in personas:
            personas[persona_id] = {
                "id": persona_id,
                "name": team.get("persona", ""),
                "evidence": team.get("evidence", []),
                "team_id": team.get("id", ""),
            }
        evidence_ids = object_rows[-1]["evidence_ids"]
        add_measure(str(team.get("id", "")), "capacity", "Effectif", team.get("headcount_fte"), "ETP", method="Effectif déclaré", evidence_ids=str(evidence_ids))
    for persona in personas.values():
        add_object(persona, "persona", parent_id=persona.get("team_id", ""))

    for activity in activities:
        add_object(
            activity,
            "activity",
            category=activity.get("category", ""),
            owner_id=activity.get("persona_id", ""),
            parent_id=activity.get("team_id", ""),
            source_system_id=activity.get("application_id", ""),
            attributes={"process_id": activity.get("process_id", "")},
        )
        evidence_ids = str(object_rows[-1]["evidence_ids"])
        activity_id = str(activity.get("id", ""))
        add_measure(activity_id, "volume", "Volume mensuel", activity.get("monthly_volume"), "tâches/mois", method="Volume source", evidence_ids=evidence_ids)
        add_measure(activity_id, "duration", "Temps avant", activity.get("minutes_per_task_before"), "minutes/tâche", method="Temps source", evidence_ids=evidence_ids)
        add_measure(activity_id, "workload", "Charge mensuelle avant", activity.get("monthly_workload_hours"), "heures/mois", method="Volume × durée / 60", evidence_ids=evidence_ids, status="derived")

    for decision in decisions:
        add_object(
            decision,
            "decision",
            name_key="decision",
            owner_id=decision.get("responsible_persona_id", ""),
            parent_id=decision.get("activity_id", ""),
            attributes={"rule": decision.get("rule", ""), "threshold": decision.get("threshold"), "unit": decision.get("unit", "")},
        )
    for source in sources:
        add_object(
            source,
            "knowledge_source",
            status=source.get("status", ""),
            category=source.get("family", ""),
            attributes={"owner": source.get("owner", ""), "collection_mode": source.get("collection_mode", ""), "priority": source.get("priority", "")},
        )
    for application in applications:
        add_object(
            application,
            "application",
            status=application.get("status", ""),
            category=application.get("domain", ""),
            source_system_id=application.get("source_id", ""),
            attributes={"vendor": application.get("vendor", ""), "hosting": application.get("hosting", "")},
        )
    for ai in ais:
        add_object(
            ai,
            "ai_usage",
            status=ai.get("status", ""),
            category=ai.get("category", ""),
            parent_id=ai.get("activity_id", ""),
            source_system_id=ai.get("application_id", ""),
            attributes={"model": ai.get("model", ""), "usage_evidence": ai.get("usage_evidence", ""), "value_method_limit": ai.get("value_method_limit", "")},
        )
        evidence_ids = str(object_rows[-1]["evidence_ids"])
        ai_id = str(ai.get("id", ""))
        for measure_type, name, key, unit, method in (
            ("adoption", "Comptes licenciés", "licensed_accounts", "comptes", "Mesure d'adoption"),
            ("adoption", "Comptes actifs mensuels", "monthly_active_accounts", "comptes", "Mesure d'adoption"),
            ("adoption", "Taux d'activation", "activation_rate", "ratio", "Actifs / licenciés"),
            ("cost", "Coût mensuel", "monthly_cost_eur", "EUR/mois", "Coût déclaré"),
            ("time", "Temps libéré simulé", "hours_released_simulated", "heures/mois", "Simulation déclarée"),
            ("budget_saving", "Économie budgétaire", "budget_savings_eur", "EUR/mois", "Économie déclarée"),
            ("avoided_loss", "Risque évité estimé", "avoided_loss_estimate_eur", "EUR/mois", "Estimation déclarée"),
            ("attributed_revenue", "Revenu attribué estimé", "attributed_revenue_estimate_eur", "EUR/mois", "Estimation déclarée"),
            ("delegation", "Délégation observée", "observed_delegation", "niveau", "Observation"),
            ("delegation", "Délégation autorisée", "authorized_delegation", "niveau", "Règle métier"),
            ("delegation", "Délégation cible proposée", "proposed_target_delegation", "niveau", "Proposition à valider"),
        ):
            add_measure(ai_id, measure_type, name, ai.get(key), unit, method=method, evidence_ids=evidence_ids, status="estimated" if "estimé" in name.lower() or "simulé" in name.lower() else "observed")
    for opportunity in opportunities:
        item = dict(opportunity)
        item["id"] = opportunity.get("id", "")
        item["name"] = opportunity.get("title", "")
        add_object(
            item,
            "transformation_opportunity",
            status="open",
            category=opportunity.get("priority", ""),
            attributes={"finding_id": opportunity.get("finding_id", ""), "objects": opportunity.get("objects", []), "conditions": opportunity.get("conditions", ""), "action": opportunity.get("action", "")},
        )

    for relation in relations:
        relation_counter += 1
        relation_id = str(relation.get("id", "")) or f"REL-{relation_counter:05d}"
        evidence_ids = register_evidence(relation_id, relation.get("evidence"))
        relation_rows.append(
            _ordered(
                "Atlas Relations",
                {
                    "relation_id": relation_id,
                    "source_object_id": relation.get("source", ""),
                    "relation_type": relation.get("relation", ""),
                    "target_object_id": relation.get("target", ""),
                    "source_system_id": relation.get("source_id", ""),
                    "evidence_ids": evidence_ids,
                    "confidence": "source",
                    "attributes_json": "{}",
                },
            )
        )

    question_rows, control_rows, finding_questions = _build_controls_and_questions(
        activities=activities,
        ais=ais,
        delegations=delegations,
        findings=findings,
        strategic_depth=_as_dict(report.get("strategic_depth")),
        object_rows=object_rows,
        checked_at=checked_at,
        register_evidence=register_evidence,
    )

    finding_rows = []
    for finding in findings:
        finding_id = str(finding.get("id", ""))
        finding_rows.append(
            _ordered(
                "Atlas Findings",
                {
                    "finding_id": finding_id,
                    "map_id": finding.get("map_id", ""),
                    "finding_type": finding.get("type", ""),
                    "title": finding.get("title", ""),
                    "statement": finding.get("statement", ""),
                    "severity": finding.get("severity", ""),
                    "confidence": finding.get("confidence", ""),
                    "status": "open",
                    "object_ids": ";".join(str(value) for value in finding.get("objects", []) if value),
                    "measures_json": _json(finding.get("measures", {})),
                    "conditions": _cell_value(finding.get("conditions", "")),
                    "recommended_action": finding.get("recommended_action", ""),
                    "evidence_ids": register_evidence(finding_id, finding.get("evidence")),
                    "question_ids": ";".join(finding_questions.get(finding_id, [])),
                },
            )
        )

    v2_sheets = _build_v2_sheets(activities, applications, ais, findings, personas)
    extended_sheets: dict[str, dict[str, object]] = {
        **v2_sheets,
        "Atlas Objects": _sheet("Atlas Objects", object_rows),
        "Atlas Relations": _sheet("Atlas Relations", relation_rows),
        "Atlas Measures": _sheet("Atlas Measures", measure_rows),
        "Atlas Findings": _sheet("Atlas Findings", finding_rows),
        "Atlas Evidence": _sheet("Atlas Evidence", evidence_rows),
        "Atlas Questions": _sheet("Atlas Questions", question_rows),
        "Atlas Rules": _sheet("Atlas Rules", [_ordered("Atlas Rules", _rule_dict(rule)) for rule in ATLAS_RULES]),
        "Import Control": _sheet("Import Control", control_rows),
    }
    return {
        "schema_version": "flow-atlas-import-v3",
        "source_report_version": report.get("schema_version", ""),
        "dataset": dataset,
        "maieutic_journey": list(MAIEUTIC_JOURNEY),
        "sheets": extended_sheets,
        "compatibility": {
            "nexus_v2_preserved": True,
            "original_v2_headers_preserved": True,
            "canonical_model": "objects-relations-measures-findings-evidence-questions-rules-controls",
            "unknown_values_policy": "blank_and_question_never_invent",
        },
    }


def _build_controls_and_questions(
    *,
    activities: list[dict[str, object]],
    ais: list[dict[str, object]],
    delegations: list[dict[str, object]],
    findings: list[dict[str, object]],
    strategic_depth: dict[str, object],
    object_rows: list[dict[str, object]],
    checked_at: str,
    register_evidence: Callable[[str, object], str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, list[str]]]:
    questions: list[dict[str, object]] = []
    controls: list[dict[str, object]] = []
    finding_questions: dict[str, list[str]] = defaultdict(list)
    question_counter = 0
    control_counter = 0

    def add_question(
        *,
        stage: str,
        rule_id: str,
        map_id: str,
        target: str,
        question: str,
        why: str,
        priority: str,
        blocked: bool,
        answer_type: str = "texte",
        allowed: str = "",
        evidence_required: bool = True,
        evidence_ids: str = "",
        finding_id: str = "",
    ) -> str:
        nonlocal question_counter
        question_counter += 1
        question_id = f"Q-{question_counter:04d}"
        questions.append(
            _ordered(
                "Atlas Questions",
                {
                    "question_id": question_id,
                    "journey_stage": stage,
                    "rule_id": rule_id,
                    "map_id": map_id,
                    "target_object_id": target,
                    "question": question,
                    "why_asked": why,
                    "answer_type": answer_type,
                    "allowed_values": allowed,
                    "decision_blocked": "Oui" if blocked else "Non",
                    "evidence_required": "Oui" if evidence_required else "Non",
                    "priority": priority,
                    "status": "Open",
                    "answer": "",
                    "answered_by": "",
                    "answered_at": "",
                    "evidence_ids": evidence_ids,
                },
            )
        )
        if finding_id:
            finding_questions[finding_id].append(question_id)
        return question_id

    def add_control(
        rule_id: str,
        status: str,
        target: str,
        observed: object,
        expected: object,
        issue: str,
        action: str,
        *,
        question_id: str = "",
        evidence_ids: str = "",
    ) -> None:
        nonlocal control_counter
        control_counter += 1
        controls.append(
            _ordered(
                "Import Control",
                {
                    "control_id": f"CTRL-{control_counter:04d}",
                    "rule_id": rule_id,
                    "status": status,
                    "target_object_id": target,
                    "observed": _cell_value(observed),
                    "expected": _cell_value(expected),
                    "issue": issue,
                    "required_action": action,
                    "question_id": question_id,
                    "evidence_ids": evidence_ids,
                    "checked_at": checked_at,
                },
            )
        )

    ids = [str(row.get("object_id", "")) for row in object_rows]
    duplicate_ids = sorted({value for value in ids if value and ids.count(value) > 1})
    add_control("R-001", "FAIL" if duplicate_ids else "PASS", "PORTFOLIO", ";".join(duplicate_ids) or f"{len(ids)} identifiants uniques", "Aucun doublon", "Identifiants dupliqués" if duplicate_ids else "Aucun doublon détecté", "Corriger les identifiants" if duplicate_ids else "Aucune action")

    unassigned = [str(item.get("id", "")) for item in activities if not item.get("team_id") or not item.get("persona_id")]
    add_control("R-002", "FAIL" if unassigned else "PASS", "ACTIVITIES", ";".join(unassigned) or f"{len(activities)} activités attribuées", "Équipe et persona présents", "Attribution incomplète" if unassigned else "Attribution complète", "Qualifier les responsables" if unassigned else "Aucune action")

    uncontextualized = [str(item.get("id", "")) for item in ais if not item.get("activity_id") or not item.get("application_id")]
    add_control("R-003", "FAIL" if uncontextualized else "PASS", "AI-USAGES", ";".join(uncontextualized) or f"{len(ais)} usages contextualisés", "Activité et application présentes", "Contexte incomplet" if uncontextualized else "Contexte complet", "Créer les liens manquants" if uncontextualized else "Aucune action")

    for delegation in delegations:
        if bool(delegation.get("within_authority", True)):
            continue
        ai_id = str(delegation.get("ai_id", ""))
        delegation_finding = next(
            (
                item
                for item in findings
                if item.get("type") == "delegation_overrun"
                and ai_id in item.get("objects", [])
            ),
            {},
        )
        finding_id = str(delegation_finding.get("id", ""))
        evidence_ids = register_evidence(ai_id, delegation.get("evidence"))
        question_id = add_question(
            stage="Déléguer",
            rule_id="R-004",
            map_id="decisions_responsibilities",
            target=ai_id,
            question=(
                f"Pour {ai_id}, confirmez-vous la règle suivante : l'IA prépare le paiement, "
                "mais une personne doit le vérifier et l'autoriser avant son envoi ?"
            ),
            why=(
                str(delegation_finding.get("statement", ""))
                or "L'IA a réalisé une action qui exigeait l'accord préalable d'une personne."
            ),
            priority="P0",
            blocked=True,
            answer_type="niveau_et_controle",
            allowed="0;1;2;3;4",
            evidence_ids=evidence_ids,
            finding_id=finding_id,
        )
        add_control(
            "R-004",
            "FAIL",
            ai_id,
            delegation.get("observed_level"),
            f"≤ {delegation.get('authorized_level')}",
            "L'IA agit sans la validation humaine exigée",
            "Bloquer le paiement automatique : l'IA prépare, une personne vérifie et autorise",
            question_id=question_id,
            evidence_ids=evidence_ids,
        )

    without_evidence = [
        str(row.get("object_id", ""))
        for row in object_rows
        if not row.get("evidence_ids")
    ]
    add_control(
        "R-005",
        "FAIL" if without_evidence else "PASS",
        "PORTFOLIO",
        ";".join(without_evidence) or f"{len(object_rows)} objets sourcés",
        "Au moins une preuve pour chaque objet",
        "Objets sans preuve" if without_evidence else "Traçabilité source-cellule conservée",
        "Ajouter les preuves manquantes" if without_evidence else "Aucune action",
    )
    add_control("R-006", "PASS", "VALUE-MEASURES", "Temps, économies, pertes évitées et revenus sont séparés", "Types de valeur distincts", "Aucune agrégation en bénéfice net", "Aucune action")

    ai_activity_ids = {str(item.get("activity_id", "")) for item in ais if item.get("activity_id")}
    activity_by_id = {str(item.get("id", "")): item for item in activities}
    for activity_id in sorted(ai_activity_ids):
        activity = activity_by_id.get(activity_id, {})
        question_id = add_question(
            stage="Comprendre",
            rule_id="R-008",
            map_id="human_work",
            target=activity_id,
            question=f"Pour « {activity.get('name', activity_id)} », quelles compétences faut-il pour utiliser, contrôler et contester l'IA ?",
            why="Le jeu source ne décrit pas les compétences actuelles, les compétences attendues ni leur écart.",
            priority="P1",
            blocked=True,
            answer_type="competences_ecart_action",
        )
        add_control("R-008", "OPEN", activity_id, "Compétences non collectées", "Compétences actuelles + attendues + écart + action", "Alignement des compétences à confirmer", "Faire répondre le métier et les RH", question_id=question_id)

    finding_rule = {
        "functional_overlap": ("R-009", "Prioriser", "P1", False, "Quel arbitrage faut-il prendre entre ces usages qui se recouvrent : consolider, différencier ou arrêter ?"),
        "low_adoption": ("R-007", "Évaluer", "P1", False, "Qu'est-ce qui explique l'écart entre licences achetées et usage réel, et quelle action doit-on tester ?"),
        "data_incompleteness": ("R-010", "Évaluer", "P0", True, "Quel seuil de complétude est acceptable et quel contrôle doit empêcher une décision insuffisamment documentée ?"),
        "citation_quality": ("R-010", "Évaluer", "P0", True, "Quel taux d'erreur de citation est acceptable et qui valide les réponses à risque ?"),
        "time_without_budget_savings": ("R-012", "Évaluer", "P1", False, "Le temps libéré produit-il une capacité supplémentaire, une meilleure qualité ou une économie mesurable ?"),
        "unqualified_usage": ("R-013", "Situer", "P0", True, "Quel modèle, quel fournisseur et quelles conditions d'usage encadrent réellement cet usage ?"),
        "qualification_incomplete": ("R-014", "Comprendre", "P0", True, "Quelle information ou validation manque encore pour qualifier cet usage ?"),
    }
    for finding in findings:
        finding_type = str(finding.get("type", ""))
        if finding_type == "delegation_overrun":
            continue
        spec = finding_rule.get(finding_type)
        if not spec:
            continue
        rule_id, stage, priority, blocked, question_text = spec
        finding_id = str(finding.get("id", ""))
        objects = [str(value) for value in finding.get("objects", []) if value]
        target = objects[0] if objects else finding_id
        evidence_ids = register_evidence(finding_id, finding.get("evidence"))
        question_id = add_question(stage=stage, rule_id=rule_id, map_id=str(finding.get("map_id", "")), target=target, question=question_text, why=str(finding.get("statement", finding.get("title", ""))), priority=priority, blocked=blocked, evidence_ids=evidence_ids, finding_id=finding_id)
        add_control(rule_id, "OPEN" if blocked else "WARN", target, finding.get("measures", {}), "Condition validée ou arbitrée", str(finding.get("title", "")), str(finding.get("recommended_action", "")), question_id=question_id, evidence_ids=evidence_ids)

    strategic_questions = {
        "objective_to_capability": "Quel objectif stratégique mesurable cette capacité métier doit-elle servir ?",
        "capability_to_activity": "Quelles activités contribuent réellement à cette capacité métier ?",
        "customer_journey_to_activity": "À quelle étape du parcours client cette activité contribue-t-elle ?",
        "ai_use_to_objective": "À quel objectif mesurable cet usage IA contribue-t-il, et par quel mécanisme ?",
    }
    for missing_link in strategic_depth.get("missing_links", []):
        question_id = add_question(stage="Prioriser", rule_id="R-011", map_id="transformation_opportunities", target=str(missing_link), question=strategic_questions.get(str(missing_link), f"Comment valider le lien stratégique {missing_link} ?"), why=str(strategic_depth.get("assessment", "Lien stratégique absent.")), priority="P1", blocked=False, answer_type="lien_et_indicateur")
        add_control("R-011", "OPEN", str(missing_link), "Lien absent", "Lien explicite et validé", "Profondeur stratégique encore esquissée", "Collecter puis faire confirmer le lien", question_id=question_id)

    invalid_categories = sorted({str(item.get("category", "")) for item in [*activities, *ais] if item.get("category") not in STRATEGIC_CATEGORIES})
    add_control("R-015", "FAIL" if invalid_categories else "PASS", "FINALITIES", ";".join(invalid_categories) or "Six catégories Flow Scout respectées", ";".join(STRATEGIC_CATEGORIES), "Finalité hors grille" if invalid_categories else "Finalités conformes", "Requalifier la finalité" if invalid_categories else "Aucune action")

    blocking = sum(row["decision_blocked"] == "Oui" for row in questions)
    add_control("R-014", "OPEN" if blocking else "PASS", "MAIEUTIC", f"{blocking} questions bloquantes ouvertes", "0 question bloquante ouverte", "Qualification incomplète" if blocking else "Qualification complète", "Répondre et valider les questions bloquantes" if blocking else "Aucune action")
    return questions, controls, finding_questions


def _build_v2_sheets(
    activities: list[dict[str, object]],
    applications: list[dict[str, object]],
    ais: list[dict[str, object]],
    findings: list[dict[str, object]],
    personas: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    application_by_id = {str(item.get("id", "")): item for item in applications}
    ai_by_activity: dict[str, list[str]] = defaultdict(list)
    for ai in ais:
        ai_by_activity[str(ai.get("activity_id", ""))].append(str(ai.get("id", "")))
    use_cases = []
    for ai in ais:
        app = application_by_id.get(str(ai.get("application_id", "")), {})
        observed = _number(ai.get("observed_delegation"))
        delegation_level = max(0, min(5, int(observed)))
        if delegation_level <= 1:
            ai_type = "Assistant"
        elif delegation_level <= 3:
            ai_type = "Copilote"
        else:
            ai_type = "Agent autonome"
        delegation_label = {
            0: "humain uniquement",
            1: "assistance",
            2: "préparation",
            3: "recommandation",
            4: "exécution supervisée",
            5: "autonomie encadrée",
        }[delegation_level]
        description = f"[D{delegation_level} · {delegation_label}]"
        details = f"{ai.get('activity', '')} — {ai.get('usage_evidence', '')}".strip(
            " —"
        )
        if details:
            description = f"{description} {details}"
        use_cases.append(
            _ordered_v2(
                "Use cases",
                {
                    "id": ai.get("id", ""),
                    "nom": ai.get("name", ""),
                    "domaine": _v2_domain(str(app.get("domain", ""))),
                    "type": ai_type,
                    "statut": _v2_status(str(ai.get("status", ""))),
                    "owner": "",
                    "entite": "",
                    "valeur": "",
                    "effort": "",
                    "risque": "",
                    "maturite": "",
                    "reutilisation": "",
                    "roi_keuros": "",
                    "utilisateurs": ai.get("monthly_active_accounts"),
                    "classe_ai_act": "",
                    "base_rgpd": "",
                    "dpia": "",
                    "humain_dans_boucle": "",
                    "source_id": ai.get("application_id", ""),
                    "briques": "",
                    "tags": ai.get("category", ""),
                    "description": description,
                },
            )
        )
    source_rows = [
        _ordered_v2(
            "Sources",
            {
                "id": app.get("id", ""),
                "nom": app.get("name", ""),
                "editeur": app.get("vendor", ""),
                "logo": "",
                "couleur": "",
                "statut": "À configurer",
                "protocole": "À confirmer",
                "cadence": "À confirmer",
            },
        )
        for app in applications
    ]
    task_rows = []
    for activity in activities:
        activity_id = str(activity.get("id", ""))
        persona = personas.get(str(activity.get("persona_id", "")), {})
        task_rows.append(
            _ordered_v2(
                "Tasks_Roles_Skills",
                {
                    "task_id": activity_id,
                    "tache": activity.get("name", ""),
                    "role": persona.get("name", activity.get("persona_id", "")),
                    "entite": activity.get("team_id", ""),
                    "use_case_id": ";".join(ai_by_activity.get(activity_id, [])),
                    "statut_travail": "Observé",
                    "potentiel_automation": "",
                    "criticite_humaine": "",
                    "competences_actuelles": "",
                    "competences_a_developper": "",
                    "niveau_ecart": "",
                    "formation_recommandee": "À qualifier par la maïeutique" if ai_by_activity.get(activity_id) else "",
                },
            )
        )
    transition_rows = []
    for finding in findings:
        objects = [str(value) for value in finding.get("objects", []) if value]
        transition_rows.append(
            _ordered_v2(
                "Transition Board",
                {
                    "decision_id": finding.get("id", ""),
                    "objet": objects[0] if objects else finding.get("title", ""),
                    "type_objet": finding.get("map_id", ""),
                    "decision": "À arbitrer",
                    "priorite": finding.get("severity", ""),
                    "sponsor": "",
                    "valeur": "",
                    "cout": "",
                    "adoption": "",
                    "impact_travail": finding.get("statement", ""),
                    "ecart_competence": "À qualifier",
                    "criticite_humaine": "",
                    "action_30j": finding.get("recommended_action", ""),
                    "action_60j": "",
                    "action_90j": "",
                    "kpi": "",
                },
            )
        )
    return {
        "Use cases": {"headers": list(NEXUS_V2_HEADERS["Use cases"]), "rows": use_cases},
        "Agents": {"headers": list(NEXUS_V2_HEADERS["Agents"]), "rows": []},
        "Sources": {"headers": list(NEXUS_V2_HEADERS["Sources"]), "rows": source_rows},
        "Briques": {"headers": list(NEXUS_V2_HEADERS["Briques"]), "rows": []},
        "Transition Board": {"headers": list(NEXUS_V2_HEADERS["Transition Board"]), "rows": transition_rows},
        "Tasks_Roles_Skills": {"headers": list(NEXUS_V2_HEADERS["Tasks_Roles_Skills"]), "rows": task_rows},
    }


def assert_nexus_v3_headers(payload: dict[str, object]) -> None:
    sheets = payload.get("sheets")
    if not isinstance(sheets, dict):
        raise ValueError("Le payload Atlas v3 ne contient pas de feuilles.")
    for sheet_name, expected in {**NEXUS_V2_HEADERS, **NEXUS_V3_HEADERS}.items():
        sheet = sheets.get(sheet_name)
        if not isinstance(sheet, dict) or sheet.get("headers") != list(expected):
            raise ValueError(f"Contrat Atlas v3 invalide pour la feuille {sheet_name}.")


def _content(maps: dict[str, dict[str, object]], map_id: str) -> dict[str, object]:
    return _as_dict(_as_dict(maps.get(map_id)).get("content"))


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _cell_value(value: object) -> object:
    if isinstance(value, (dict, list, tuple)):
        return _json(value)
    return value


def _ordered(sheet_name: str, values: dict[str, object]) -> dict[str, object]:
    return {header: values.get(header, "") for header in NEXUS_V3_HEADERS[sheet_name]}


def _ordered_v2(sheet_name: str, values: dict[str, object]) -> dict[str, object]:
    return {header: values.get(header, "") for header in NEXUS_V2_HEADERS[sheet_name]}


def _sheet(sheet_name: str, rows: list[dict[str, object]]) -> dict[str, object]:
    return {"headers": list(NEXUS_V3_HEADERS[sheet_name]), "rows": rows}


def _rule_dict(rule: tuple[str, ...]) -> dict[str, object]:
    return dict(zip(NEXUS_V3_HEADERS["Atlas Rules"], rule, strict=True))


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _v2_status(value: str) -> str:
    normalized = value.casefold()
    if "pilote" in normalized or "test" in normalized:
        return "Pilote"
    if "production" in normalized or "actif" in normalized or "déploy" in normalized:
        return "Production"
    if "retrait" in normalized or "dépréci" in normalized:
        return "Déprécié"
    return "Cadrage"


def _v2_domain(value: str) -> str:
    normalized = value.casefold()
    mappings = (
        (("sinistre", "indemn"), "Sinistres"),
        (("souscri", "tarif"), "Souscription"),
        (("client", "réclamation", "commercial", "distribution"), "Relation client"),
        (("finance", "achat", "coût"), "Finance"),
        (("rh", "compétence", "formation"), "RH"),
        (("marketing",), "Marketing"),
        (("conform", "risque", "fraude"), "Conformité"),
    )
    for needles, domain in mappings:
        if any(needle in normalized for needle in needles):
            return domain
    return "IT / Run"
