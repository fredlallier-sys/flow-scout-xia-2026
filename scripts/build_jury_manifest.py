#!/usr/bin/env python3
"""Write a checksum manifest for the current local Jury Mode run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    score_path = args.run / "evaluation-scorecard.json"
    score = json.loads(score_path.read_text(encoding="utf-8"))
    dashboard_path = (
        args.project
        / "outputs"
        / "portfolio-decision-demo"
        / "alignment-dashboard.json"
    )
    dashboard_html_path = dashboard_path.with_suffix(".html")
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    if dashboard.get("human_approval_required") is not True:
        raise SystemExit("Le dashboard doit imposer une approbation humaine.")
    if dashboard.get("automatic_finalization") is not False:
        raise SystemExit("Le dashboard ne doit jamais finaliser automatiquement.")
    targets = {
        "Lancer_Flow_Scout_Jury.command": args.project
        / "Lancer_Flow_Scout_Jury.command",
        "scripts/build_jury_mode.py": args.project / "scripts/build_jury_mode.py",
        "scripts/serve_jury_mode.py": args.project / "scripts/serve_jury_mode.py",
        "outputs/jury-mode/latest/index.html": args.run / "index.html",
        "outputs/jury-mode/latest/replay-events-agentic.ndjson": args.run
        / "replay-events-agentic.ndjson",
        "outputs/jury-mode/latest/evaluation-scorecard.json": score_path,
        "outputs/jury-mode/latest/flow-atlas-v3-validated.xlsx": args.run
        / "flow-atlas-v3-validated.xlsx",
        "config/flow-scout-portfolio-decision-policy.v1.json": args.project
        / "config"
        / "flow-scout-portfolio-decision-policy.v1.json",
        "outputs/portfolio-decision-demo/alignment-dashboard.json": dashboard_path,
        "outputs/portfolio-decision-demo/alignment-dashboard.html": dashboard_html_path,
    }
    manifest = {
        "package": "Flow Scout Jury Mode v1",
        "run_id": json.loads(
            (args.run / "winner-demo-result.json").read_text(encoding="utf-8")
        )["run_id"],
        "launch": "Lancer_Flow_Scout_Jury.command",
        "mode": "local-offline-zero-spend",
        "acceptance": {
            "guided_steps": 12,
            "jury_questions": 20,
            "rehearsal_timer": True,
            "random_qa_trainer": True,
            "agentic_ndjson_replay": True,
            "full_local_run_button": True,
            "portfolio_decision_engine": True,
            "alignment_dashboard": True,
            "alignment_score": dashboard.get("portfolio_alignment_score"),
            "alignment_status": dashboard.get("overall_status"),
            "human_approval_required": True,
            "replays_passed": score["replay_count"] if score["passed"] else 0,
            "replays_total": score["replay_count"],
            "checks_passed": score["passed_checks"],
            "checks_total": score["check_count"],
            "external_service_calls": score["external_service_calls"],
            "internet_resources": 0,
            "automatic_finalization": False,
        },
        "sha256": {name: digest(path) for name, path in targets.items()},
    }
    output = args.run / "JURY-MODE-MANIFEST.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(output)
    print(f"Manifeste vérifiable : {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
