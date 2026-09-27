"""Interprétation déterministe des réponses de comblement Flow Scout.

Le premier MVP reconnaît quatre familles d'activités du jeu de référence. Toute
instruction glissée dans une réponse est traitée comme une donnée et signalée ; elle
ne peut ni modifier les règles ni créer un objet.
"""

from __future__ import annotations

import re
import unicodedata


def interpret_interview(payload: dict[str, object]) -> dict[str, object]:
    raw_responses = payload.get("reponses", [])
    if not isinstance(raw_responses, list):
        raise ValueError("Le champ 'reponses' doit être une liste.")

    activities_by_key: dict[str, dict[str, object]] = {}
    rejected_instructions: list[dict[str, object]] = []
    processed = 0

    for index, item in enumerate(raw_responses, start=1):
        if not isinstance(item, dict):
            continue
        answer = item.get("reponse", "")
        if not isinstance(answer, str) or not answer.strip():
            continue
        processed += 1
        detected_patterns = detect_prompt_injection(answer)
        if detected_patterns:
            rejected_instructions.append(
                {
                    "response_number": index,
                    "patterns": detected_patterns,
                    "quote": answer.strip(),
                    "action": "Réponse conservée comme donnée, aucune instruction exécutée.",
                }
            )
            continue

        normalized = _normalize(answer)
        if _contains_any(normalized, ("appel d offres", "appels d offres", "memoire technique", " ao ")):
            activities_by_key.setdefault(
                "calls_for_tenders",
                _activity(
                    key="calls_for_tenders",
                    name="Répondre à un appel d'offres",
                    domain="Commerce",
                    criticality=5,
                    value=5,
                    description="Du sourcing de l'AO au dépôt du mémoire technique.",
                    answer=answer,
                    response_number=index,
                    keywords=("appel", "ao", "mémoire technique"),
                ),
            )
        if "reclamation" in normalized:
            activities_by_key.setdefault(
                "customer_complaints",
                _activity(
                    key="customer_complaints",
                    name="Traiter une réclamation client",
                    domain="Commerce",
                    criticality=4,
                    value=3,
                    description="Réception, qualification, réponse et suivi.",
                    answer=answer,
                    response_number=index,
                    keywords=("réclamation",),
                ),
            )
        if _contains_any(normalized, ("planification", "ordonnancement", "planifier")):
            activities_by_key.setdefault(
                "production_planning",
                _activity(
                    key="production_planning",
                    name="Planifier la production",
                    domain="Production",
                    criticality=5,
                    value=4,
                    description="Ordonnancement des ateliers et arbitrage des urgences.",
                    answer=answer,
                    response_number=index,
                    keywords=("planification", "ordonnanc"),
                ),
            )
        if _contains_any(normalized, ("reporting", "cloture", "tableaux de bord")):
            activities_by_key.setdefault(
                "financial_reporting",
                _activity(
                    key="financial_reporting",
                    name="Produire le reporting financier",
                    domain="Finance",
                    criticality=3,
                    value=3,
                    description="Clôture mensuelle et tableaux de bord de direction.",
                    answer=answer,
                    response_number=index,
                    keywords=("reporting", "clôture", "tableaux de bord"),
                ),
            )

    order = (
        "calls_for_tenders",
        "customer_complaints",
        "production_planning",
        "financial_reporting",
    )
    activities = [activities_by_key[key] for key in order if key in activities_by_key]
    return {
        "schema_version": "flow-scout-interview-v1",
        "responses_processed": processed,
        "activities": activities,
        "rejected_instructions": rejected_instructions,
        "safe": not rejected_instructions,
    }


def detect_prompt_injection(text: str) -> list[str]:
    normalized = _normalize(text)
    patterns = {
        "ignore_previous_instructions": (
            "ignore tes instructions",
            "ignore les instructions",
            "instructions precedentes",
        ),
        "system_prompt_request": ("system prompt", "prompt systeme", "message systeme"),
        "score_manipulation": ("attribue un roa", "donne un roa", "roa de 10"),
    }
    return [
        name
        for name, phrases in patterns.items()
        if any(phrase in normalized for phrase in phrases)
    ]


def _activity(
    *,
    key: str,
    name: str,
    domain: str,
    criticality: int,
    value: int,
    description: str,
    answer: str,
    response_number: int,
    keywords: tuple[str, ...],
) -> dict[str, object]:
    return {
        "key": key,
        "kind": "activity",
        "name": name,
        "domain": domain,
        "criticality": criticality,
        "value": value,
        "description": description,
        "provenance": "User declared",
        "evidence": [
            {
                "source": "interview",
                "locator": f"Réponse {response_number}",
                "quote": _evidence_sentence(answer, keywords),
            }
        ],
    }


def _evidence_sentence(answer: str, keywords: tuple[str, ...]) -> str:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", answer) if part.strip()]
    for sentence in sentences:
        normalized = _normalize(sentence)
        if any(_normalize(keyword) in normalized for keyword in keywords):
            return sentence
    return answer.strip()


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    padded = f" {value} "
    return any(needle in padded for needle in needles)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())
