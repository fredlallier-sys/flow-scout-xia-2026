"""Agent opérateur local entre un dépôt client et Flow Atlas.

Le moteur est déterministe, sans appel réseau ni service payant. Il alimente un espace
Atlas versionné en staging ; la finalisation reste toujours une action humaine.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from app.flow_scout.atlas_bridge import stage_atlas_workspace
from app.flow_scout.atlas_v3_lifecycle import summarize_atlas_v3
from app.flow_scout.enterprise_maps import EnterpriseMapError, build_enterprise_maps
from app.flow_scout.ingestion import IngestionError, ingest_file
from app.flow_scout.nexus_v3 import build_nexus_v3_payload
from app.flow_scout.nexus_xlsx import export_nexus_v3_xlsx

_SUPPORTED_SUFFIXES = {".csv", ".xlsx"}


class FlowScoutOperatorError(ValueError):
    """Le dépôt ne permet pas de produire un passage contrôlé vers Atlas."""


def scan_client_deposit(source: str | Path) -> dict[str, object]:
    """Inventorie, reconnaît et empreinte les fichiers déposés."""
    root = Path(source)
    if not root.is_dir():
        raise FlowScoutOperatorError(f"Répertoire de dépôt introuvable : {root}")
    files = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if (
            not path.is_file()
            or path.name.startswith(".")
            or path.name.startswith("~$")
        ):
            continue
        if path.suffix.casefold() not in _SUPPORTED_SUFFIXES:
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "supported": False,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "source_kinds": [],
                    "warnings": ["Format ignoré par Flow Scout."],
                }
            )
            continue
        try:
            tables = ingest_file(path)
        except IngestionError as exc:
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "supported": True,
                    "readable": False,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "source_kinds": [],
                    "warnings": [str(exc)],
                }
            )
            continue
        files.append(
            {
                "name": path.name,
                "path": str(path),
                "supported": True,
                "readable": True,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "source_kinds": sorted({table.kind.value for table in tables}),
                "table_count": len(tables),
                "row_count": sum(len(table.rows) for table in tables),
                "warnings": sorted(
                    {
                        warning
                        for table in tables
                        for warning in table.warnings
                    }
                ),
            }
        )
    supported = [item for item in files if item.get("supported")]
    fingerprint = hashlib.sha256(
        "\n".join(
            f"{item['name']}:{item['sha256']}" for item in supported
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "flow-scout-deposit-scan-v1",
        "source_directory": str(root.resolve()),
        "file_count": len(files),
        "supported_file_count": len(supported),
        "readable_file_count": sum(item.get("readable") is True for item in files),
        "fingerprint": fingerprint,
        "files": files,
    }


def build_agent_preview(source_file: str | Path) -> dict[str, object]:
    """Exécute le cycle jusqu'à l'espace Atlas mis en attente."""
    source = Path(source_file)
    try:
        report = build_enterprise_maps(source)
    except (IngestionError, EnterpriseMapError) as exc:
        raise FlowScoutOperatorError(str(exc)) from exc
    payload = build_nexus_v3_payload(report)
    summary = summarize_atlas_v3(payload)
    stages = _stages(report, summary)
    return {
        "schema_version": "flow-scout-operator-preview-v1",
        "run_id": f"RUN-{_sha256(source)[:12].upper()}",
        "source": {
            "name": source.name,
            "sha256": _sha256(source),
            "size_bytes": source.stat().st_size,
            "role": report.get("dataset", {}).get("role", "")
            if isinstance(report.get("dataset"), dict)
            else "",
        },
        "stages": stages,
        "summary": summary,
        "report": report,
        "atlas_payload": payload,
    }


def run_agent_once(
    deposit_directory: str | Path, output_directory: str | Path
) -> dict[str, object]:
    """Traite une version du dépôt et écrit un paquet de démonstration auditable."""
    scan = scan_client_deposit(deposit_directory)
    candidates = []
    for item in scan["files"]:
        if (
            isinstance(item, dict)
            and item.get("supported")
            and item.get("readable")
            and str(item.get("name", "")).casefold().endswith(".xlsx")
        ):
            path = Path(str(item["path"]))
            try:
                preview = build_agent_preview(path)
            except FlowScoutOperatorError:
                continue
            candidates.append((path, preview))
    if not candidates:
        raise FlowScoutOperatorError(
            "Aucun classeur du dépôt ne contient le jeu de sources nécessaire aux sept cartes."
        )
    if len(candidates) > 1:
        names = ", ".join(path.name for path, _ in candidates)
        raise FlowScoutOperatorError(
            f"Plusieurs collectes complètes sont présentes ({names}). Isolez un client par dépôt."
        )
    source, preview = candidates[0]
    run_id = str(preview["run_id"])
    root = Path(output_directory)
    run_directory = root / "runs" / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    atlas_directory = root / "flow-atlas" / "workspace"

    payload = preview["atlas_payload"]
    summary = preview["summary"]
    payload_path = run_directory / "flow-atlas-import-v3.json"
    workbook_path = run_directory / "flow-atlas-import-v3.xlsx"
    report_path = run_directory / "flow-scout-agent-run.json"
    events_path = run_directory / "events.ndjson"

    payload_path.write_text(_json(payload) + "\n", encoding="utf-8")
    workbook_path.write_bytes(export_nexus_v3_xlsx(payload))
    atlas_import = stage_atlas_workspace(
        payload,
        atlas_directory,
        imported_by="Flow Scout Agent",
    )
    staged_path = Path(atlas_import["paths"]["active"])
    public_report = {
        key: value for key, value in preview.items() if key != "atlas_payload"
    }
    public_report["deposit_scan"] = scan
    public_report["artifacts"] = {
        "atlas_json": str(payload_path.resolve()),
        "atlas_xlsx": str(workbook_path.resolve()),
        "atlas_staged_import": str(staged_path.resolve()),
        "events": str(events_path.resolve()),
    }
    report_path.write_text(_json(public_report) + "\n", encoding="utf-8")
    events = [
        _event(run_id, "deposit_detected", source.name, "completed"),
        _event(run_id, "sources_recognized", source.name, "completed"),
        _event(run_id, "enterprise_maps_built", "7 maps", "completed"),
        _event(
            run_id,
            "maieutic_opened",
            f"{summary['open_blocking_question_count']} blocking questions",
            "waiting_human",
        ),
        _event(
            run_id,
            "atlas_workspace_loaded",
            str(staged_path.resolve()),
            str(summary["atlas_load_status"]),
        ),
    ]
    events_path.write_text(
        "".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True, default=str) + "\n"
            for event in events
        ),
        encoding="utf-8",
    )
    return public_report


def watch_client_deposit(
    deposit_directory: str | Path,
    output_directory: str | Path,
    *,
    poll_seconds: float = 2.0,
    max_cycles: int | None = None,
) -> list[dict[str, object]]:
    """Surveille par empreinte ; utile en continu et bornable dans les tests."""
    if poll_seconds < 0:
        raise FlowScoutOperatorError("L'intervalle de surveillance ne peut pas être négatif.")
    results: list[dict[str, object]] = []
    previous_fingerprint = ""
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        scan = scan_client_deposit(deposit_directory)
        fingerprint = str(scan["fingerprint"])
        if fingerprint and fingerprint != previous_fingerprint:
            results.append(run_agent_once(deposit_directory, output_directory))
            previous_fingerprint = fingerprint
        cycles += 1
        if max_cycles is None or cycles < max_cycles:
            time.sleep(poll_seconds)
    return results


def _stages(
    report: dict[str, object], summary: dict[str, object]
) -> list[dict[str, object]]:
    finding_count = int(report.get("finding_count", 0) or 0)
    return [
        {"id": "deposit", "label": "Dépôt client détecté", "status": "completed"},
        {"id": "recognition", "label": "Sources reconnues", "status": "completed"},
        {"id": "quality", "label": "Qualité et provenance contrôlées", "status": "completed"},
        {"id": "extraction", "label": "Objets métier extraits", "status": "completed"},
        {"id": "maps", "label": "Sept cartes construites", "status": "completed"},
        {"id": "findings", "label": f"{finding_count} constats détectés", "status": "completed"},
        {"id": "maieutic", "label": "Questions maïeutiques préparées", "status": "waiting_human"},
        {"id": "validation", "label": "Validation humaine", "status": "waiting_human"},
        {"id": "atlas_file", "label": "Fichier Atlas v3 produit", "status": "completed"},
        {
            "id": "atlas_load",
            "label": "Espace Atlas réellement alimenté en staging",
            "status": summary["atlas_load_status"],
        },
    ]


def _event(run_id: str, action: str, subject: str, status: str) -> dict[str, str]:
    return {
        "occurred_at": _now(),
        "run_id": run_id,
        "actor": "flow-scout-agent",
        "action": action,
        "subject": subject,
        "status": status,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    )


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
