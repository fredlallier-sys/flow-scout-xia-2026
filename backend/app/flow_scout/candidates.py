"""Extraction prudente de candidats Flow Scout à partir des tableaux ingérés.

Ce module produit uniquement des objets qui possèdent une preuve source. Les activités
ne sont jamais inventées depuis un intitulé de poste : elles restent un trou à combler
par une question ciblée.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from app.flow_scout.models import IngestionBatch, SourceKind, SourceRow

_STOP_WORDS = {
    "a",
    "au",
    "aux",
    "de",
    "des",
    "du",
    "en",
    "et",
    "la",
    "le",
    "les",
    "l",
    "niveau",
    "pour",
    "un",
    "une",
}


def extract_candidates(batch: IngestionBatch) -> dict[str, object]:
    tables = {table.kind: table for table in batch.tables if table.kind is not SourceKind.UNKNOWN}
    subscriptions = list(tables.get(SourceKind.SUBSCRIPTIONS, _EMPTY_TABLE).rows)
    inventory = list(tables.get(SourceKind.AI_INVENTORY, _EMPTY_TABLE).rows)
    applications = list(tables.get(SourceKind.APPLICATIONS, _EMPTY_TABLE).rows)
    workforce = list(tables.get(SourceKind.WORKFORCE, _EMPTY_TABLE).rows)

    ais, matched_subscriptions = _extract_ais(inventory, subscriptions)
    systems = _extract_systems(applications)
    skills, personas = _extract_workforce(workforce)
    questions = _build_gap_questions(ais, workforce)

    unusable_rows: list[dict[str, object]] = []
    ignored_subscriptions: list[dict[str, object]] = []
    for index, row in enumerate(subscriptions):
        if index in matched_subscriptions:
            continue
        supplier = _text(row, "Libellé fournisseur")
        description = _text(row, "Objet de la dépense")
        if _looks_unusable(supplier, description):
            unusable_rows.append(
                {
                    "source": _row_evidence(row),
                    "reason": "Ligne inexploitable : information insuffisante, aucune valeur déduite.",
                }
            )
        else:
            ignored_subscriptions.append(
                {
                    "supplier": supplier,
                    "description": description,
                    "source": _row_evidence(row),
                    "reason": "Aucun usage IA identifiable avec une confiance suffisante.",
                }
            )

    return {
        "schema_version": "flow-scout-candidates-v1",
        "ais": ais,
        "systems": systems,
        "skills": skills,
        "personas": personas,
        "activities": [],
        "links": [],
        "gaps": {
            "activities_missing": True,
            "questions": questions,
        },
        "review": {
            "unusable_rows": unusable_rows,
            "ignored_non_ai_subscriptions": ignored_subscriptions,
        },
        "counts": {
            "ais": len(ais),
            "systems": len(systems),
            "skills": len(skills),
            "personas": len(personas),
            "activities": 0,
            "questions": len(questions),
        },
    }


class _EmptyTable:
    rows: tuple[()] = ()


_EMPTY_TABLE = _EmptyTable()


def _extract_ais(
    inventory: list[SourceRow], subscriptions: list[SourceRow]
) -> tuple[list[dict[str, object]], set[int]]:
    result: list[dict[str, object]] = []
    matched: set[int] = set()

    for row in inventory:
        name = _text(row, "Outil")
        description = _text(row, "Ce que ça fait")
        best_index = _best_subscription_match(name, description, subscriptions, matched)
        subscription = subscriptions[best_index] if best_index is not None else None
        if best_index is not None:
            matched.add(best_index)

        owner_person, owner_department = _parse_owner(_text(row, "Qui s'en occupe"))
        ai_act = _text(row, "Risque IA Act") or "Non classée"
        item: dict[str, object] = {
            "candidate_id": f"ai-{len(result) + 1}",
            "kind": "ai",
            "name": name,
            "description": description,
            "status": _normalize_status(_text(row, "Statut")),
            "owner": owner_department,
            "owner_person": owner_person,
            "model": _text(row, "Modèle"),
            "provider": _provider(subscription) if subscription else "",
            "ai_act": ai_act,
            "annual_cost_keur": _cost_keur(subscription) if subscription else 0.0,
            "provenance": "Imported",
            "evidence": _selected_evidence(row, ("Outil", "Ce que ça fait", "Statut")),
            "open_questions": [],
        }
        if subscription:
            item["evidence"].extend(
                _selected_evidence(
                    subscription,
                    ("Libellé fournisseur", "Objet de la dépense", "Montant annuel", "Devise / unité"),
                )
            )
        if not owner_person:
            item["open_questions"].append("Aucun propriétaire nommé trouvé")
        if ai_act == "Non classée":
            item["open_questions"].append("Classification AI Act absente")
        result.append(item)

    for index, row in enumerate(subscriptions):
        if index in matched:
            continue
        supplier = _text(row, "Libellé fournisseur")
        description = _text(row, "Objet de la dépense")
        searchable = _normalized(f"{supplier} {description}")
        if "chatgpt" not in searchable:
            continue
        context = re.sub(r"(?i)^abonnement\s+", "", description)
        context = re.sub(r"\s*\([^)]*\)\s*$", "", context).strip()
        name = f"ChatGPT {context}".strip()
        result.append(
            {
                "candidate_id": f"ai-{len(result) + 1}",
                "kind": "ai",
                "name": name,
                "description": description,
                "status": "Production",
                "owner": "",
                "owner_person": "",
                "model": "GPT-4",
                "provider": "OpenAI",
                "ai_act": "Non classée",
                "annual_cost_keur": _cost_keur(row),
                "provenance": "Imported",
                "evidence": _selected_evidence(
                    row,
                    ("Libellé fournisseur", "Objet de la dépense", "Montant annuel"),
                ),
                "open_questions": [
                    "Absente de l'inventaire IA",
                    "Aucun propriétaire nommé trouvé",
                    "Montant non renseigné" if _value(row, "Montant annuel") is None else "Classification AI Act absente",
                ],
            }
        )
        matched.add(index)

    return result, matched


def _extract_systems(rows: list[SourceRow]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in rows:
        category = _normalized(_text(row, "Catégorie"))
        if category not in {"crm", "erp", "decisionnel", "bi", "bi data"}:
            continue
        raw_name = _text(row, "Application")
        if category == "crm":
            name, system_type = f"CRM {raw_name}", "CRM"
        elif category == "erp":
            name, system_type = f"ERP {raw_name.replace(' ECC', '')}", "ERP"
        else:
            name, system_type = f"BI {raw_name}", "BI / Data"
        result.append(
            {
                "candidate_id": f"system-{len(result) + 1}",
                "kind": "application",
                "name": name,
                "type": system_type,
                "department": _text(row, "Direction"),
                "ai_ready": _ai_ready(row),
                "provenance": "Imported",
                "evidence": _selected_evidence(
                    row, ("Application", "Catégorie", "Direction", "API ?")
                ),
            }
        )
    return result


def _extract_workforce(
    rows: list[SourceRow],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    skills: list[dict[str, object]] = []
    personas: list[dict[str, object]] = []
    for row in rows:
        department = _text(row, "Direction")
        role = _text(row, "Intitulé de poste")
        headcount = _number(row, "ETP")
        skill_name = _text(row, "Compétence clé")
        level = _number(row, "Niveau maîtrise (1-5)")
        succession = _text(row, "Relève identifiée")
        personas.append(
            {
                "candidate_id": f"persona-{len(personas) + 1}",
                "kind": "persona",
                "name": role,
                "department": department,
                "headcount": headcount,
                "provenance": "Imported",
                "evidence": _selected_evidence(row, ("Direction", "Intitulé de poste", "ETP")),
            }
        )
        skills.append(
            {
                "candidate_id": f"skill-{len(skills) + 1}",
                "kind": "skill",
                "name": skill_name,
                "department": department,
                "level": level,
                "headcount": headcount,
                "succession_identified": _normalized(succession) == "oui",
                "criticality": None,
                "provenance": "Imported",
                "evidence": _selected_evidence(
                    row,
                    (
                        "Compétence clé",
                        "Niveau maîtrise (1-5)",
                        "ETP",
                        "Relève identifiée",
                    ),
                ),
                "open_questions": ["Criticité de la compétence à confirmer"],
            }
        )
    return skills, personas


def _build_gap_questions(
    ais: list[dict[str, object]], workforce: list[SourceRow]
) -> list[dict[str, str]]:
    departments = {_normalized(str(item.get("owner", ""))) for item in ais}
    workforce_departments = {_normalized(_text(row, "Direction")) for row in workforce}
    questions: list[dict[str, str]] = []
    if "direction commerciale" in departments or "commerce" in workforce_departments:
        questions.append(
            {
                "department": "Commerce",
                "question": "Sur quoi vos équipes commerciales passent-elles le plus de temps ?",
                "why_asked": "Des IA sont rattachées au Commerce, mais aucune activité n'est déclarée.",
            }
        )
    fragile_production = any(
        _normalized(_text(row, "Direction")) == "production"
        and _number(row, "Niveau maîtrise (1-5)") <= 2
        and _normalized(_text(row, "Relève identifiée")) == "non"
        for row in workforce
    )
    if fragile_production:
        questions.append(
            {
                "department": "Production",
                "question": "Et côté production, quelle est l'activité critique ?",
                "why_asked": "Une compétence Production est fragile et aucune activité n'est rattachée.",
            }
        )
    if "direction financiere" in departments or "finance" in workforce_departments:
        questions.append(
            {
                "department": "Finance",
                "question": "Et en finance ?",
                "why_asked": "Une IA Finance est en pilote, mais aucune activité n'est rattachée.",
            }
        )
    return questions


def _best_subscription_match(
    name: str,
    description: str,
    subscriptions: list[SourceRow],
    excluded: set[int],
) -> int | None:
    source_tokens = _tokens(f"{name} {description}")
    best_index: int | None = None
    best_score = 0
    for index, row in enumerate(subscriptions):
        if index in excluded or _looks_unusable(
            _text(row, "Libellé fournisseur"), _text(row, "Objet de la dépense")
        ):
            continue
        candidate_tokens = _tokens(
            f"{_text(row, 'Libellé fournisseur')} {_text(row, 'Objet de la dépense')}"
        )
        overlap = source_tokens & candidate_tokens
        score = len(overlap)
        if "tresorerie" in overlap:
            score += 2
        if "reclamation" in source_tokens and "ticket" in overlap:
            score += 1
        if score > best_score:
            best_index, best_score = index, score
    return best_index if best_score >= 2 else None


def _tokens(value: str) -> set[str]:
    tokens = set(_normalized(value).split()) - _STOP_WORDS
    normalized: set[str] = set()
    for token in tokens:
        if token.endswith("s") and len(token) > 4:
            token = token[:-1]
        if token.startswith("prevoi") or token.startswith("prevision"):
            token = "prevision"
        if token.startswith("reclam"):
            token = "reclamation"
        if token.startswith("repond") or token.startswith("reponse"):
            token = "reponse"
        normalized.add(token)
    return normalized


def _parse_owner(raw: str) -> tuple[str, str]:
    if not raw:
        return "", ""
    match = re.match(r"\s*(.*?)\s*\((.*?)\)\s*$", raw)
    if match is None:
        return raw.strip(), ""
    person, department = match.groups()
    department = re.sub(r"(?i)^dir\.?\s*", "Direction ", department).strip()
    return person.strip(), department


def _normalize_status(raw: str) -> str:
    value = _normalized(raw)
    if "production" in value:
        return "Production"
    if "pilote" in value:
        return "Pilote"
    if "idee" in value:
        return "Idée"
    return raw.strip()


def _provider(row: SourceRow | None) -> str:
    if row is None:
        return ""
    supplier = _text(row, "Libellé fournisseur")
    normalized = _normalized(supplier)
    if normalized.startswith("openai") or normalized.startswith("open ai"):
        return "OpenAI"
    if normalized.startswith("intercom"):
        return "Intercom"
    if normalized.startswith("sap"):
        return "SAP"
    if normalized.startswith("ovhcloud") and "hebergement" in _normalized(
        _text(row, "Objet de la dépense")
    ):
        return ""
    return supplier


def _cost_keur(row: SourceRow | None) -> float:
    if row is None:
        return 0.0
    amount = _number(row, "Montant annuel")
    unit = _normalized(_text(row, "Devise / unité"))
    if unit in {"keur", "k eur"}:
        return float(amount)
    if unit == "eur":
        return round(float(amount) / 1000, 3)
    return 0.0


def _ai_ready(row: SourceRow) -> int:
    api = _normalized(_text(row, "API ?"))
    comment = _normalized(_text(row, "Commentaire DSI"))
    if api == "oui" and "donnees propres" in comment:
        return 4
    if api == "oui":
        return 3
    if api == "partiel":
        return 3
    if api == "non" and ("ancienne" in comment or "manuelle" in comment):
        return 2
    return 1


def _looks_unusable(supplier: str, description: str) -> bool:
    combined = _normalized(f"{supplier} {description}")
    return not combined or "voir avec compta" in combined or combined == "compta"


def _selected_evidence(row: SourceRow, fields: Iterable[str]) -> list[dict[str, str]]:
    return [row.evidence[field].to_dict() for field in fields if field in row.evidence]


def _row_evidence(row: SourceRow) -> list[dict[str, str]]:
    return [evidence.to_dict() for evidence in row.evidence.values()]


def _value(row: SourceRow, field: str) -> object:
    return row.values.get(field)


def _text(row: SourceRow, field: str) -> str:
    value = _value(row, field)
    return "" if value is None else str(value).strip()


def _number(row: SourceRow, field: str) -> float:
    value = _value(row, field)
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return 0.0


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())
