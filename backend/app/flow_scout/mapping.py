"""Correspondance explicite entre colonnes client et vocabulaire Flow Scout.

Une colonne inconnue reste inconnue. Ce choix empêche l'agent de forcer des données
dans un champ voisin et rend les trous visibles avant l'appel à un modèle de langage.
"""

from __future__ import annotations

import re
import unicodedata

from app.flow_scout.models import IngestionBatch, SourceKind

_MAPPINGS: dict[SourceKind, dict[str, str]] = {
    SourceKind.SUBSCRIPTIONS: {
        "libelle fournisseur": "supplier",
        "objet de la depense": "description",
        "montant annuel": "annual_amount",
        "devise unite": "amount_unit",
    },
    SourceKind.APPLICATIONS: {
        "application": "name",
        "categorie": "category",
        "direction": "department",
        "criticite 1 5": "criticality",
        "api": "api_status",
    },
    SourceKind.WORKFORCE: {
        "direction": "department",
        "intitule de poste": "role",
        "etp": "headcount",
        "competence cle": "key_skill",
        "niveau maitrise 1 5": "mastery_level",
        "releve identifiee": "succession_identified",
    },
    SourceKind.AI_INVENTORY: {
        "outil": "name",
        "ce que ca fait": "description",
        "statut": "status",
        "qui s en occupe": "owner",
        "modele": "model",
        "risque ia act": "ai_act_risk",
    },
}


def build_column_mapping_report(batch: IngestionBatch) -> dict[str, object]:
    mapped: list[dict[str, str]] = []
    unmapped: list[dict[str, str]] = []
    for table in batch.tables:
        mapping = _MAPPINGS.get(table.kind, {})
        for header in table.headers:
            normalized = normalize_label(header)
            target = mapping.get(normalized)
            item = {
                "file": table.file_name,
                "sheet": table.sheet_name,
                "source_kind": table.kind.value,
                "source_column": header,
            }
            if target is None:
                unmapped.append(item)
            else:
                mapped.append({**item, "target_field": target})

    total = len(mapped) + len(unmapped)
    rate = round(100 * len(mapped) / total, 2) if total else 0.0
    return {
        "total_columns": total,
        "mapped_columns": len(mapped),
        "unmapped_columns_count": len(unmapped),
        "mapping_rate_pct": rate,
        "target_met": rate >= 85.0,
        "mapped": mapped,
        "unmapped": unmapped,
    }


def normalize_label(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())
