"""Génération locale d'un classeur NEXUS v2 compatible avec Atlas.

Le générateur n'appelle aucun service externe. Il produit un fichier OOXML minimal,
lisible par Excel et LibreOffice, à partir du pont tabulaire défini dans ``nexus.py``.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from io import BytesIO
from numbers import Real
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
from xml.etree import ElementTree as ET

from app.flow_scout.nexus import NEXUS_V2_HEADERS, build_nexus_v2_payload
from app.flow_scout.nexus_v3 import (
    NEXUS_V3_HEADERS,
    NEXUS_V3_SHEET_ORDER,
    assert_nexus_v3_headers,
    build_nexus_v3_payload,
)

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_CORE_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_DCTERMS_NS = "http://purl.org/dc/terms/"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
_VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
_XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("", _MAIN_NS)
ET.register_namespace("r", _REL_NS)

_SHEET_ORDER = (
    "Lisez-moi",
    "Use cases",
    "Agents",
    "Sources",
    "Briques",
    "Transition Board",
    "Tasks_Roles_Skills",
    "NEXUS V2 Readme",
)

_READ_ME_ROWS = (
    {"section": "Format", "instruction": "Classeur NEXUS v2 généré par Flow Scout."},
    {
        "section": "Import Atlas",
        "instruction": "Importer les six onglets de données sans renommer leurs colonnes.",
    },
    {
        "section": "Cellules vides",
        "instruction": "Une cellule vide signifie que l'information n'est pas encore confirmée. Elle ne vaut pas zéro.",
    },
    {
        "section": "Agents et briques",
        "instruction": "Ces onglets restent vides tant qu'aucun agent ou composant technique distinct n'est prouvé.",
    },
    {
        "section": "Référence complète",
        "instruction": "Le graphe JSON Flow Scout conserve les preuves, relations et questions que NEXUS v2 ne peut pas représenter.",
    },
)

_NEXUS_README_ROWS = (
    {"champ": "Version", "description": "nexus-import-v2-bridge"},
    {"champ": "Use cases", "description": "Usages IA et automatisations confirmés."},
    {"champ": "Sources", "description": "Systèmes et répertoires de données associés."},
    {"champ": "Tasks_Roles_Skills", "description": "Activités, rôles et compétences issus de Flow Scout."},
    {
        "champ": "Compatibilité",
        "description": "Projection avec pertes contrôlées ; le JSON Flow Scout reste la source canonique.",
    },
)

_NEXUS_V3_README_ROWS = (
    {"section": "Contrat", "instruction": "Flow Atlas v3 : objets, relations, mesures, constats, preuves, questions, règles et contrôles."},
    {"section": "Compatibilité", "instruction": "Les huit premiers onglets et leurs colonnes NEXUS v2 sont conservés à l'identique."},
    {"section": "Maïeutique", "instruction": "Les questions suivent le parcours Situer → Comprendre → Évaluer → Déléguer → Prioriser."},
    {"section": "Inconnues", "instruction": "Une cellule vide reste inconnue ; Import Control et Atlas Questions indiquent ce qui doit être confirmé."},
    {"section": "Compétences", "instruction": "Aucune compétence n'est inventée : les activités assistées par IA déclenchent une qualification métier/RH."},
    {"section": "Import", "instruction": "Atlas doit refuser une décision finale tant qu'une question bloquante reste ouverte."},
)


def build_nexus_v2_xlsx(graph: dict[str, object]) -> bytes:
    """Construit le classeur NEXUS v2 correspondant à un graphe Flow Scout."""
    return export_nexus_v2_xlsx(build_nexus_v2_payload(graph))


def export_nexus_v2_xlsx(payload: dict[str, object]) -> bytes:
    """Sérialise un payload NEXUS v2 en classeur XLSX."""
    assert_nexus_v2_headers(payload)
    sheets = _sheet_specs(payload)
    return _export_xlsx(sheets, title="Import NEXUS v2 pour Flow Atlas")


def build_nexus_v3_xlsx(report: dict[str, object]) -> bytes:
    """Construit le classeur Atlas v3 depuis le rapport des sept cartes."""
    return export_nexus_v3_xlsx(build_nexus_v3_payload(report))


def export_nexus_v3_xlsx(payload: dict[str, object]) -> bytes:
    """Sérialise un payload Atlas v3 tout en préservant NEXUS v2."""
    assert_nexus_v3_headers(payload)
    return _export_xlsx(_sheet_specs_v3(payload), title="Import Flow Atlas v3")


def _export_xlsx(
    sheets: list[
        tuple[str, list[str], list[dict[str, object]], list[tuple[str, list[str]]]]
    ],
    *,
    title: str,
) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        _write(archive, "[Content_Types].xml", _content_types_xml(len(sheets)))
        _write(archive, "_rels/.rels", _root_relationships_xml())
        _write(archive, "docProps/core.xml", _core_properties_xml(title))
        _write(archive, "docProps/app.xml", _app_properties_xml([name for name, *_ in sheets]))
        _write(archive, "xl/workbook.xml", _workbook_xml([name for name, *_ in sheets]))
        _write(archive, "xl/_rels/workbook.xml.rels", _workbook_relationships_xml(len(sheets)))
        _write(archive, "xl/styles.xml", _styles_xml())
        for index, (name, headers, rows, validations) in enumerate(sheets, start=1):
            _write(
                archive,
                f"xl/worksheets/sheet{index}.xml",
                _worksheet_xml(name, headers, rows, validations),
            )
    return buffer.getvalue()


def _sheet_specs_v3(
    payload: dict[str, object],
) -> list[tuple[str, list[str], list[dict[str, object]], list[tuple[str, list[str]]]]]:
    payload_sheets = payload.get("sheets")
    if not isinstance(payload_sheets, dict):
        raise ValueError("Le payload Atlas v3 ne contient pas de feuilles.")

    source_values = ["INT"]
    source_sheet = payload_sheets.get("Sources")
    if isinstance(source_sheet, dict) and isinstance(source_sheet.get("rows"), list):
        source_values = [
            str(row.get("id"))
            for row in source_sheet["rows"]
            if isinstance(row, dict) and row.get("id")
        ] or source_values

    specs: list[tuple[str, list[str], list[dict[str, object]], list[tuple[str, list[str]]]]] = []
    for name in NEXUS_V3_SHEET_ORDER:
        if name == "Lisez-moi":
            rows = [*_READ_ME_ROWS, {"section": "Atlas v3", "instruction": "Consulter NEXUS V3 Readme, Import Control et Atlas Questions avant tout arbitrage."}]
            specs.append((name, ["section", "instruction"], rows, []))
            continue
        if name == "NEXUS V2 Readme":
            specs.append((name, ["champ", "description"], list(_NEXUS_README_ROWS), []))
            continue
        if name == "NEXUS V3 Readme":
            specs.append((name, ["section", "instruction"], list(_NEXUS_V3_README_ROWS), []))
            continue
        sheet = payload_sheets.get(name)
        if not isinstance(sheet, dict):
            raise ValueError(f"Feuille Atlas v3 absente : {name}")
        headers = sheet.get("headers")
        rows = sheet.get("rows")
        if not isinstance(headers, list) or not all(isinstance(item, str) for item in headers):
            raise ValueError(f"En-têtes invalides pour la feuille {name}.")
        if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
            raise ValueError(f"Lignes invalides pour la feuille {name}.")
        specs.append((name, headers, rows, _validations_v3(name, source_values)))
    return specs


def _sheet_specs(
    payload: dict[str, object],
) -> list[tuple[str, list[str], list[dict[str, object]], list[tuple[str, list[str]]]]]:
    payload_sheets = payload.get("sheets")
    if not isinstance(payload_sheets, dict):
        raise ValueError("Le payload NEXUS ne contient pas de feuilles.")

    source_values = ["INT"]
    source_sheet = payload_sheets.get("Sources")
    if isinstance(source_sheet, dict):
        source_rows = source_sheet.get("rows")
        if isinstance(source_rows, list):
            source_values = [
                str(row.get("id"))
                for row in source_rows
                if isinstance(row, dict) and row.get("id")
            ] or source_values

    specs: list[tuple[str, list[str], list[dict[str, object]], list[tuple[str, list[str]]]]] = []
    for name in _SHEET_ORDER:
        if name == "Lisez-moi":
            specs.append((name, ["section", "instruction"], list(_READ_ME_ROWS), []))
            continue
        if name == "NEXUS V2 Readme":
            specs.append((name, ["champ", "description"], list(_NEXUS_README_ROWS), []))
            continue
        sheet = payload_sheets.get(name)
        if not isinstance(sheet, dict):
            raise ValueError(f"Feuille NEXUS absente : {name}")
        headers = sheet.get("headers")
        rows = sheet.get("rows")
        if not isinstance(headers, list) or not all(isinstance(item, str) for item in headers):
            raise ValueError(f"En-têtes invalides pour la feuille {name}.")
        if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
            raise ValueError(f"Lignes invalides pour la feuille {name}.")
        specs.append((name, headers, rows, _validations(name, source_values)))
    return specs


def _validations(sheet_name: str, source_values: list[str]) -> list[tuple[str, list[str]]]:
    yes_no = ["Oui", "Non"]
    if sheet_name == "Use cases":
        return [
            ("C2:C300", ["Relation client", "Souscription", "Sinistres", "Finance", "RH", "IT / Run", "Marketing", "Conformité"]),
            ("D2:D300", ["Assistant", "Copilote", "Agent autonome", "Automatisation", "Analytics"]),
            ("E2:E300", ["Idée", "Cadrage", "POC", "Pilote", "Production", "Déprécié"]),
            ("L2:L300", ["Faible", "Moyen", "Élevé"]),
            ("O2:O300", ["Haut risque", "Risque limité", "Minimal", "Inacceptable"]),
            ("Q2:Q300", yes_no),
            ("R2:R300", yes_no),
            ("S2:S300", source_values),
        ]
    if sheet_name == "Agents":
        return [
            ("D2:D300", ["Assistant", "Copilote", "Agent autonome", "Automatisation", "Analytics"]),
            ("E2:E300", ["Supervisé", "Semi-autonome", "Autonome"]),
            ("F2:F300", ["Actif", "Surveillé", "Test", "En conception", "Retiré"]),
            ("M2:M300", source_values),
        ]
    if sheet_name == "Sources":
        return [("F2:F300", ["Connecté", "Sync en cours", "À configurer"])]
    return []


def _validations_v3(
    sheet_name: str, source_values: list[str]
) -> list[tuple[str, list[str]]]:
    legacy = _validations(sheet_name, source_values)
    if legacy:
        return legacy
    if sheet_name == "Atlas Objects":
        return [
            ("B2:B2000", ["team", "persona", "activity", "decision", "knowledge_source", "application", "ai_usage", "transformation_opportunity"]),
            ("E2:E2000", ["Confort", "Productivité", "Sécurisation", "Go-to-market", "Produit", "Stratégique"]),
        ]
    if sheet_name == "Atlas Measures":
        return [("I2:I4000", ["observed", "derived", "estimated", "confirmed", "rejected"])]
    if sheet_name == "Atlas Findings":
        return [("H2:H1000", ["open", "confirmed", "resolved", "rejected"])]
    if sheet_name == "Atlas Questions":
        return [
            ("B2:B2000", ["Situer", "Comprendre", "Évaluer", "Déléguer", "Prioriser"]),
            ("J2:J2000", ["Oui", "Non"]),
            ("K2:K2000", ["Oui", "Non"]),
            ("L2:L2000", ["P0", "P1", "P2"]),
            ("M2:M2000", ["Open", "Answered", "Validated", "Rejected"]),
        ]
    if sheet_name == "Import Control":
        return [("C2:C2000", ["PASS", "WARN", "OPEN", "FAIL"])]
    return []


def _worksheet_xml(
    sheet_name: str,
    headers: list[str],
    rows: list[dict[str, object]],
    validations: list[tuple[str, list[str]]],
) -> bytes:
    root = ET.Element(_q(_MAIN_NS, "worksheet"))
    dimension_end = f"{_column_name(len(headers))}{max(1, len(rows) + 1)}"
    ET.SubElement(root, _q(_MAIN_NS, "dimension"), {"ref": f"A1:{dimension_end}"})
    views = ET.SubElement(root, _q(_MAIN_NS, "sheetViews"))
    view = ET.SubElement(views, _q(_MAIN_NS, "sheetView"), {"workbookViewId": "0"})
    if sheet_name not in {"Lisez-moi", "NEXUS V2 Readme", "NEXUS V3 Readme"}:
        ET.SubElement(
            view,
            _q(_MAIN_NS, "pane"),
            {"ySplit": "1", "topLeftCell": "A2", "activePane": "bottomLeft", "state": "frozen"},
        )
    ET.SubElement(root, _q(_MAIN_NS, "sheetFormatPr"), {"defaultRowHeight": "18"})

    cols = ET.SubElement(root, _q(_MAIN_NS, "cols"))
    for index, header in enumerate(headers, start=1):
        width = _column_width(header, rows)
        ET.SubElement(
            cols,
            _q(_MAIN_NS, "col"),
            {"min": str(index), "max": str(index), "width": f"{width:.1f}", "customWidth": "1"},
        )

    sheet_data = ET.SubElement(root, _q(_MAIN_NS, "sheetData"))
    header_row = ET.SubElement(sheet_data, _q(_MAIN_NS, "row"), {"r": "1", "ht": "24", "customHeight": "1"})
    for column, header in enumerate(headers, start=1):
        _append_cell(header_row, 1, column, header, style=1)
    for row_index, row_data in enumerate(rows, start=2):
        row_element = ET.SubElement(sheet_data, _q(_MAIN_NS, "row"), {"r": str(row_index)})
        for column, header in enumerate(headers, start=1):
            value = row_data.get(header)
            if value is None or value == "":
                continue
            _append_cell(row_element, row_index, column, value, style=2)

    ET.SubElement(root, _q(_MAIN_NS, "autoFilter"), {"ref": f"A1:{dimension_end}"})
    if validations:
        validations_element = ET.SubElement(
            root,
            _q(_MAIN_NS, "dataValidations"),
            {"count": str(len(validations))},
        )
        for sqref, values in validations:
            validation = ET.SubElement(
                validations_element,
                _q(_MAIN_NS, "dataValidation"),
                {
                    "type": "list",
                    "allowBlank": "1",
                    "showErrorMessage": "1",
                    "errorTitle": "Valeur non reconnue",
                    "error": "Choisissez une valeur de la liste.",
                    "sqref": sqref,
                },
            )
            formula = ET.SubElement(validation, _q(_MAIN_NS, "formula1"))
            formula.text = f'"{",".join(values)}"'
    ET.SubElement(
        root,
        _q(_MAIN_NS, "pageMargins"),
        {"left": "0.7", "right": "0.7", "top": "0.75", "bottom": "0.75", "header": "0.3", "footer": "0.3"},
    )
    return _xml_bytes(root, default_namespace=_MAIN_NS)


def _append_cell(
    row: ET.Element,
    row_index: int,
    column_index: int,
    value: object,
    *,
    style: int,
) -> None:
    reference = f"{_column_name(column_index)}{row_index}"
    attributes = {"r": reference, "s": str(style)}
    if isinstance(value, bool):
        attributes["t"] = "b"
        cell = ET.SubElement(row, _q(_MAIN_NS, "c"), attributes)
        ET.SubElement(cell, _q(_MAIN_NS, "v")).text = "1" if value else "0"
        return
    if isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value)):
        cell = ET.SubElement(row, _q(_MAIN_NS, "c"), attributes)
        ET.SubElement(cell, _q(_MAIN_NS, "v")).text = str(value)
        return
    attributes["t"] = "inlineStr"
    cell = ET.SubElement(row, _q(_MAIN_NS, "c"), attributes)
    inline = ET.SubElement(cell, _q(_MAIN_NS, "is"))
    text = ET.SubElement(inline, _q(_MAIN_NS, "t"))
    rendered = str(value)
    if rendered != rendered.strip():
        text.set(_q(_XML_NS, "space"), "preserve")
    text.text = rendered


def _column_width(header: str, rows: list[dict[str, object]]) -> float:
    lengths = [len(header)]
    for row in rows[:200]:
        value = row.get(header)
        if value is not None:
            lengths.append(len(str(value)))
    longest = max(lengths, default=10)
    if header in {"description", "instruction"}:
        return min(60.0, max(28.0, longest * 0.9))
    return min(34.0, max(10.0, longest * 1.05 + 2))


def _column_name(index: int) -> str:
    if index < 1:
        raise ValueError("L'index de colonne doit être positif.")
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _content_types_xml(sheet_count: int) -> bytes:
    root = ET.Element(_q(_CONTENT_NS, "Types"))
    ET.SubElement(root, _q(_CONTENT_NS, "Default"), {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    ET.SubElement(root, _q(_CONTENT_NS, "Default"), {"Extension": "xml", "ContentType": "application/xml"})
    overrides = [
        ("/xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
        ("/xl/styles.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"),
        ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        ("/docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml"),
    ]
    overrides.extend(
        (f"/xl/worksheets/sheet{index}.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
        for index in range(1, sheet_count + 1)
    )
    for part_name, content_type in overrides:
        ET.SubElement(root, _q(_CONTENT_NS, "Override"), {"PartName": part_name, "ContentType": content_type})
    return _xml_bytes(root, default_namespace=_CONTENT_NS)


def _root_relationships_xml() -> bytes:
    root = ET.Element(_q(_PKG_REL_NS, "Relationships"))
    relationships = (
        ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", "xl/workbook.xml"),
        ("rId2", "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties", "docProps/core.xml"),
        ("rId3", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties", "docProps/app.xml"),
    )
    for rel_id, rel_type, target in relationships:
        ET.SubElement(root, _q(_PKG_REL_NS, "Relationship"), {"Id": rel_id, "Type": rel_type, "Target": target})
    return _xml_bytes(root, default_namespace=_PKG_REL_NS)


def _workbook_xml(sheet_names: list[str]) -> bytes:
    root = ET.Element(_q(_MAIN_NS, "workbook"))
    views = ET.SubElement(root, _q(_MAIN_NS, "bookViews"))
    ET.SubElement(views, _q(_MAIN_NS, "workbookView"), {"activeTab": "1"})
    sheets = ET.SubElement(root, _q(_MAIN_NS, "sheets"))
    for index, name in enumerate(sheet_names, start=1):
        ET.SubElement(
            sheets,
            _q(_MAIN_NS, "sheet"),
            {"name": name, "sheetId": str(index), _q(_REL_NS, "id"): f"rId{index}"},
        )
    ET.SubElement(root, _q(_MAIN_NS, "calcPr"), {"calcId": "191029", "fullCalcOnLoad": "1"})
    return _xml_bytes(root, default_namespace=_MAIN_NS)


def _workbook_relationships_xml(sheet_count: int) -> bytes:
    root = ET.Element(_q(_PKG_REL_NS, "Relationships"))
    for index in range(1, sheet_count + 1):
        ET.SubElement(
            root,
            _q(_PKG_REL_NS, "Relationship"),
            {
                "Id": f"rId{index}",
                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
                "Target": f"worksheets/sheet{index}.xml",
            },
        )
    ET.SubElement(
        root,
        _q(_PKG_REL_NS, "Relationship"),
        {
            "Id": f"rId{sheet_count + 1}",
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
            "Target": "styles.xml",
        },
    )
    return _xml_bytes(root, default_namespace=_PKG_REL_NS)


def _styles_xml() -> bytes:
    root = ET.Element(_q(_MAIN_NS, "styleSheet"))
    fonts = ET.SubElement(root, _q(_MAIN_NS, "fonts"), {"count": "2"})
    body_font = ET.SubElement(fonts, _q(_MAIN_NS, "font"))
    ET.SubElement(body_font, _q(_MAIN_NS, "sz"), {"val": "10"})
    ET.SubElement(body_font, _q(_MAIN_NS, "name"), {"val": "Arial"})
    header_font = ET.SubElement(fonts, _q(_MAIN_NS, "font"))
    ET.SubElement(header_font, _q(_MAIN_NS, "b"))
    ET.SubElement(header_font, _q(_MAIN_NS, "color"), {"rgb": "FFFFFFFF"})
    ET.SubElement(header_font, _q(_MAIN_NS, "sz"), {"val": "10"})
    ET.SubElement(header_font, _q(_MAIN_NS, "name"), {"val": "Arial"})

    fills = ET.SubElement(root, _q(_MAIN_NS, "fills"), {"count": "3"})
    for pattern in ("none", "gray125"):
        fill = ET.SubElement(fills, _q(_MAIN_NS, "fill"))
        ET.SubElement(fill, _q(_MAIN_NS, "patternFill"), {"patternType": pattern})
    header_fill = ET.SubElement(fills, _q(_MAIN_NS, "fill"))
    pattern = ET.SubElement(header_fill, _q(_MAIN_NS, "patternFill"), {"patternType": "solid"})
    ET.SubElement(pattern, _q(_MAIN_NS, "fgColor"), {"rgb": "FF17365D"})
    ET.SubElement(pattern, _q(_MAIN_NS, "bgColor"), {"indexed": "64"})

    borders = ET.SubElement(root, _q(_MAIN_NS, "borders"), {"count": "1"})
    border = ET.SubElement(borders, _q(_MAIN_NS, "border"))
    for side in ("left", "right", "top", "bottom", "diagonal"):
        ET.SubElement(border, _q(_MAIN_NS, side))

    style_xfs = ET.SubElement(root, _q(_MAIN_NS, "cellStyleXfs"), {"count": "1"})
    ET.SubElement(style_xfs, _q(_MAIN_NS, "xf"), {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0"})
    cell_xfs = ET.SubElement(root, _q(_MAIN_NS, "cellXfs"), {"count": "3"})
    ET.SubElement(cell_xfs, _q(_MAIN_NS, "xf"), {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0", "xfId": "0"})
    header_xf = ET.SubElement(
        cell_xfs,
        _q(_MAIN_NS, "xf"),
        {"numFmtId": "0", "fontId": "1", "fillId": "2", "borderId": "0", "xfId": "0", "applyAlignment": "1"},
    )
    ET.SubElement(header_xf, _q(_MAIN_NS, "alignment"), {"horizontal": "center", "vertical": "center", "wrapText": "1"})
    body_xf = ET.SubElement(
        cell_xfs,
        _q(_MAIN_NS, "xf"),
        {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0", "xfId": "0", "applyAlignment": "1"},
    )
    ET.SubElement(body_xf, _q(_MAIN_NS, "alignment"), {"vertical": "top", "wrapText": "1"})
    cell_styles = ET.SubElement(root, _q(_MAIN_NS, "cellStyles"), {"count": "1"})
    ET.SubElement(cell_styles, _q(_MAIN_NS, "cellStyle"), {"name": "Normal", "xfId": "0", "builtinId": "0"})
    return _xml_bytes(root, default_namespace=_MAIN_NS)


def _core_properties_xml(title: str = "Import NEXUS v2 pour Flow Atlas") -> bytes:
    ET.register_namespace("cp", _CORE_NS)
    ET.register_namespace("dc", _DC_NS)
    ET.register_namespace("dcterms", _DCTERMS_NS)
    ET.register_namespace("xsi", _XSI_NS)
    root = ET.Element(_q(_CORE_NS, "coreProperties"))
    ET.SubElement(root, _q(_DC_NS, "creator")).text = "Flow Scout"
    ET.SubElement(root, _q(_CORE_NS, "lastModifiedBy")).text = "Flow Scout"
    ET.SubElement(root, _q(_DC_NS, "title")).text = title
    created = ET.SubElement(root, _q(_DCTERMS_NS, "created"), {_q(_XSI_NS, "type"): "dcterms:W3CDTF"})
    created.text = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return _xml_bytes(root)


def _app_properties_xml(sheet_names: list[str]) -> bytes:
    ET.register_namespace("vt", _VT_NS)
    root = ET.Element(_q(_APP_NS, "Properties"))
    ET.SubElement(root, _q(_APP_NS, "Application")).text = "Flow Scout"
    ET.SubElement(root, _q(_APP_NS, "AppVersion")).text = "1.0"
    titles = ET.SubElement(root, _q(_APP_NS, "TitlesOfParts"))
    vector = ET.SubElement(titles, _q(_VT_NS, "vector"), {"size": str(len(sheet_names)), "baseType": "lpstr"})
    for name in sheet_names:
        ET.SubElement(vector, _q(_VT_NS, "lpstr")).text = name
    return _xml_bytes(root, default_namespace=_APP_NS)


def _write(archive: ZipFile, name: str, content: bytes) -> None:
    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, content)


def _xml_bytes(root: ET.Element, *, default_namespace: str | None = None) -> bytes:
    if default_namespace:
        ET.register_namespace("", default_namespace)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _q(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def assert_nexus_v2_headers(payload: dict[str, object]) -> None:
    """Vérifie que le payload conserve exactement le contrat de colonnes v2."""
    sheets = payload.get("sheets")
    if not isinstance(sheets, dict):
        raise ValueError("Le payload NEXUS ne contient pas de feuilles.")
    for sheet_name, expected in NEXUS_V2_HEADERS.items():
        sheet = sheets.get(sheet_name)
        if not isinstance(sheet, dict) or sheet.get("headers") != list(expected):
            raise ValueError(f"Contrat NEXUS v2 invalide pour la feuille {sheet_name}.")
