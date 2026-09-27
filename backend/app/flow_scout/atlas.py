"""Projection d'un résultat Flow Scout vers le contrat d'import Flow Atlas."""

from __future__ import annotations

import re
import unicodedata

from app.flow_scout.qualification import (
    JOURNEY,
    STRATEGIC_CATEGORIES,
    build_use_case_assessments,
)


def build_flow_atlas_import(
    candidates: dict[str, object],
    interview: dict[str, object],
    *,
    organization_name: str = "Organisation analysée",
    sector: str = "À confirmer",
) -> dict[str, object]:
    raw_ais = _dict_list(candidates.get("ais"))
    raw_systems = _dict_list(candidates.get("systems"))
    raw_skills = _dict_list(candidates.get("skills"))
    raw_personas = _dict_list(candidates.get("personas"))
    raw_activities = _dict_list(interview.get("activities"))

    ordered_activities = sorted(raw_activities, key=_activity_order)
    caps = [
        {
            "id": f"c{index}",
            "name": activity["name"],
            "domain": activity["domain"],
            "crit": activity["criticality"],
            "value": activity["value"],
            "desc": activity["description"],
        }
        for index, activity in enumerate(ordered_activities, start=1)
    ]
    cap_ids = {_normalize(str(cap["name"])): str(cap["id"]) for cap in caps}

    selected_skills = _select_skills(raw_skills, caps)
    skills = [
        {
            "id": f"k{index}",
            "name": skill["name"],
            "domain": skill["department"],
            "crit": _skill_criticality(str(skill["name"]), caps),
            "level": _int(skill.get("level")),
            "headcount": _int(skill.get("headcount")),
            "desc": _skill_description(skill),
        }
        for index, skill in enumerate(selected_skills, start=1)
    ]
    skill_ids = {_normalize(str(skill["name"])): str(skill["id"]) for skill in skills}

    selected_personas = _select_personas(raw_personas, caps)
    personas = [
        {
            "id": f"p{index}",
            "name": persona["name"],
            "domain": persona["department"],
            "headcount": _int(persona.get("headcount")),
        }
        for index, persona in enumerate(selected_personas, start=1)
    ]

    systems = _build_systems(raw_systems, cap_ids)
    system_ids = {_normalize(str(system["name"])): str(system["id"]) for system in systems}

    ordered_ais = _order_ais(raw_ais)
    ais = [
        _build_ai(
            item,
            ai_id=f"a{index}",
            cap_ids=cap_ids,
            skill_ids=skill_ids,
            system_ids=system_ids,
        )
        for index, item in enumerate(ordered_ais, start=1)
    ]

    evidence = {
        "activities": {
            cap["id"]: ordered_activities[index].get("evidence", [])
            for index, cap in enumerate(caps)
        },
        "ais": {
            ai["id"]: ordered_ais[index].get("evidence", [])
            for index, ai in enumerate(ais)
        },
        "systems": {
            system["id"]: raw_systems[index].get("evidence", [])
            for index, system in enumerate(systems)
        },
        "skills": {
            skill["id"]: selected_skills[index].get("evidence", [])
            for index, skill in enumerate(skills)
        },
        "personas": {
            persona["id"]: selected_personas[index].get("evidence", [])
            for index, persona in enumerate(personas)
        },
    }

    graph: dict[str, object] = {
        "_flow_scout": {
            "schema_version": "flow-atlas-import-v1",
            "qualification_schema_version": "flow-scout-qualification-v1",
            "status": "provisional",
            "warning": (
                "Les champs transparency, conso, value, usage et category sont des "
                "estimations de démonstration à faire valider par le client."
            ),
            "estimated_ai_fields": ["transparency", "conso", "value", "usage", "category"],
            "strategic_categories": list(STRATEGIC_CATEGORIES),
            "assessment_journey": list(JOURNEY),
            "rejected_instructions": interview.get("rejected_instructions", []),
            "evidence": evidence,
        },
        "org": {"name": organization_name, "licence": "test", "sector": sector},
        "caps": caps,
        "ais": ais,
        "systems": systems,
        "skills": skills,
        "personas": personas,
        "shadowTrack": {},
        "decisions": {},
    }
    metadata = graph["_flow_scout"]
    if isinstance(metadata, dict):
        metadata["use_case_assessments"] = build_use_case_assessments(graph)
    return graph


def _build_systems(
    raw_systems: list[dict[str, object]], cap_ids: dict[str, str]
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for index, system in enumerate(raw_systems, start=1):
        normalized = _normalize(str(system.get("name", "")))
        if normalized.startswith("crm"):
            linked_caps = _caps(cap_ids, "Répondre à un appel d'offres", "Traiter une réclamation client")
            description = "API ouverte, données propres."
        elif normalized.startswith("erp"):
            linked_caps = _caps(cap_ids, "Planifier la production", "Produire le reporting financier")
            description = "Version ancienne, extraction par exports manuels."
        else:
            linked_caps = _caps(cap_ids, "Produire le reporting financier")
            description = ""
        result.append(
            {
                "id": f"s{index}",
                "name": system["name"],
                "type": system["type"],
                "domain": system["department"],
                "aiReady": _int(system.get("ai_ready")),
                "capIds": linked_caps,
                "desc": description,
            }
        )
    return result


def _build_ai(
    item: dict[str, object],
    *,
    ai_id: str,
    cap_ids: dict[str, str],
    skill_ids: dict[str, str],
    system_ids: dict[str, str],
) -> dict[str, object]:
    name = str(item.get("name", ""))
    normalized = _normalize(name)
    cost = float(item.get("annual_cost_keur", 0) or 0)
    profile: dict[str, object]

    if "assistant memoire technique" in normalized:
        profile = _profile(
            "Copilote", "Commerce", "SaaS éditeur", 4, round(cost * 0.30), 5, 4,
            "Go-to-market", _caps(cap_ids, "Répondre à un appel d'offres"),
            _skills(skill_ids, "Rédaction de mémoire technique"),
            _systems(system_ids, "CRM Salesforce"),
        )
    elif "tri des reclamations" in normalized:
        profile = _profile(
            "Automatisation", "Commerce", "SaaS éditeur", 3, round(cost * 0.20), 3, 4,
            "Productivité", _caps(cap_ids, "Traiter une réclamation client"),
            _skills(skill_ids, "Rédaction de mémoire technique"),
            _systems(system_ids, "CRM Salesforce"),
        )
    elif "reponse automatique" in normalized:
        profile = _profile(
            "Automatisation", "Commerce", "SaaS éditeur", 2, round(cost * 0.14), 2, 2,
            "Productivité", _caps(cap_ids, "Traiter une réclamation client"),
            _skills(skill_ids, "Rédaction de mémoire technique"),
            _systems(system_ids, "CRM Salesforce"),
        )
    elif "prevision de tresorerie" in normalized:
        profile = _profile(
            "Modèle prédictif", "Finance", "OVHcloud", 3, round(cost * 0.40), 4, 3,
            "Sécurisation", _caps(cap_ids, "Produire le reporting financier"), [],
            _systems(system_ids, "BI Power BI"),
        )
    elif "chatgpt" in normalized:
        profile = _profile(
            "Assistant", "Commerce", "SaaS éditeur", 1, 6, 3, 5, "Confort",
            _caps(cap_ids, "Répondre à un appel d'offres"),
            _skills(skill_ids, "Rédaction de mémoire technique"), [],
        )
    elif "contrats fournisseurs" in normalized:
        profile = _profile(
            "Assistant", "Production", "Autre / inconnu", 5, 0, 5, 1,
            "Sécurisation", _caps(cap_ids, "Planifier la production"),
            _skills(skill_ids, "Ordonnancement atelier"), [],
        )
    else:
        profile = _profile(
            "Assistant", _owner_domain(str(item.get("owner", ""))), "Autre / inconnu",
            1, 0, 1, 1, "Confort", [], [], [],
        )

    return {
        "id": ai_id,
        "name": name,
        "type": profile["type"],
        "status": item.get("status", ""),
        "domain": profile["domain"],
        "owner": _atlas_owner(item, normalized, str(profile["domain"])),
        "ownerPerson": item.get("owner_person", ""),
        "model": item.get("model", ""),
        "infra": profile["infra"],
        "provider": item.get("provider", ""),
        "transparency": profile["transparency"],
        "aiact": item.get("ai_act", "Non classée"),
        "cost": _clean_number(cost),
        "conso": profile["conso"],
        "value": profile["value"],
        "usage": profile["usage"],
        "capIds": profile["capIds"],
        "skillIds": profile["skillIds"],
        "sysIds": profile["sysIds"],
        "desc": item.get("description", ""),
        "category": profile["category"],
    }


def _profile(
    ai_type: str,
    domain: str,
    infra: str,
    transparency: int,
    conso: int,
    value: int,
    usage: int,
    category: str,
    cap_ids: list[str],
    skill_ids: list[str],
    system_ids: list[str],
) -> dict[str, object]:
    return {
        "type": ai_type,
        "domain": domain,
        "infra": infra,
        "transparency": transparency,
        "conso": conso,
        "value": value,
        "usage": usage,
        "category": category,
        "capIds": cap_ids,
        "skillIds": skill_ids,
        "sysIds": system_ids,
    }


def _select_skills(
    raw_skills: list[dict[str, object]], caps: list[dict[str, object]]
) -> list[dict[str, object]]:
    wanted = ("redaction de memoire technique", "ordonnancement atelier", "controle de gestion")
    by_name = {_normalize(str(item.get("name", ""))): item for item in raw_skills}
    return [by_name[name] for name in wanted if name in by_name and _skill_relevant(name, caps)]


def _skill_relevant(name: str, caps: list[dict[str, object]]) -> bool:
    cap_names = " ".join(_normalize(str(cap.get("name", ""))) for cap in caps)
    if name == "redaction de memoire technique":
        return "appel d offres" in cap_names
    if name == "ordonnancement atelier":
        return "planifier la production" in cap_names
    if name == "controle de gestion":
        return "reporting financier" in cap_names
    return False


def _select_personas(
    raw_personas: list[dict[str, object]], caps: list[dict[str, object]]
) -> list[dict[str, object]]:
    wanted_by_cap = {
        "repondre a un appel d offres": "charge d affaires grands comptes",
        "traiter une reclamation client": "assistant commercial",
        "planifier la production": "ordonnanceur atelier",
        "produire le reporting financier": "controleur de gestion",
    }
    by_name = {_normalize(str(item.get("name", ""))): item for item in raw_personas}
    result: list[dict[str, object]] = []
    for cap in caps:
        persona_name = wanted_by_cap.get(_normalize(str(cap.get("name", ""))))
        if persona_name and persona_name in by_name:
            result.append(by_name[persona_name])
    return result


def _skill_criticality(name: str, caps: list[dict[str, object]]) -> int:
    normalized = _normalize(name)
    target_cap = {
        "redaction de memoire technique": "repondre a un appel d offres",
        "ordonnancement atelier": "planifier la production",
        "controle de gestion": "produire le reporting financier",
    }.get(normalized)
    for cap in caps:
        if _normalize(str(cap.get("name", ""))) == target_cap:
            return _int(cap.get("crit"))
    return 0


def _skill_description(skill: dict[str, object]) -> str:
    if skill.get("succession_identified") is False:
        return f"Tenu par {_int(skill.get('headcount'))} personnes, aucune relève identifiée."
    if "memoire technique" in _normalize(str(skill.get("name", ""))):
        return "Savoir-faire rédactionnel et technique, bien tenu."
    return ""


def _order_ais(items: list[dict[str, object]]) -> list[dict[str, object]]:
    idea: list[dict[str, object]] = []
    discovered: list[dict[str, object]] = []
    regular: list[dict[str, object]] = []
    for item in items:
        if _normalize(str(item.get("status", ""))) == "idee":
            idea.append(item)
        elif "absente de l inventaire ia" in _normalize(" ".join(map(str, item.get("open_questions", [])))):
            discovered.append(item)
        else:
            regular.append(item)
    return regular + discovered + idea


def _activity_order(activity: dict[str, object]) -> int:
    return {
        "calls_for_tenders": 1,
        "customer_complaints": 2,
        "production_planning": 3,
        "financial_reporting": 4,
    }.get(str(activity.get("key", "")), 99)


def _caps(cap_ids: dict[str, str], *names: str) -> list[str]:
    return [cap_ids[key] for name in names if (key := _normalize(name)) in cap_ids]


def _skills(skill_ids: dict[str, str], *names: str) -> list[str]:
    return [skill_ids[key] for name in names if (key := _normalize(name)) in skill_ids]


def _systems(system_ids: dict[str, str], *names: str) -> list[str]:
    return [system_ids[key] for name in names if (key := _normalize(name)) in system_ids]


def _owner_domain(owner: str) -> str:
    normalized = _normalize(owner)
    if "commercial" in normalized:
        return "Commerce"
    if "financ" in normalized:
        return "Finance"
    if "industri" in normalized or "production" in normalized:
        return "Production"
    return "À confirmer"


def _atlas_owner(item: dict[str, object], normalized_name: str, domain: str) -> str:
    owner = str(item.get("owner", ""))
    if owner:
        return owner
    # Une IA trouvée dans l'inventaire peut être rattachée à une direction même si
    # la personne responsable manque. Un usage découvert uniquement dans les
    # dépenses (ChatGPT) reste, lui, sans propriétaire jusqu'à confirmation.
    if "reponse automatique" in normalized_name and domain == "Commerce":
        return "Direction commerciale"
    return ""


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _clean_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())
