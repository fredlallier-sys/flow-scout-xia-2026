"""Commande locale Flow Scout pour contrôler un dépôt client avant extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.flow_scout.atlas import build_flow_atlas_import
from app.flow_scout.atlas_bridge import (
    inspect_atlas_v3_payload,
    rollback_atlas_workspace,
    stage_atlas_workspace,
)
from app.flow_scout.atlas_v3_lifecycle import (
    answer_atlas_v3_question,
    summarize_atlas_v3,
    validate_atlas_v3_question,
)
from app.flow_scout.candidates import extract_candidates
from app.flow_scout.codex_gateway import review_with_codex, review_with_codex_local
from app.flow_scout.enterprise_maps import build_enterprise_maps
from app.flow_scout.ingestion import ingest_directory
from app.flow_scout.interview import interpret_interview
from app.flow_scout.mapping import build_column_mapping_report
from app.flow_scout.nexus import build_nexus_v2_payload
from app.flow_scout.nexus_xlsx import (
    build_nexus_v2_xlsx,
    build_nexus_v3_xlsx,
    export_nexus_v3_xlsx,
)
from app.flow_scout.operator import run_agent_once, watch_client_deposit
from app.flow_scout.pipelex_bridge import write_pipelex_inputs
from app.flow_scout.source_catalog import load_collection_catalog
from app.flow_scout.voice_orchestrator import interpret_voice_command
from app.flow_scout.winner_demo import run_winner_demo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flow-scout")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Lire les CSV/XLSX d'un répertoire et produire un manifeste sourcé.",
    )
    inspect_parser.add_argument("source", type=Path)
    inspect_parser.add_argument("--output", "-o", type=Path)
    inspect_parser.add_argument(
        "--prefer-csv",
        action="store_true",
        help="Choisir le CSV quand un CSV et un XLSX portent le même nom.",
    )
    extract_parser = subparsers.add_parser(
        "extract",
        help="Produire les objets candidats sourcés et les questions de comblement.",
    )
    extract_parser.add_argument("source", type=Path)
    extract_parser.add_argument("--output", "-o", type=Path)
    extract_parser.add_argument("--prefer-csv", action="store_true")
    complete_parser = subparsers.add_parser(
        "complete",
        help="Assembler les sources et les réponses en import Flow Atlas.",
    )
    complete_parser.add_argument("source", type=Path)
    complete_parser.add_argument("--interview", type=Path, required=True)
    complete_parser.add_argument("--output", "-o", type=Path, required=True)
    complete_parser.add_argument("--org-name", default="Organisation analysée")
    complete_parser.add_argument("--sector", default="À confirmer")
    complete_parser.add_argument("--prefer-csv", action="store_true")
    nexus_parser = subparsers.add_parser(
        "nexus-v2",
        help="Projeter les sources et réponses vers le contrat tabulaire NEXUS v2.",
    )
    nexus_parser.add_argument("source", type=Path)
    nexus_parser.add_argument("--interview", type=Path, required=True)
    nexus_parser.add_argument("--output", "-o", type=Path, required=True)
    nexus_parser.add_argument("--org-name", default="Organisation analysée")
    nexus_parser.add_argument("--sector", default="À confirmer")
    nexus_parser.add_argument("--prefer-csv", action="store_true")
    nexus_xlsx_parser = subparsers.add_parser(
        "nexus-xlsx",
        help="Créer le classeur Excel NEXUS v2 prêt pour l'import Atlas.",
    )
    nexus_xlsx_parser.add_argument("source", type=Path)
    nexus_xlsx_parser.add_argument("--interview", type=Path, required=True)
    nexus_xlsx_parser.add_argument("--output", "-o", type=Path, required=True)
    nexus_xlsx_parser.add_argument("--org-name", default="Organisation analysée")
    nexus_xlsx_parser.add_argument("--sector", default="À confirmer")
    nexus_xlsx_parser.add_argument("--prefer-csv", action="store_true")
    catalog_parser = subparsers.add_parser(
        "catalog",
        help="Lire un référentiel de collecte sans le traiter comme une preuve client.",
    )
    catalog_parser.add_argument("source", type=Path)
    catalog_parser.add_argument("--output", "-o", type=Path)
    catalog_parser.add_argument("--focus-family")
    catalog_parser.add_argument(
        "--priority",
        action="append",
        dest="priorities",
        help="Priorité à inclure dans le plan, répétable (P0 par défaut).",
    )
    maps_parser = subparsers.add_parser(
        "enterprise-maps",
        help="Construire les sept cartes liées depuis le jeu assureur de démonstration.",
    )
    maps_parser.add_argument("source", type=Path)
    maps_parser.add_argument("--output", "-o", type=Path)
    atlas_v3_parser = subparsers.add_parser(
        "atlas-v3",
        help="Créer le classeur Atlas v3 avec règles, contrôles et maïeutique.",
    )
    atlas_v3_parser.add_argument("source", type=Path)
    atlas_v3_parser.add_argument("--output", "-o", type=Path, required=True)
    agent_once_parser = subparsers.add_parser(
        "agent-once",
        help="Traiter une version du dépôt client et alimenter Atlas en staging.",
    )
    agent_once_parser.add_argument("source", type=Path)
    agent_once_parser.add_argument("--output", "-o", type=Path, required=True)
    agent_watch_parser = subparsers.add_parser(
        "agent-watch",
        help="Surveiller un dépôt client et relancer l'agent lors d'un changement.",
    )
    agent_watch_parser.add_argument("source", type=Path)
    agent_watch_parser.add_argument("--output", "-o", type=Path, required=True)
    agent_watch_parser.add_argument("--poll-seconds", type=float, default=2.0)
    agent_watch_parser.add_argument("--max-cycles", type=int)
    answer_parser = subparsers.add_parser(
        "atlas-answer",
        help="Enregistrer une réponse maïeutique dans un payload Atlas v3.",
    )
    answer_parser.add_argument("source", type=Path)
    answer_parser.add_argument("--question", required=True)
    answer_parser.add_argument("--answer-file", type=Path, required=True)
    answer_parser.add_argument("--answered-by", required=True)
    answer_parser.add_argument("--evidence-note", default="")
    answer_parser.add_argument("--output", "-o", type=Path, required=True)
    validate_parser = subparsers.add_parser(
        "atlas-validate",
        help="Valider humainement une réponse et recalculer le contrôle.",
    )
    validate_parser.add_argument("source", type=Path)
    validate_parser.add_argument("--question", required=True)
    validate_parser.add_argument("--validator", required=True)
    validate_parser.add_argument("--reject", action="store_true")
    validate_parser.add_argument("--resolution-confirmed", action="store_true")
    validate_parser.add_argument("--validation-note", default="")
    validate_parser.add_argument("--output", "-o", type=Path, required=True)
    atlas_payload_xlsx_parser = subparsers.add_parser(
        "atlas-v3-xlsx",
        help="Exporter un payload Atlas v3 enrichi ou validé en classeur XLSX.",
    )
    atlas_payload_xlsx_parser.add_argument("source", type=Path)
    atlas_payload_xlsx_parser.add_argument("--output", "-o", type=Path, required=True)
    winner_parser = subparsers.add_parser(
        "winner-demo",
        help="Rejouer le scénario jury complet, l'évaluer et alimenter Atlas.",
    )
    winner_parser.add_argument("source", type=Path)
    winner_parser.add_argument("--output", "-o", type=Path, required=True)
    winner_parser.add_argument("--replay-count", type=int, default=5)
    pipelex_inputs_parser = subparsers.add_parser(
        "pipelex-inputs",
        help="Preparer un paquet minimise pour la relecture Pipelex, sans appel externe.",
    )
    pipelex_inputs_parser.add_argument("source", type=Path)
    pipelex_inputs_parser.add_argument("--output", "-o", type=Path, required=True)
    codex_parser = subparsers.add_parser(
        "codex-review",
        help="Relire un paquet source avec le Codex harness, sous confirmation explicite.",
    )
    codex_parser.add_argument("source", type=Path)
    codex_parser.add_argument("--output", "-o", type=Path, required=True)
    codex_parser.add_argument("--model")
    codex_parser.add_argument(
        "--confirm-existing-credits",
        action="store_true",
        help="Confirmer l'utilisation des credits OpenAI API deja disponibles.",
    )
    codex_local_parser = subparsers.add_parser(
        "codex-local-review",
        help="Relire un paquet avec le Codex local connecte au compte ChatGPT/Codex.",
    )
    codex_local_parser.add_argument("source", type=Path)
    codex_local_parser.add_argument("--output", "-o", type=Path, required=True)
    codex_local_parser.add_argument("--project-root", type=Path, required=True)
    codex_local_parser.add_argument("--model")
    codex_local_parser.add_argument(
        "--confirm-subscription-usage",
        action="store_true",
        help="Confirmer l'utilisation du quota du compte Codex local deja connecte.",
    )
    voice_parser = subparsers.add_parser(
        "voice-command",
        help="Interpréter une transcription vocale sans appel externe.",
    )
    voice_parser.add_argument("transcript")
    voice_parser.add_argument(
        "--pending-action",
        type=Path,
        help="Action JSON déjà relue à confirmer ; aucune action implicite n'est acceptée.",
    )
    bridge_inspect_parser = subparsers.add_parser(
        "atlas-bridge-inspect",
        help="Contrôler un payload Atlas v3 avant son chargement.",
    )
    bridge_inspect_parser.add_argument("source", type=Path)
    bridge_stage_parser = subparsers.add_parser(
        "atlas-bridge-stage",
        help="Charger un payload v3 dans un espace Atlas local versionné.",
    )
    bridge_stage_parser.add_argument("source", type=Path)
    bridge_stage_parser.add_argument("--output", "-o", type=Path, required=True)
    bridge_stage_parser.add_argument("--imported-by", required=True)
    bridge_rollback_parser = subparsers.add_parser(
        "atlas-bridge-rollback",
        help="Réactiver un instantané Atlas antérieur sans effacer l'historique.",
    )
    bridge_rollback_parser.add_argument("workspace", type=Path)
    bridge_rollback_parser.add_argument("--import-id", required=True)
    bridge_rollback_parser.add_argument("--actor", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "voice-command":
        pending_action = None
        if args.pending_action:
            pending_action = json.loads(args.pending_action.read_text(encoding="utf-8"))
            if not isinstance(pending_action, dict):
                raise ValueError("L'action en attente doit être un objet JSON.")
        print(
            json.dumps(
                interpret_voice_command(
                    args.transcript,
                    pending_action=pending_action,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "codex-review":
        from app.flow_scout.operator import build_agent_preview

        receipt = review_with_codex(
            build_agent_preview(args.source),
            confirmed_existing_credits=args.confirm_existing_credits,
            model=args.model,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "completed": receipt["completed"],
                    "provider": receipt["provider"],
                    "runtime": receipt["runtime"],
                    "model": receipt["model"],
                    "session_id": receipt["session_id"],
                    "usage": receipt["usage"],
                    "output": str(args.output.resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "codex-local-review":
        from app.flow_scout.operator import build_agent_preview

        receipt = review_with_codex_local(
            build_agent_preview(args.source),
            confirmed_subscription_usage=args.confirm_subscription_usage,
            project_root=args.project_root,
            model=args.model,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "completed": receipt["completed"],
                    "provider": receipt["provider"],
                    "runtime": receipt["runtime"],
                    "model": receipt["model"],
                    "session_id": receipt["session_id"],
                    "usage": receipt["usage"],
                    "output": str(args.output.resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "pipelex-inputs":
        from app.flow_scout.operator import build_agent_preview

        preview = build_agent_preview(args.source)
        destination = write_pipelex_inputs(preview, args.output)
        print(f"Entrée Pipelex préparée sans appel externe : {destination}")
        return 0
    if args.command == "winner-demo":
        result = run_winner_demo(
            args.source,
            output_directory=args.output,
            replay_count=args.replay_count,
        )
        print(
            json.dumps(
                {
                    "run_id": result["run_id"],
                    "evaluation": result["evaluation"],
                    "artifacts": result["artifacts"],
                    "atlas_status": result["atlas_workspace"]["workspace_status"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "atlas-bridge-inspect":
        payload = json.loads(args.source.read_text(encoding="utf-8"))
        print(json.dumps(inspect_atlas_v3_payload(payload), ensure_ascii=False, indent=2))
        return 0
    if args.command == "atlas-bridge-stage":
        payload = json.loads(args.source.read_text(encoding="utf-8"))
        result = stage_atlas_workspace(
            payload, args.output, imported_by=args.imported_by
        )
        print(json.dumps(result["paths"], ensure_ascii=False, indent=2))
        return 0
    if args.command == "atlas-bridge-rollback":
        workspace = rollback_atlas_workspace(
            args.workspace,
            import_id=args.import_id,
            rolled_back_by=args.actor,
        )
        print(json.dumps(workspace["import"], ensure_ascii=False, indent=2))
        return 0
    if args.command == "agent-once":
        result = run_agent_once(args.source, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "agent-watch":
        results = watch_client_deposit(
            args.source,
            args.output,
            poll_seconds=args.poll_seconds,
            max_cycles=args.max_cycles,
        )
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    if args.command == "atlas-answer":
        payload = json.loads(args.source.read_text(encoding="utf-8"))
        answer_text = args.answer_file.read_text(encoding="utf-8").strip()
        try:
            answer = json.loads(answer_text)
        except json.JSONDecodeError:
            answer = answer_text
        updated = answer_atlas_v3_question(
            payload,
            question_id=args.question,
            answer=answer,
            answered_by=args.answered_by,
            evidence_note=args.evidence_note,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summarize_atlas_v3(updated), ensure_ascii=False, indent=2))
        return 0
    if args.command == "atlas-validate":
        payload = json.loads(args.source.read_text(encoding="utf-8"))
        updated = validate_atlas_v3_question(
            payload,
            question_id=args.question,
            validator=args.validator,
            accepted=not args.reject,
            resolution_confirmed=args.resolution_confirmed,
            validation_note=args.validation_note,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summarize_atlas_v3(updated), ensure_ascii=False, indent=2))
        return 0
    if args.command == "atlas-v3-xlsx":
        payload = json.loads(args.source.read_text(encoding="utf-8"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(export_nexus_v3_xlsx(payload))
        print(f"Classeur Atlas v3 écrit : {args.output}")
        return 0
    if args.command == "atlas-v3":
        report = build_enterprise_maps(args.source)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(build_nexus_v3_xlsx(report))
        print(f"Classeur Atlas v3 écrit : {args.output}")
        return 0
    if args.command == "enterprise-maps":
        report = build_enterprise_maps(args.source)
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(f"Cartographie écrite : {args.output}")
        else:
            print(rendered)
        return 0
    if args.command == "catalog":
        report = load_collection_catalog(
            args.source,
            focus_family=args.focus_family,
            priorities=tuple(args.priorities or ["P0"]),
        )
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(f"Plan de collecte écrit : {args.output}")
        else:
            print(rendered)
        return 0
    if args.command in {"inspect", "extract", "complete", "nexus-v2", "nexus-xlsx"}:
        batch = ingest_directory(args.source, prefer_xlsx=not args.prefer_csv)
        if args.command == "inspect":
            report = batch.to_dict()
            report["column_mapping"] = build_column_mapping_report(batch)
        elif args.command == "extract":
            report = extract_candidates(batch)
        else:
            interview_payload = json.loads(args.interview.read_text(encoding="utf-8"))
            candidates = extract_candidates(batch)
            interview = interpret_interview(interview_payload)
            graph = build_flow_atlas_import(
                candidates,
                interview,
                organization_name=args.org_name,
                sector=args.sector,
            )
            if args.command == "nexus-xlsx":
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(build_nexus_v2_xlsx(graph))
                print(f"Classeur NEXUS écrit : {args.output}")
                return 0
            report = build_nexus_v2_payload(graph) if args.command == "nexus-v2" else graph
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(f"Manifeste écrit : {args.output}")
        else:
            print(rendered)
        return 0
    return 2
