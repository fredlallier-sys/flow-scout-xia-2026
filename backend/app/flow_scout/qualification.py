"""Matrices de qualification maïeutique des cas d'usage Flow Scout.

Les matrices structurent l'entretien sans fabriquer de certitude. Chaque résultat
expose les preuves disponibles, un niveau de confiance et les points à vérifier.
"""

from __future__ import annotations

from copy import deepcopy
import re
import unicodedata

STRATEGIC_CATEGORIES = (
    "Confort",
    "Productivité",
    "Sécurisation",
    "Go-to-market",
    "Produit",
    "Stratégique",
)

JOURNEY = ("situer", "comprendre", "évaluer", "déléguer", "prioriser")

_MATRIX_QUESTIONS = (
    ("coverage.axis_1", "coverage", "axis_1", "Quelle fonction métier est principalement concernée ?", "text", ()),
    ("coverage.axis_2", "coverage", "axis_2", "Quelle est la finalité principale, puis la finalité secondaire éventuelle ?", "text", STRATEGIC_CATEGORIES),
    ("real_work.axis_1", "real_work", "axis_1", "Quel rôle ou persona utilise réellement cette IA ?", "text", ()),
    ("real_work.axis_2", "real_work", "axis_2", "Pour quelle activité précise, et avec quel changement concret ?", "text", ()),
    ("value.axis_1", "value", "axis_1", "Quel gain d'efficacité mesurable attendez-vous ?", "text", ()),
    ("value.axis_2", "value", "axis_2", "En quoi cet usage peut-il différencier l'organisation ?", "text", ()),
    ("delegation.axis_1", "delegation", "axis_1", "Quel niveau de délégation D0 à D5 paraît acceptable ?", "select", ("D0", "D1", "D2", "D3", "D4", "D5")),
    ("delegation.axis_2", "delegation", "axis_2", "Quelle serait la criticité d'une erreur, de 1 à 5, et quel contrôle humain faut-il ?", "text", ("1", "2", "3", "4", "5")),
    ("feasibility.axis_1", "feasibility", "axis_1", "Comment évaluez-vous la disponibilité et la qualité des données, de 1 à 5 ?", "scale", ("1", "2", "3", "4", "5")),
    ("feasibility.axis_2", "feasibility", "axis_2", "Quelle est la difficulté d'intégration au SI, de 1 à 5, et quel prérequis manque ?", "text", ("1", "2", "3", "4", "5")),
    ("economics.axis_1", "economics", "axis_1", "Quelle valeur attendez-vous, avec quelle unité et sur quelle période ?", "text", ()),
    ("economics.axis_2", "economics", "axis_2", "Quel est le coût complet : outils, intégration, usage, formation et contrôle ?", "text", ()),
)


def build_use_case_assessments(graph: dict[str, object]) -> list[dict[str, object]]:
    """Produit les six matrices pour chaque IA du graphe Atlas."""
    ais = _dict_list(graph.get("ais"))
    caps = _by_id(_dict_list(graph.get("caps")))
    systems = _by_id(_dict_list(graph.get("systems")))
    personas = _dict_list(graph.get("personas"))
    metadata = graph.get("_flow_scout")
    evidence_index = metadata.get("evidence", {}) if isinstance(metadata, dict) else {}
    if not isinstance(evidence_index, dict):
        evidence_index = {}

    assessments: list[dict[str, object]] = []
    for ai in ais:
        ai_id = str(ai.get("id", ""))
        linked_caps = [caps[key] for key in _string_list(ai.get("capIds")) if key in caps]
        linked_systems = [
            systems[key] for key in _string_list(ai.get("sysIds")) if key in systems
        ]
        linked_personas = _personas_for_caps(linked_caps, personas)
        ai_evidence = _evidence(evidence_index, "ais", [ai_id])
        cap_evidence = _evidence(
            evidence_index, "activities", [str(item.get("id", "")) for item in linked_caps]
        )
        system_evidence = _evidence(
            evidence_index, "systems", [str(item.get("id", "")) for item in linked_systems]
        )

        matrices = [
            _coverage_matrix(ai, ai_evidence),
            _real_work_matrix(linked_personas, linked_caps, ai_evidence + cap_evidence),
            _value_matrix(ai, ai_evidence + cap_evidence),
            _delegation_matrix(ai, linked_caps, ai_evidence + cap_evidence),
            _feasibility_matrix(linked_systems, ai_evidence + system_evidence),
            _economics_matrix(ai, ai_evidence),
        ]
        questions = _questions_for(ai)
        assessments.append(
            {
                "ai_id": ai_id,
                "use_case_name": ai.get("name", ""),
                "journey": list(JOURNEY),
                "matrices": matrices,
                "questions": questions,
                "answered_question_ids": [],
                "confirmation": {
                    "status": "À confirmer",
                    "confirmed_matrix_count": 0,
                    "total_matrix_count": len(matrices),
                    "answered_question_count": 0,
                    "total_question_count": len(questions),
                    "ready_for_confirmation": False,
                    "next_question_id": questions[0]["id"],
                    "next_question": questions[0]["question"],
                    "next_question_kind": questions[0]["kind"],
                    "next_question_options": questions[0]["options"],
                    "prompt": _confirmation_prompt(ai, linked_personas, linked_caps),
                },
            }
        )
    return assessments


def apply_qualification_answer(
    graph: dict[str, object],
    *,
    ai_id: str,
    question_id: str,
    answer: str,
) -> dict[str, object]:
    """Applique une réponse humaine à la question courante d'un cas d'usage."""
    clean_answer = " ".join(answer.split())
    if not clean_answer:
        raise ValueError("La réponse ne peut pas être vide.")
    if len(clean_answer) > 4000:
        raise ValueError("La réponse dépasse la limite de 4 000 caractères.")

    updated = deepcopy(graph)
    assessment = _find_assessment(updated, ai_id)
    confirmation = assessment.get("confirmation")
    if not isinstance(confirmation, dict):
        raise ValueError("État de qualification invalide.")
    expected_question_id = confirmation.get("next_question_id")
    if expected_question_id != question_id:
        raise ValueError("Cette question n'est plus la question active.")

    question = _find_question(assessment, question_id)
    matrix = _find_matrix(assessment, str(question["matrix_id"]))
    axis_key = str(question["axis_key"])
    axis = matrix.get(axis_key)
    if not isinstance(axis, dict):
        raise ValueError("Axe de qualification introuvable.")
    if "proposal" not in axis:
        axis["proposal"] = deepcopy(axis.get("value"))
    axis["value"] = clean_answer
    axis["provenance"] = "User declared"

    proof = matrix.get("proof_available")
    if not isinstance(proof, list):
        proof = []
        matrix["proof_available"] = proof
    proof.append(
        {
            "source": "qualification_interview",
            "locator": question_id,
            "quote": clean_answer,
            "provenance": "User declared",
        }
    )
    matrix["confidence"] = "moyenne"
    matrix["status"] = "déclaré"
    matrix["conclusion"] = _declared_conclusion(matrix)

    answered = assessment.get("answered_question_ids")
    if not isinstance(answered, list):
        answered = []
        assessment["answered_question_ids"] = answered
    if question_id not in answered:
        answered.append(question_id)
    _refresh_confirmation(assessment)
    return updated


def confirm_use_case_assessment(
    graph: dict[str, object], *, ai_id: str
) -> dict[str, object]:
    """Valide la compréhension du cas d'usage après les réponses aux matrices."""
    updated = deepcopy(graph)
    assessment = _find_assessment(updated, ai_id)
    confirmation = assessment.get("confirmation")
    if not isinstance(confirmation, dict) or not confirmation.get("ready_for_confirmation"):
        raise ValueError("Toutes les questions doivent être renseignées avant confirmation.")
    matrices = assessment.get("matrices")
    if not isinstance(matrices, list):
        raise ValueError("Matrices de qualification absentes.")
    for matrix in matrices:
        if not isinstance(matrix, dict):
            continue
        matrix["status"] = "validé"
        if matrix.get("confidence") == "moyenne" and matrix.get("proof_available"):
            matrix["confidence"] = "élevée"
    confirmation.update(
        {
            "status": "Validé",
            "confirmed_matrix_count": len(matrices),
            "next_question_id": None,
            "next_question": None,
            "next_question_kind": None,
            "next_question_options": [],
            "ready_for_confirmation": False,
            "validated_provenance": "User declared",
        }
    )
    return updated


def _coverage_matrix(
    ai: dict[str, object], evidence: list[dict[str, object]]
) -> dict[str, object]:
    category = str(ai.get("category", ""))
    if category not in STRATEGIC_CATEGORIES:
        category = ""
    return _matrix(
        matrix_id="coverage",
        name="Couverture des usages",
        stage="situer",
        axis_1={"label": "Fonction", "value": ai.get("domain") or None},
        axis_2={
            "label": "Finalité stratégique",
            "value": {
                "primary": category or None,
                "secondary": None,
                "allowed": list(STRATEGIC_CATEGORIES),
            },
        },
        conclusion=(
            f"Usage provisoirement situé en {ai.get('domain')} avec la finalité {category}."
            if ai.get("domain") and category
            else "La fonction ou la finalité stratégique reste à situer."
        ),
        evidence=evidence,
        confidence="faible",
        to_verify=[
            "Confirmer la fonction métier concernée.",
            "Confirmer la finalité principale et, si utile, une finalité secondaire.",
        ],
    )


def _real_work_matrix(
    personas: list[dict[str, object]],
    caps: list[dict[str, object]],
    evidence: list[dict[str, object]],
) -> dict[str, object]:
    persona_names = [str(item.get("name", "")) for item in personas if item.get("name")]
    activity_names = [str(item.get("name", "")) for item in caps if item.get("name")]
    has_context = bool(persona_names and activity_names)
    return _matrix(
        matrix_id="real_work",
        name="Travail réel",
        stage="comprendre",
        axis_1={"label": "Personas concernés", "value": persona_names or None},
        axis_2={"label": "Activités réalisées", "value": activity_names or None},
        conclusion=(
            f"{', '.join(persona_names)} → {', '.join(activity_names)}."
            if has_context
            else "Le cas d'usage n'est pas encore rattaché à une situation de travail complète."
        ),
        evidence=evidence,
        confidence="moyenne" if has_context and evidence else "faible",
        to_verify=[
            "Confirmer qui réalise réellement l'activité.",
            "Décrire le changement concret avant et après l'usage de l'IA.",
        ],
    )


def _value_matrix(
    ai: dict[str, object], evidence: list[dict[str, object]]
) -> dict[str, object]:
    measures = _value_measures(str(ai.get("category", "")))
    return _matrix(
        matrix_id="value",
        name="Valeur créée",
        stage="évaluer",
        axis_1={"label": "Gains d'efficacité", "value": None},
        axis_2={"label": "Contribution à la différenciation", "value": None},
        conclusion="La valeur n'est pas encore mesurée ; aucun score n'est présenté comme acquis.",
        evidence=evidence,
        confidence="inconnue",
        to_verify=[
            f"Mesurer au moins un indicateur : {', '.join(measures)}.",
            "Distinguer l'amélioration de l'existant d'un avantage concurrentiel démontrable.",
        ],
    )


def _delegation_matrix(
    ai: dict[str, object],
    caps: list[dict[str, object]],
    evidence: list[dict[str, object]],
) -> dict[str, object]:
    current = _delegation_level(str(ai.get("type", "")))
    criticalities = [_number(item.get("crit")) for item in caps if item.get("crit") is not None]
    error_criticality = max(criticalities) if criticalities else None
    return _matrix(
        matrix_id="delegation",
        name="Délégation acceptable",
        stage="déléguer",
        axis_1={
            "label": "Niveau d'autonomie envisagé",
            "value": {"current_proposal": current, "target": None},
        },
        axis_2={"label": "Criticité d'une erreur", "value": error_criticality},
        conclusion=(
            f"Niveau actuel proposé : {current}. Le niveau cible reste à décider avec le métier."
            if current
            else "Le niveau actuel et le niveau cible de délégation restent à qualifier."
        ),
        evidence=evidence,
        confidence="faible",
        to_verify=[
            "Confirmer le niveau actuel D0 à D5.",
            "Fixer le niveau cible et le contrôle humain requis.",
            "Décrire les conséquences d'une erreur et les possibilités de retour en arrière.",
        ],
    )


def _feasibility_matrix(
    systems: list[dict[str, object]], evidence: list[dict[str, object]]
) -> dict[str, object]:
    readiness = [_number(item.get("aiReady")) for item in systems if item.get("aiReady") is not None]
    data_quality = min(readiness) if readiness else None
    integration_difficulty = 6 - data_quality if data_quality else None
    system_names = [str(item.get("name", "")) for item in systems if item.get("name")]
    return _matrix(
        matrix_id="feasibility",
        name="Faisabilité",
        stage="prioriser",
        axis_1={
            "label": "Disponibilité et qualité des données",
            "value": data_quality,
            "scale": "1-5, estimation par l'état des systèmes",
        },
        axis_2={
            "label": "Difficulté d'intégration au SI",
            "value": integration_difficulty,
            "scale": "1-5, estimation inverse de la préparation IA",
        },
        conclusion=(
            f"Sources techniques candidates : {', '.join(system_names)}."
            if system_names
            else "Aucune source technique n'est encore reliée au cas d'usage."
        ),
        evidence=evidence,
        confidence="moyenne" if system_names and evidence else "faible",
        to_verify=[
            "Confirmer les droits d'accès, la qualité et la fraîcheur des données.",
            "Valider le mode d'intégration, la sécurité et les dépendances SI.",
        ],
    )


def _economics_matrix(
    ai: dict[str, object], evidence: list[dict[str, object]]
) -> dict[str, object]:
    cost = _optional_number(ai.get("cost"))
    known_components = ["outils/licences"] if cost is not None else []
    return _matrix(
        matrix_id="economics",
        name="Arbitrage économique",
        stage="prioriser",
        axis_1={"label": "Valeur attendue", "value": None},
        axis_2={
            "label": "Coût complet",
            "value": {
                "known_annual_cost_keur": cost,
                "known_components": known_components,
                "missing_components": ["intégration", "usage", "formation", "contrôle"],
                "completeness": "partiel" if cost is not None else "inconnu",
            },
        },
        conclusion="Décision bloquée : mesurer la valeur attendue et documenter le coût complet.",
        evidence=evidence,
        confidence="faible" if cost is not None else "inconnue",
        to_verify=[
            "Quantifier la valeur attendue avec une période et une unité.",
            "Compléter les coûts d'intégration, d'usage, de formation et de contrôle.",
            "Décider ensuite : expérimenter, industrialiser, revoir ou abandonner.",
        ],
        decision={"status": "bloquée", "reason": "Valeur ou coût complet non documenté."},
    )


def _matrix(
    *,
    matrix_id: str,
    name: str,
    stage: str,
    axis_1: dict[str, object],
    axis_2: dict[str, object],
    conclusion: str,
    evidence: list[dict[str, object]],
    confidence: str,
    to_verify: list[str],
    decision: dict[str, object] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": matrix_id,
        "name": name,
        "stage": stage,
        "axis_1": axis_1,
        "axis_2": axis_2,
        "conclusion": conclusion,
        "proof_available": evidence,
        "confidence": confidence,
        "to_verify": to_verify,
        "status": "proposition",
    }
    if decision is not None:
        result["decision"] = decision
    return result


def _questions_for(ai: dict[str, object]) -> list[dict[str, object]]:
    name = str(ai.get("name", "ce cas d'usage"))
    return [
        {
            "id": question_id,
            "matrix_id": matrix_id,
            "axis_key": axis_key,
            "question": f"Pour « {name} » — {prompt}",
            "kind": kind,
            "options": list(options),
        }
        for question_id, matrix_id, axis_key, prompt, kind, options in _MATRIX_QUESTIONS
    ]


def _find_assessment(graph: dict[str, object], ai_id: str) -> dict[str, object]:
    metadata = graph.get("_flow_scout")
    if not isinstance(metadata, dict):
        raise ValueError("Métadonnées Flow Scout absentes.")
    assessments = metadata.get("use_case_assessments")
    if not isinstance(assessments, list):
        raise ValueError("Qualifications Flow Scout absentes.")
    for assessment in assessments:
        if isinstance(assessment, dict) and assessment.get("ai_id") == ai_id:
            return assessment
    raise ValueError(f"Cas d'usage introuvable : {ai_id}.")


def _find_question(
    assessment: dict[str, object], question_id: str
) -> dict[str, object]:
    questions = assessment.get("questions")
    if isinstance(questions, list):
        for question in questions:
            if isinstance(question, dict) and question.get("id") == question_id:
                return question
    raise ValueError(f"Question de qualification introuvable : {question_id}.")


def _find_matrix(
    assessment: dict[str, object], matrix_id: str
) -> dict[str, object]:
    matrices = assessment.get("matrices")
    if isinstance(matrices, list):
        for matrix in matrices:
            if isinstance(matrix, dict) and matrix.get("id") == matrix_id:
                return matrix
    raise ValueError(f"Matrice de qualification introuvable : {matrix_id}.")


def _refresh_confirmation(assessment: dict[str, object]) -> None:
    questions = [
        item for item in assessment.get("questions", []) if isinstance(item, dict)
    ]
    answered = {
        str(item) for item in assessment.get("answered_question_ids", []) if item
    }
    confirmation = assessment.get("confirmation")
    if not isinstance(confirmation, dict):
        raise ValueError("État de confirmation absent.")

    completed_matrices = 0
    for matrix_id in {str(item.get("matrix_id")) for item in questions}:
        matrix_question_ids = {
            str(item.get("id"))
            for item in questions
            if str(item.get("matrix_id")) == matrix_id
        }
        if matrix_question_ids and matrix_question_ids.issubset(answered):
            completed_matrices += 1

    next_question = next(
        (item for item in questions if str(item.get("id")) not in answered),
        None,
    )
    confirmation.update(
        {
            "confirmed_matrix_count": completed_matrices,
            "answered_question_count": len(answered),
            "ready_for_confirmation": next_question is None,
            "status": "Prêt à confirmer" if next_question is None else "À confirmer",
            "next_question_id": next_question.get("id") if next_question else None,
            "next_question": next_question.get("question") if next_question else None,
            "next_question_kind": next_question.get("kind") if next_question else None,
            "next_question_options": next_question.get("options", []) if next_question else [],
        }
    )


def _declared_conclusion(matrix: dict[str, object]) -> str:
    axis_1 = matrix.get("axis_1")
    axis_2 = matrix.get("axis_2")
    value_1 = axis_1.get("value") if isinstance(axis_1, dict) else None
    value_2 = axis_2.get("value") if isinstance(axis_2, dict) else None
    if value_1 not in (None, "") and value_2 not in (None, ""):
        return "Les deux axes disposent d'une déclaration métier ; la compréhension reste à confirmer."
    return "Une déclaration métier est enregistrée ; l'autre axe reste à renseigner."


def _confirmation_prompt(
    ai: dict[str, object],
    personas: list[dict[str, object]],
    caps: list[dict[str, object]],
) -> str:
    persona = str(personas[0].get("name")) if personas else "un rôle à confirmer"
    activity = str(caps[0].get("name")) if caps else "une activité à préciser"
    return (
        f"Voici ce que j'ai compris : {persona} utilise l'IA « {ai.get('name', 'à préciser')} » "
        f"pour {activity}. Est-ce exact, et que faut-il corriger ?"
    )


def _personas_for_caps(
    caps: list[dict[str, object]], personas: list[dict[str, object]]
) -> list[dict[str, object]]:
    wanted_by_cap = {
        "repondre a un appel d offres": "charge d affaires grands comptes",
        "traiter une reclamation client": "assistant commercial",
        "planifier la production": "ordonnanceur atelier",
        "produire le reporting financier": "controleur de gestion",
    }
    by_name = {_normalize(str(item.get("name", ""))): item for item in personas}
    result: list[dict[str, object]] = []
    for cap in caps:
        persona_name = wanted_by_cap.get(_normalize(str(cap.get("name", ""))))
        if persona_name and persona_name in by_name and by_name[persona_name] not in result:
            result.append(by_name[persona_name])
    return result


def _value_measures(category: str) -> list[str]:
    return {
        "Confort": ["satisfaction", "temps perçu", "usage"],
        "Productivité": ["temps économisé", "coût évité", "délai réduit"],
        "Sécurisation": ["erreurs évitées", "incidents évités", "risque financier évité"],
        "Go-to-market": ["conversion", "pipeline", "cycle commercial", "churn"],
        "Produit": ["adoption", "revenu produit", "rétention", "usage"],
        "Stratégique": ["nouveau revenu", "transformation du coût", "nouveau canal"],
    }.get(category, ["temps", "qualité", "revenu", "risque"])


def _delegation_level(ai_type: str) -> str | None:
    normalized = _normalize(ai_type)
    if normalized == "assistant":
        return "D1"
    if normalized == "copilote":
        return "D2"
    if normalized in {"modele predictif", "analytics", "analytique"}:
        return "D3"
    if normalized in {"automatisation", "agent autonome"}:
        return "D4"
    return None


def _evidence(
    evidence_index: dict[str, object], collection: str, object_ids: list[str]
) -> list[dict[str, object]]:
    collection_evidence = evidence_index.get(collection)
    if not isinstance(collection_evidence, dict):
        return []
    result: list[dict[str, object]] = []
    for object_id in object_ids:
        evidence = collection_evidence.get(object_id)
        if not isinstance(evidence, list):
            continue
        for item in evidence:
            if isinstance(item, dict) and item not in result:
                result.append(item)
    return result


def _by_id(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(item.get("id")): item for item in items if item.get("id")}


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _number(value: object) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _optional_number(value: object) -> int | float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return int(number) if number.is_integer() else number


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())
