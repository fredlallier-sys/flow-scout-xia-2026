#!/usr/bin/env python3
"""Exécute localement les règles portefeuille et le dashboard d'alignement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.flow_scout.portfolio_decision import (  # noqa: E402
    build_alignment_dashboard,
    evaluate_portfolio,
    load_decision_policy,
)
from app.flow_scout.alignment_dashboard import render_alignment_dashboard  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Évaluer un portefeuille IA sans service externe."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--policy", type=Path, default=None)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("Le fichier d'entrée doit contenir une liste 'items'.")

    policy = load_decision_policy(args.policy)
    review = evaluate_portfolio(items, policy=policy)
    dashboard = build_alignment_dashboard(items, policy=policy)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    review_path = args.output_dir / "portfolio-decision-review.json"
    dashboard_path = args.output_dir / "alignment-dashboard.json"
    dashboard_html_path = args.output_dir / "alignment-dashboard.html"
    review_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    dashboard_path.write_text(
        json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    dashboard_html_path.write_text(
        render_alignment_dashboard(dashboard), encoding="utf-8"
    )
    print(f"Arbitrage préparé : {review_path}")
    print(f"Dashboard d'alignement : {dashboard_path}")
    print(f"Dashboard visuel : {dashboard_html_path}")
    print(
        f"{review['item_count']} usages · validation humaine requise · "
        "aucune finalisation automatique"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
