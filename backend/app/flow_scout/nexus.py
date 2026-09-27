"""Pont de compatibilité entre le graphe Flow Scout et NEXUS/Atlas v2.

Le format NEXUS v2 est un classeur de tables plates. Cette projection reste
volontairement prudente : elle laisse une cellule vide quand le graphe ne possède pas
l'information et consigne chaque perte dans ``compatibility_issues``.
"""

from __future__ import annotations

import re
import unicodedata

NEXUS_V2_HEADERS: dict[str, tuple[str, ...]] = {
    "Use cases": (
        "id",
        "nom",
        "domaine",
        "type",
        "statut",
        "owner",
        "entite",
        "valeur",
        "effort",
        "risque",
        "maturite",
        "reutilisation",
        "roi_keuros",
        "utilisateurs",
        "classe_ai_act",
        "base_rgpd",
        "dpia",
        "humain_dans_boucle",
        "source_id",
        "briques",
        "tags",
        "description",
    ),
    "Agents": (
        "id",
        "use_case_id",
        "nom",
        "type",
        "autonomie",
        "statut",
        "environnement",
        "modele",
        "version",
        "owner",
        "appels_mois",
        "csat",
        "source_id",
    ),
    "Sources": ("id", "nom", "editeur", "logo", "couleur", "statut", "protocole", "cadence"),
    "Briques": ("id", "nom", "type"),
    "Transition Board": (
        "decision_id",
        "objet",
        "type_objet",
        "decision",
        "priorite",
        "sponsor",
        "valeur",
        "cout",
        "adoption",
        "impact_travail",
        "ecart_competence",
        "criticite_humaine",
        "action_30j",
        "action_60j",
        "action_90j",
        "kpi",
    ),
    "Tasks_Roles_Skills": (
        "task_id",
        "tache",
        "role",
        "entite",
        "use_case_id",
        "statut_travail",
        "potentiel_automation",
        "criticite_humaine",
        "competences_actuelles",
        "competences_a_developper",
        "niveau_ecart",
        "formation_recommandee",
    ),
}

_ALLOWED_DOMAINS = {
    "Relation client",
    "Souscription",
    "Sinistres",
    "Finance",
    "RH",
    "IT / Run",
    "Marketing",
    "Conformité",
}
_ALLOWED_TYPES = {
    "Assistant",
    "Copilote",
    "Agent autonome",
    "Automatisation",
    "Analytics",
}
_ALLOWED_STATUSES = {"Idée", "Cadrage", "POC", "Pilote", "Production", "Déprécié"}
_ALLOWED_AI_ACT = {"Haut risque", "Risque limité", "Minimal", "Inacceptable"}


def build_nexus_v2_payload(graph: dict[str, object]) -> dict[str, object]:
    issues: list[dict[str, object]] = []
    ais = _dict_list(graph.get("ais"))
    systems = _dict_list(graph.get("systems"))
    caps = _dict_list(graph.get("caps"))
    skills = _dict_list(graph.get("skills"))
    personas = _dict_list(graph.get("personas"))
    decisions = _dict_list(graph.get("decisions"))

    source_rows, system_to_source = _build_sources(systems, issues)
    use_case_rows, ai_to_use_case = _build_use_cases(
        ais, system_to_source=system_to_source, issues=issues
    )
    task_rows = _build_tasks(
        caps,
        ais,
        skills,
        personas,
        ai_to_use_case=ai_to_use_case,
        issues=issues,
    )
    decision_rows = _build_decisions(decisions, issues)

    sheets: dict[str, dict[str, object]] = {
        "Use cases": {"headers": list(NEXUS_V2_HEADERS["Use cases"]), "rows": use_case_rows},
        "Agents": {"headers": list(NEXUS_V2_HEADERS["Agents"]), "rows": []},
        "Sources": {"headers": list(NEXUS_V2_HEADERS["Sources"]), "rows": source_rows},
        "Briques": {"headers": list(NEXUS_V2_HEADERS["Briques"]), "rows": []},
        "Transition Board": {
            "headers": list(NEXUS_V2_HEADERS["Transition Board"]),
            "rows": decision_rows,
        },
        "Tasks_Roles_Skills": {
            "headers": list(NEXUS_V2_HEADERS["Tasks_Roles_Skills"]),
            "rows": task_rows,
        },
    }

    return {
        "schema_version": "nexus-import-v2-bridge",
        "source_graph_version": _source_graph_version(graph),
        "sheets": sheets,
        "compatibility": {
            "status": "lossy",
            "issues": issues,
            "issue_count": len(issues),
            "preserved_in_canonical_graph": True,
            "note": (
                "Ce payload alimente Atlas v2 sans remplacer le graphe canonique Flow Scout. "
                "Les cellules vides représentent des informations inconnues, jamais des zéros."
            ),
        },
    }


def _build_use_cases(
    ais: list[dict[str, object]],
    *,
    system_to_source: dict[str, str],
    issues: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, str]]:
    rows: list[dict[str, object]] = []
    ids: dict[str, str] = {}
    for index, ai in enumerate(ais, start=1):
        ai_id = str(ai.get("id", f"a{index}"))
        use_case_id = f"U{index}"
        ids[ai_id] = use_case_id
        domain = _map_domain(str(ai.get("domain", "")), ai_id, issues)
        ai_type = _map_type(str(ai.get("type", "")), ai_id, issues)
        status = str(ai.get("status", ""))
        if status not in _ALLOWED_STATUSES:
            _issue(issues, ai_id, "statut", status, "Valeur absente de la liste NEXUS v2.")
            status = ""
        ai_act = _map_ai_act(str(ai.get("aiact", "")), ai_id, issues)
        sys_ids = [str(value) for value in ai.get("sysIds", []) if value]
        source_ids = [system_to_source[value] for value in sys_ids if value in system_to_source]
        if len(source_ids) > 1:
            _issue(
                issues,
                ai_id,
                "source_id",
                source_ids,
                "NEXUS v2 n'accepte qu'une source par use case ; seule la première est exportée.",
            )
        if not source_ids:
            _issue(
                issues,
                ai_id,
                "source_id",
                "",
                "Aucun système confirmé : la cellule reste vide, sans forcer INT.",
            )
        owner_person = str(ai.get("ownerPerson", ""))
        owner_entity = str(ai.get("owner", "")) or str(ai.get("domain", ""))
        rows.append(
            _row(
                "Use cases",
                {
                    "id": use_case_id,
                    "nom": ai.get("name", ""),
                    "domaine": domain,
                    "type": ai_type,
                    "statut": status,
                    "owner": owner_person,
                    "entite": owner_entity,
                    "valeur": ai.get("value"),
                    "effort": None,
                    "risque": None,
                    "maturite": None,
                    "reutilisation": None,
                    "roi_keuros": None,
                    "utilisateurs": None,
                    "classe_ai_act": ai_act,
                    "base_rgpd": None,
                    "dpia": None,
                    "humain_dans_boucle": None,
                    "source_id": source_ids[0] if source_ids else "",
                    "briques": "",
                    "tags": str(ai.get("category", "")),
                    "description": ai.get("desc", ""),
                },
            )
        )
    return rows, ids


def _build_sources(
    systems: list[dict[str, object]], issues: list[dict[str, object]]
) -> tuple[list[dict[str, object]], dict[str, str]]:
    rows = [
        _row(
            "Sources",
            {
                "id": "INT",
                "nom": "Plateforme interne",
                "editeur": "Interne",
                "logo": "INT",
                "couleur": "#6366f1",
                "statut": "À configurer",
                "protocole": "Import fichier",
                "cadence": "Ponctuelle",
            },
        )
    ]
    mapping: dict[str, str] = {}
    used = {"INT"}
    for index, system in enumerate(systems, start=1):
        system_id = str(system.get("id", f"s{index}"))
        name = str(system.get("name", ""))
        source_id = _source_code(name, index, used)
        used.add(source_id)
        mapping[system_id] = source_id
        ai_ready = _number(system.get("aiReady"))
        if ai_ready >= 4:
            connection_status, protocol = "Connecté", "API"
        elif ai_ready >= 3:
            connection_status, protocol = "Sync en cours", "Connecteur à confirmer"
        else:
            connection_status, protocol = "À configurer", "Import manuel"
        rows.append(
            _row(
                "Sources",
                {
                    "id": source_id,
                    "nom": name,
                    "editeur": _editor(name),
                    "logo": source_id,
                    "couleur": _source_color(index),
                    "statut": connection_status,
                    "protocole": protocol,
                    "cadence": "À confirmer",
                },
            )
        )
        if source_id not in {"SAP", "MSF", "SF", "SNOW", "WD", "ORA", "INT"}:
            _issue(
                issues,
                system_id,
                "source_id",
                source_id,
                "La validation NEXUS v2 est figée ; elle doit devenir dynamique depuis l'onglet Sources.",
            )
    return rows, mapping


def _build_tasks(
    caps: list[dict[str, object]],
    ais: list[dict[str, object]],
    skills: list[dict[str, object]],
    personas: list[dict[str, object]],
    *,
    ai_to_use_case: dict[str, str],
    issues: list[dict[str, object]],
) -> list[dict[str, object]]:
    skill_by_id = {str(item.get("id", "")): item for item in skills}
    ais_by_cap: dict[str, list[dict[str, object]]] = {}
    for ai in ais:
        for cap_id in ai.get("capIds", []):
            ais_by_cap.setdefault(str(cap_id), []).append(ai)

    rows: list[dict[str, object]] = []
    for index, cap in enumerate(caps, start=1):
        cap_id = str(cap.get("id", f"c{index}"))
        linked_ais = ais_by_cap.get(cap_id, [])
        use_case_ids = [
            ai_to_use_case[str(ai.get("id"))]
            for ai in linked_ais
            if str(ai.get("id")) in ai_to_use_case
        ]
        if len(use_case_ids) > 1:
            _issue(
                issues,
                cap_id,
                "use_case_id",
                use_case_ids,
                "La relation plusieurs-à-plusieurs est aplatie ; seul le premier use case est exporté.",
            )
        linked_skill_ids = {
            str(skill_id)
            for ai in linked_ais
            for skill_id in ai.get("skillIds", [])
            if skill_id
        }
        linked_skills = [skill_by_id[key] for key in linked_skill_ids if key in skill_by_id]
        skill_names = [str(skill.get("name", "")) for skill in linked_skills]
        gap = None
        if linked_skills:
            lowest_level = min(_number(skill.get("level")) for skill in linked_skills)
            gap = max(0, _number(cap.get("crit")) - lowest_level)
        persona = _persona_for_cap(cap, personas)
        rows.append(
            _row(
                "Tasks_Roles_Skills",
                {
                    "task_id": f"T{index}",
                    "tache": cap.get("name", ""),
                    "role": persona.get("name", "") if persona else "",
                    "entite": cap.get("domain", ""),
                    "use_case_id": use_case_ids[0] if use_case_ids else "",
                    "statut_travail": None,
                    "potentiel_automation": None,
                    "criticite_humaine": cap.get("crit"),
                    "competences_actuelles": ";".join(skill_names),
                    "competences_a_developper": None,
                    "niveau_ecart": gap,
                    "formation_recommandee": None,
                },
            )
        )
    return rows


def _build_decisions(
    decisions: list[dict[str, object]], issues: list[dict[str, object]]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, decision in enumerate(decisions, start=1):
        if not decision:
            continue
        rows.append(
            _row(
                "Transition Board",
                {
                    "decision_id": decision.get("id", f"D{index}"),
                    "objet": decision.get("object_name", decision.get("objet", "")),
                    "type_objet": decision.get("object_type", decision.get("type_objet", "")),
                    "decision": decision.get("decision", ""),
                    "priorite": decision.get("priority", decision.get("priorite")),
                    "sponsor": decision.get("sponsor", ""),
                    "valeur": decision.get("value", decision.get("valeur")),
                    "cout": decision.get("cost", decision.get("cout")),
                    "adoption": decision.get("adoption"),
                    "impact_travail": decision.get("work_impact", decision.get("impact_travail", "")),
                    "ecart_competence": decision.get("skill_gap", decision.get("ecart_competence")),
                    "criticite_humaine": decision.get("human_criticality", decision.get("criticite_humaine")),
                    "action_30j": decision.get("action_30d", decision.get("action_30j", "")),
                    "action_60j": decision.get("action_60d", decision.get("action_60j", "")),
                    "action_90j": decision.get("action_90d", decision.get("action_90j", "")),
                    "kpi": decision.get("kpi", ""),
                },
            )
        )
    if not rows:
        _issue(
            issues,
            "portfolio",
            "Transition Board",
            "",
            "Aucune décision n'est encore présente ; cet onglet restera vide avant le moteur Atlas.",
        )
    return rows


def _map_domain(value: str, object_id: str, issues: list[dict[str, object]]) -> str:
    normalized = _normalize(value)
    mapped = {
        "commerce": "Relation client",
        "relation client": "Relation client",
        "finance": "Finance",
        "rh": "RH",
        "marketing": "Marketing",
        "conformite": "Conformité",
        "it run": "IT / Run",
    }.get(normalized)
    if mapped in _ALLOWED_DOMAINS:
        if mapped != value:
            _issue(
                issues,
                object_id,
                "domaine",
                value,
                f"Domaine rapproché de '{mapped}' pour NEXUS v2.",
            )
        return mapped
    _issue(
        issues,
        object_id,
        "domaine",
        value,
        "Domaine non représentable par la liste fermée NEXUS v2 ; cellule laissée vide.",
    )
    return ""


def _map_type(value: str, object_id: str, issues: list[dict[str, object]]) -> str:
    if value in _ALLOWED_TYPES:
        return value
    normalized = _normalize(value)
    if normalized in {"modele predictif", "analytique", "analytics"}:
        mapped = "Analytics"
    elif normalized == "assistant":
        mapped = "Assistant"
    elif normalized == "copilote":
        mapped = "Copilote"
    else:
        mapped = ""
    _issue(
        issues,
        object_id,
        "type",
        value,
        f"Type rapproché de '{mapped}' pour NEXUS v2." if mapped else "Type non représentable.",
    )
    return mapped


def _map_ai_act(value: str, object_id: str, issues: list[dict[str, object]]) -> str:
    mapped = "Minimal" if _normalize(value) == "risque minimal" else value
    if mapped in _ALLOWED_AI_ACT:
        return mapped
    _issue(
        issues,
        object_id,
        "classe_ai_act",
        value,
        "Valeur non représentable par NEXUS v2 ; 'Non classée' doit devenir une valeur autorisée.",
    )
    return ""


def _persona_for_cap(
    cap: dict[str, object], personas: list[dict[str, object]]
) -> dict[str, object] | None:
    target = {
        "repondre a un appel d offres": "charge d affaires grands comptes",
        "traiter une reclamation client": "assistant commercial",
        "planifier la production": "ordonnanceur atelier",
        "produire le reporting financier": "controleur de gestion",
    }.get(_normalize(str(cap.get("name", ""))))
    for persona in personas:
        if _normalize(str(persona.get("name", ""))) == target:
            return persona
    return None


def _source_code(name: str, index: int, used: set[str]) -> str:
    normalized = _normalize(name)
    preferred = ""
    if "salesforce" in normalized:
        preferred = "SF"
    elif re.search(r"\bsap\b", normalized):
        preferred = "SAP"
    elif "power bi" in normalized:
        preferred = "PBI"
    if preferred and preferred not in used:
        return preferred
    base = re.sub(r"[^A-Z0-9]", "", name.upper())[:4] or f"SYS{index}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base[:3]}{suffix}"
        suffix += 1
    return candidate


def _editor(name: str) -> str:
    normalized = _normalize(name)
    if "salesforce" in normalized:
        return "Salesforce"
    if re.search(r"\bsap\b", normalized):
        return "SAP"
    if "power bi" in normalized:
        return "Microsoft"
    return "À confirmer"


def _source_color(index: int) -> str:
    palette = ("#34d399", "#0fa0c0", "#22d3ee", "#a78bfa", "#fbbf24", "#f87171")
    return palette[(index - 1) % len(palette)]


def _row(sheet: str, values: dict[str, object]) -> dict[str, object]:
    return {header: values.get(header) for header in NEXUS_V2_HEADERS[sheet]}


def _issue(
    issues: list[dict[str, object]],
    object_id: str,
    field: str,
    value: object,
    reason: str,
) -> None:
    issues.append({"object_id": object_id, "field": field, "value": value, "reason": reason})


def _source_graph_version(graph: dict[str, object]) -> str:
    metadata = graph.get("_flow_scout")
    if isinstance(metadata, dict):
        return str(metadata.get("schema_version", "unknown"))
    return "unknown"


def _dict_list(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _number(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())
