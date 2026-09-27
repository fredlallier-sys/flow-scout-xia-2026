"""Lecture déterministe de tableaux CSV et XLSX pour Flow Scout.

Le lecteur XLSX est volontairement fondé sur le format Open XML standard. Il évite
d'imposer une bibliothèque lourde au serveur et suffit pour les classeurs tabulaires
attendus par Flow Scout. Aucune macro et aucune formule n'est exécutée.
"""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from io import StringIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from app.flow_scout.models import (
    CellEvidence,
    IngestionBatch,
    Scalar,
    SourceKind,
    SourceRow,
    SourceTable,
)
from app.flow_scout.mapping import normalize_label

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_KIND_SIGNATURES: tuple[tuple[SourceKind, frozenset[str]], ...] = (
    (
        SourceKind.COLLECTION_CATALOG,
        frozenset({"id", "famille", "source a rechercher", "priorite proposee"}),
    ),
    (SourceKind.SUBSCRIPTIONS, frozenset({"libelle fournisseur", "objet de la depense", "montant annuel"})),
    (SourceKind.APPLICATIONS, frozenset({"application", "categorie", "direction", "criticite 1 5"})),
    (SourceKind.WORKFORCE, frozenset({"direction", "intitule de poste", "etp", "competence cle"})),
    (SourceKind.AI_INVENTORY, frozenset({"outil", "ce que ca fait", "statut", "modele"})),
    (SourceKind.DEMO_GUIDE, frozenset({"repere", "description"})),
    (
        SourceKind.DEMO_COLLECTION,
        frozenset({"source id", "famille", "source", "mode prevu", "nombre de faits"}),
    ),
    (
        SourceKind.DEMO_EXTRACTS,
        frozenset({"extrait id", "source id", "champ", "valeur synthetique"}),
    ),
    (
        SourceKind.DEMO_ORGANIZATION,
        frozenset({"team id", "equipe", "persona id", "persona representatif", "etp equipe"}),
    ),
    (
        SourceKind.DEMO_ACTIVITIES,
        frozenset({"activity id", "persona id", "activite", "decision id", "volume mensuel"}),
    ),
    (
        SourceKind.DEMO_DECISIONS,
        frozenset({"decision id", "activity id", "decision", "responsable", "regle"}),
    ),
    (
        SourceKind.DEMO_APPLICATIONS,
        frozenset({"application id", "application fictive", "domaine", "hebergement declare"}),
    ),
    (
        SourceKind.DEMO_AI,
        frozenset({"ai id", "ia fonction fictive", "activity id", "d observe", "d autorise"}),
    ),
    (
        SourceKind.DEMO_COSTS,
        frozenset({"cost id", "ai id", "poste", "montant eur", "regle d imputation"}),
    ),
    (
        SourceKind.DEMO_VALUE,
        frozenset({"value id", "ai id", "heures liberees simulees", "economie budgetaire eur"}),
    ),
    (
        SourceKind.DEMO_METRICS,
        frozenset({"metric id", "activity id", "mesure", "valeur", "unite"}),
    ),
    (
        SourceKind.DEMO_EVENTS,
        frozenset({"event id", "case id", "etape", "horodatage utc", "executant"}),
    ),
    (
        SourceKind.DEMO_RELATIONS,
        frozenset({"relation id", "objet source", "relation", "objet cible", "preuve source id"}),
    ),
    (
        SourceKind.DEMO_EXPECTED_RESULTS,
        frozenset({"test", "constat attendu", "objets concernes", "resultat de reference"}),
    ),
    (SourceKind.DEMO_SUMMARY, frozenset({"indicateur", "valeur"})),
)


class IngestionError(ValueError):
    """Fichier illisible ou incompatible avec le contrat d'ingestion."""


def ingest_file(path: str | Path) -> tuple[SourceTable, ...]:
    source = Path(path)
    if not source.is_file():
        raise IngestionError(f"Fichier introuvable : {source}")

    suffix = source.suffix.casefold()
    if suffix == ".csv":
        return (_read_csv(source),)
    if suffix == ".xlsx":
        return _read_xlsx(source)
    raise IngestionError(f"Format non supporté : {source.suffix or '(sans extension)'}")


def ingest_directory(path: str | Path, *, prefer_xlsx: bool = True) -> IngestionBatch:
    """Ingère un dépôt de fichiers en évitant les doublons CSV/XLSX de même nom."""
    root = Path(path)
    if not root.is_dir():
        raise IngestionError(f"Répertoire introuvable : {root}")

    supported = sorted(
        (candidate for candidate in root.iterdir() if candidate.is_file() and candidate.suffix.casefold() in {".csv", ".xlsx"}),
        key=lambda candidate: candidate.name.casefold(),
    )
    unsupported = tuple(
        sorted(
            candidate.name
            for candidate in root.iterdir()
            if candidate.is_file() and not candidate.name.startswith(".") and candidate.suffix.casefold() not in {".csv", ".xlsx"}
        )
    )

    selected: list[Path] = []
    skipped: list[str] = []
    by_stem: dict[str, list[Path]] = {}
    for candidate in supported:
        by_stem.setdefault(candidate.stem.casefold(), []).append(candidate)

    for candidates in by_stem.values():
        candidates.sort(key=lambda candidate: candidate.suffix.casefold())
        xlsx = next((item for item in candidates if item.suffix.casefold() == ".xlsx"), None)
        csv_file = next((item for item in candidates if item.suffix.casefold() == ".csv"), None)
        chosen = xlsx if prefer_xlsx and xlsx is not None else csv_file or xlsx
        if chosen is not None:
            selected.append(chosen)
            skipped.extend(item.name for item in candidates if item != chosen)

    tables: list[SourceTable] = []
    for source in sorted(selected, key=lambda candidate: candidate.name.casefold()):
        tables.extend(ingest_file(source))

    return IngestionBatch(
        tables=tuple(tables),
        skipped_mirrors=tuple(sorted(skipped)),
        unsupported_files=unsupported,
    )


def classify_headers(headers: Iterable[str]) -> SourceKind:
    normalized = {normalize_label(header) for header in headers if header.strip()}
    for kind, signature in _KIND_SIGNATURES:
        if signature.issubset(normalized):
            return kind
    return SourceKind.UNKNOWN


def _read_csv(path: Path) -> SourceTable:
    text = path.read_text(encoding="utf-8-sig")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t,")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"

    reader = csv.reader(StringIO(text), dialect)
    all_rows = list(reader)
    header_index = _header_row_index(all_rows)
    if header_index is None:
        raise IngestionError(f"Fichier vide : {path.name}")

    headers = _deduplicate_headers(all_rows[header_index])
    rows, empty_count = _make_rows(
        file_name=path.name,
        sheet_name="CSV",
        headers=headers,
        raw_rows=(
            (row_index + 1, [_parse_scalar(value) for value in row])
            for row_index, row in enumerate(
                all_rows[header_index + 1 :], start=header_index + 1
            )
        ),
    )
    return SourceTable(
        file_name=path.name,
        sheet_name="CSV",
        kind=classify_headers(headers),
        headers=tuple(headers),
        rows=tuple(rows),
        ignored_empty_rows=empty_count,
    )


def _read_xlsx(path: Path) -> tuple[SourceTable, ...]:
    try:
        archive = ZipFile(path)
    except BadZipFile as exc:
        raise IngestionError(f"Classeur XLSX invalide : {path.name}") from exc

    with archive:
        shared_strings = _read_shared_strings(archive)
        sheets = _sheet_paths(archive)
        tables: list[SourceTable] = []
        for sheet_name, xml_path in sheets:
            matrix = _read_sheet_matrix(archive, xml_path, shared_strings)
            header_index = _header_row_index([values for _, values in matrix])
            if header_index is None:
                continue
            header_row_number, header_values = matrix[header_index]
            headers = _deduplicate_headers([_display(value) for value in header_values])
            rows, empty_count = _make_rows(
                file_name=path.name,
                sheet_name=sheet_name,
                headers=headers,
                raw_rows=matrix[header_index + 1 :],
            )
            warnings: list[str] = []
            if header_row_number != 1:
                warnings.append(f"En-tête détecté à la ligne {header_row_number}")
            tables.append(
                SourceTable(
                    file_name=path.name,
                    sheet_name=sheet_name,
                    kind=classify_headers(headers),
                    headers=tuple(headers),
                    rows=tuple(rows),
                    ignored_empty_rows=empty_count,
                    warnings=tuple(warnings),
                )
            )
        if not tables:
            raise IngestionError(f"Aucune feuille tabulaire trouvée : {path.name}")
        return tuple(tables)


def _make_rows(
    *,
    file_name: str,
    sheet_name: str,
    headers: list[str],
    raw_rows: Iterable[tuple[int, list[Scalar]]],
) -> tuple[list[SourceRow], int]:
    result: list[SourceRow] = []
    ignored_empty_rows = 0
    for row_number, raw_values in raw_rows:
        padded = list(raw_values[: len(headers)]) + [None] * max(0, len(headers) - len(raw_values))
        if not any(not _is_empty(value) for value in padded):
            ignored_empty_rows += 1
            continue

        values: dict[str, Scalar] = {}
        evidence: dict[str, CellEvidence] = {}
        for column_index, header in enumerate(headers, start=1):
            value = padded[column_index - 1]
            values[header] = value
            if not _is_empty(value):
                evidence[header] = CellEvidence(
                    file=file_name,
                    sheet=sheet_name,
                    cell=f"{_column_letter(column_index)}{row_number}",
                    quote=_display(value),
                )
        result.append(SourceRow(row_number=row_number, values=values, evidence=evidence))
    return result, ignored_empty_rows


def _sheet_paths(archive: ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in relationships.findall(f"{{{_PKG_REL_NS}}}Relationship")
    }
    result: list[tuple[str, str]] = []
    sheets = workbook.find(f"{{{_MAIN_NS}}}sheets")
    if sheets is None:
        return result
    for sheet in sheets:
        relationship_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
        target = rel_targets.get(relationship_id or "")
        if target is None:
            continue
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        result.append((sheet.attrib.get("name", "Feuille"), target))
    return result


def _read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t")) for item in root]


def _read_sheet_matrix(
    archive: ZipFile,
    xml_path: str,
    shared_strings: list[str],
) -> list[tuple[int, list[Scalar]]]:
    root = ET.fromstring(archive.read(xml_path))
    sheet_data = root.find(f"{{{_MAIN_NS}}}sheetData")
    if sheet_data is None:
        return []
    result: list[tuple[int, list[Scalar]]] = []
    for row in sheet_data.findall(f"{{{_MAIN_NS}}}row"):
        row_number = int(row.attrib.get("r", len(result) + 1))
        cells: dict[int, Scalar] = {}
        for cell in row.findall(f"{{{_MAIN_NS}}}c"):
            reference = cell.attrib.get("r", "A1")
            match = re.match(r"([A-Z]+)", reference.upper())
            if match is None:
                continue
            column_number = _column_number(match.group(1))
            cells[column_number] = _xlsx_cell_value(cell, shared_strings)
        width = max(cells, default=0)
        result.append((row_number, [cells.get(column) for column in range(1, width + 1)]))
    return result


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> Scalar:
    cell_type = cell.attrib.get("t", "n")
    if cell_type == "inlineStr":
        inline = cell.find(f"{{{_MAIN_NS}}}is")
        if inline is None:
            return ""
        return "".join(node.text or "" for node in inline.iter(f"{{{_MAIN_NS}}}t"))

    value_node = cell.find(f"{{{_MAIN_NS}}}v")
    if value_node is None or value_node.text is None:
        return None
    raw = value_node.text
    if cell_type == "s":
        index = int(raw)
        return shared_strings[index] if 0 <= index < len(shared_strings) else raw
    if cell_type in {"str", "e"}:
        return raw
    if cell_type == "b":
        return raw == "1"
    return _parse_scalar(raw)


def _header_row_index(rows: list[list[object]]) -> int | None:
    """Repère un vrai en-tête même si le classeur commence par un titre.

    Les signatures connues ont priorité. Pour une feuille non reconnue, le
    comportement historique est conservé : première ligne non vide.
    """
    fallback = _first_non_empty_row(rows)
    for index, row in enumerate(rows):
        labels = {
            normalize_label(_display(value))
            for value in row
            if not _is_empty(value)
        }
        if any(signature.issubset(labels) for _, signature in _KIND_SIGNATURES):
            return index
    return fallback


def _first_non_empty_row(rows: list[list[object]]) -> int | None:
    for index, row in enumerate(rows):
        if any(not _is_empty(value) for value in row):
            return index
    return None


def _deduplicate_headers(raw_headers: list[str]) -> list[str]:
    result: list[str] = []
    seen: dict[str, int] = {}
    for index, raw in enumerate(raw_headers, start=1):
        base = raw.strip() or f"Colonne {index}"
        seen[base] = seen.get(base, 0) + 1
        result.append(base if seen[base] == 1 else f"{base} ({seen[base]})")
    return result


def _parse_scalar(value: str) -> Scalar:
    stripped = value.strip()
    if stripped == "":
        return None
    normalized_number = stripped.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if re.fullmatch(r"[-+]?\d+", normalized_number):
        try:
            return int(normalized_number)
        except ValueError:
            pass
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", normalized_number):
        try:
            return float(normalized_number)
        except ValueError:
            pass
    return stripped


def _is_empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _display(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _column_number(letters: str) -> int:
    number = 0
    for char in letters:
        number = number * 26 + ord(char) - ord("A") + 1
    return number


def _column_letter(number: int) -> str:
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters
