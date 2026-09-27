"""Référentiel de collecte Flow Scout.

Un catalogue décrit les sources qu'une mission pourrait demander. Il ne constitue
jamais une preuve client et ne doit pas alimenter directement le graphe Atlas.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import unicodedata

from app.flow_scout.ingestion import IngestionError, ingest_file
from app.flow_scout.models import SourceKind, SourceRow

_SHARED_FAMILIES = (
    "Stratégie et organisation",
    "Finance, achats et coût complet",
    "Applications, architecture et exploitation",
    "Données et patrimoine documentaire",
    "IA, agents et usages réels",
    "Gouvernance, conformité et cybersécurité",
    "Travail informel et connaissances tacites",
)

_FOCUS_ALIASES = {
    "sinistre": "Sinistres et indemnisation",
    "sinistres": "Sinistres et indemnisation",
    "sinistre habitation": "Sinistres et indemnisation",
    "gestion d un sinistre habitation": "Sinistres et indemnisation",
}


def load_collection_catalog(
    path: str | Path,
    *,
    focus_family: str | None = None,
    priorities: tuple[str, ...] = ("P0",),
) -> dict[str, object]:
    """Charge un inventaire de collecte et propose un périmètre de départ."""
    source = Path(path)
    table = next(
        (
            candidate
            for candidate in ingest_file(source)
            if candidate.kind is SourceKind.COLLECTION_CATALOG
        ),
        None,
    )
    if table is None:
        raise IngestionError(
            "Aucun onglet d'inventaire n'a été trouvé. Colonnes minimales : "
            "ID, Famille, Source à rechercher, Priorité proposée."
        )

    items = [_catalog_item(row) for row in table.rows]
    items = [item for item in items if item["id"] and item["source_name"]]
    if not items:
        raise IngestionError("L'onglet d'inventaire ne contient aucune source exploitable.")

    family_counts = Counter(str(item["family"]) for item in items)
    priority_counts = Counter(str(item["priority"]) for item in items)
    mode_counts = Counter(str(item["collection_mode_code"]) for item in items)
    normalized_priorities = tuple(
        priority.strip().upper() for priority in priorities if priority.strip()
    ) or ("P0",)
    resolved_focus = _resolve_focus_family(focus_family, tuple(family_counts))
    selected_families = set(_SHARED_FAMILIES)
    if resolved_focus:
        selected_families.add(resolved_focus)

    recommended = [
        item
        for item in items
        if item["priority"] in normalized_priorities
        and (not resolved_focus or item["family"] in selected_families)
    ]
    phases = _build_phases(recommended, resolved_focus)

    return {
        "schema_version": "flow-scout-collection-catalog-v1",
        "catalog_role": "collection_reference",
        "is_client_evidence": False,
        "warning": (
            "Ce catalogue guide la collecte. Ses lignes ne prouvent ni l'existence "
            "d'un système client, ni un usage IA, ni une valeur réalisée."
        ),
        "source_file": source.name,
        "source_sheet": table.sheet_name,
        "source_count": len(items),
        "family_count": len(family_counts),
        "counts": {
            "by_family": dict(sorted(family_counts.items())),
            "by_priority": dict(sorted(priority_counts.items())),
            "by_collection_mode": dict(sorted(mode_counts.items())),
        },
        "recommended_collection": {
            "focus_family": resolved_focus,
            "priorities": list(normalized_priorities),
            "source_count": len(recommended),
            "phases": phases,
            "items": recommended,
        },
        "items": items,
    }


def _catalog_item(row: SourceRow) -> dict[str, object]:
    mode = _text(row, "Mode de collecte")
    mode_parts = re.split(r"\s+[—-]\s+", mode, maxsplit=1)
    mode_code = mode_parts[0].strip() if mode_parts else ""
    mode_label = mode_parts[1].strip() if len(mode_parts) > 1 else mode
    return {
        "id": _text(row, "ID"),
        "family": _text(row, "Famille"),
        "source_name": _text(row, "Source à rechercher"),
        "formats": _split(_text(row, "Formats possibles"), r"[,;]"),
        "information_to_extract": _text(row, "Informations à extraire"),
        "likely_owner": _text(row, "Détenteur probable"),
        "collection_mode_code": mode_code,
        "collection_mode": mode_label,
        "flow_scout_processing": _text(row, "Traitement Flow Scout"),
        "atlas_outputs": _split(_text(row, "Objets / informations Atlas"), r"[,;]"),
        "strategic_categories": _split(_text(row, "Catégories IA possibles"), r"[;]"),
        "priority": _text(row, "Priorité proposée").upper(),
        "review_period": _text(row, "Période / mise à jour proposée"),
        "sensitivity": _text(row, "Sensibilité"),
        "collection_status": _text(row, "Statut de collecte"),
        "owner_comment": _text(row, "Responsable / commentaire"),
        "provenance": "Reference catalogue",
        "evidence": [
            evidence.to_dict()
            for key, evidence in row.evidence.items()
            if key in {"ID", "Famille", "Source à rechercher", "Priorité proposée"}
        ],
    }


def _build_phases(
    items: list[dict[str, object]], focus_family: str | None
) -> list[dict[str, object]]:
    phase_families = (
        (
            "Cadrer le périmètre et les règles",
            {
                "Stratégie et organisation",
                "Gouvernance, conformité et cybersécurité",
            },
        ),
        (
            "Reconstituer le travail et les décisions",
            {
                family
                for family in (
                    focus_family,
                    "Travail informel et connaissances tacites",
                )
                if family
            },
        ),
        (
            "Qualifier systèmes, données, IA et coûts",
            {
                "Finance, achats et coût complet",
                "Applications, architecture et exploitation",
                "Données et patrimoine documentaire",
                "IA, agents et usages réels",
            },
        ),
    )
    phases: list[dict[str, object]] = []
    assigned: set[str] = set()
    for index, (name, families) in enumerate(phase_families, start=1):
        phase_items = [item for item in items if item["family"] in families]
        if not phase_items:
            continue
        assigned.update(str(item["id"]) for item in phase_items)
        phases.append(
            {
                "order": index,
                "name": name,
                "source_count": len(phase_items),
                "source_ids": [item["id"] for item in phase_items],
            }
        )
    remaining = [item for item in items if str(item["id"]) not in assigned]
    if remaining:
        phases.append(
            {
                "order": len(phases) + 1,
                "name": "Compléter le périmètre ciblé",
                "source_count": len(remaining),
                "source_ids": [item["id"] for item in remaining],
            }
        )
    return phases


def _resolve_focus_family(
    focus_family: str | None, available_families: tuple[str, ...]
) -> str | None:
    if not focus_family or not focus_family.strip():
        return None
    wanted = _normalize(focus_family)
    alias = _FOCUS_ALIASES.get(wanted)
    if alias:
        return alias
    for family in available_families:
        normalized = _normalize(family)
        if wanted == normalized or wanted in normalized or normalized in wanted:
            return family
    raise IngestionError(f"Famille de collecte inconnue : {focus_family}.")


def _text(row: SourceRow, header: str) -> str:
    value = row.values.get(header)
    return "" if value is None else str(value).strip()


def _split(value: str, pattern: str) -> list[str]:
    return [item.strip() for item in re.split(pattern, value) if item.strip()]


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())
