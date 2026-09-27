"""Rendu HTML local du dashboard d'alignement Flow Scout."""

from __future__ import annotations

import html
import json
from typing import Any


def render_alignment_dashboard(dashboard: dict[str, Any]) -> str:
    """Produit une page autonome sans ressource ou appel externe."""
    dimensions = _dict_list(dashboard.get("dimensions"))
    actions = _dict_list(dashboard.get("priority_actions"))
    decisions = _dict_list(
        _dict(dashboard.get("portfolio_decisions")).get("review_queue")
    )
    counts = _dict(
        _dict(dashboard.get("portfolio_decisions")).get("recommendation_counts")
    )
    score = dashboard.get("portfolio_alignment_score")
    score_text = "—" if score is None else f"{float(score):.1f}"
    overall = str(dashboard.get("overall_status", "UNKNOWN"))

    dimension_rows = "".join(_dimension_row(item) for item in dimensions)
    action_rows = "".join(_action_row(item) for item in actions) or (
        '<tr><td colspan="5">Aucun écart prioritaire. Maintenir la mesure.</td></tr>'
    )
    decision_rows = "".join(_decision_row(item) for item in decisions) or (
        '<tr><td colspan="6">Aucun usage dans le portefeuille.</td></tr>'
    )
    count_cards = "".join(
        f'<div class="mini"><strong>{_escape(option)}</strong><span>{int(value)}</span></div>'
        for option, value in counts.items()
    )
    payload = (
        json.dumps(dashboard, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )

    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Flow Scout — Dashboard d'alignement</title>
  <style>
    :root {{ color-scheme: dark; --ink:#f5f7fb; --muted:#a9b2c3; --line:#2b3547;
      --panel:#151b25; --green:#4fd1a5; --amber:#f6c85f; --red:#ff6b78; --blue:#7aa2ff; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#0b0f16; color:var(--ink); font:15px/1.45 Inter,system-ui,sans-serif; }}
    main {{ max-width:1320px; margin:auto; padding:32px; }}
    header {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-end; margin-bottom:24px; }}
    h1 {{ margin:0; font-size:clamp(28px,4vw,48px); letter-spacing:-.04em; }}
    h2 {{ margin:32px 0 12px; font-size:20px; }}
    p {{ color:var(--muted); margin:.4rem 0 0; }}
    .badge {{ display:inline-flex; align-items:center; padding:7px 12px; border-radius:999px;
      font-weight:800; background:color-mix(in srgb, currentColor 15%, transparent); }}
    .GREEN {{ color:var(--green); }} .AMBER {{ color:var(--amber); }}
    .RED {{ color:var(--red); }} .UNKNOWN {{ color:var(--muted); }}
    .summary {{ display:grid; grid-template-columns:1.2fr 2fr; gap:16px; }}
    .panel {{ background:linear-gradient(145deg,#192130,#121720); border:1px solid var(--line);
      border-radius:18px; padding:20px; box-shadow:0 18px 50px #0005; }}
    .score {{ font-size:72px; font-weight:850; line-height:1; letter-spacing:-.06em; }}
    .counts {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:18px; }}
    .mini {{ min-width:112px; padding:12px; border:1px solid var(--line); border-radius:12px; }}
    .mini strong,.mini span {{ display:block; }} .mini span {{ font-size:24px; margin-top:4px; }}
    .guard {{ border-left:4px solid var(--amber); padding-left:16px; }}
    table {{ width:100%; border-collapse:separate; border-spacing:0; overflow:hidden;
      border:1px solid var(--line); border-radius:14px; background:var(--panel); }}
    th,td {{ padding:13px 14px; text-align:left; vertical-align:top; border-bottom:1px solid var(--line); }}
    th {{ color:#c9d2e3; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    tr:last-child td {{ border-bottom:0; }}
    .metric {{ min-width:150px; }}
    .bar {{ height:8px; border-radius:9px; background:#293244; overflow:hidden; margin-top:8px; }}
    .bar span {{ display:block; height:100%; border-radius:9px; background:var(--blue); }}
    .small {{ color:var(--muted); font-size:13px; }}
    .option {{ font-weight:800; }}
    footer {{ margin-top:28px; color:var(--muted); font-size:12px; }}
    @media(max-width:850px) {{ main{{padding:18px}} header{{display:block}} .summary{{grid-template-columns:1fr}}
      table{{display:block;overflow:auto}} }}
  </style>
</head>
<body>
<main>
  <header>
    <div><p>THE FLOW FABRIC · FLOW SCOUT</p><h1>Dashboard d'alignement</h1>
      <p>{int(dashboard.get('item_count', 0))} usages analysés · cible {_escape(dashboard.get('target_score'))}/100</p></div>
    <span class="badge {_escape(overall)}">{_escape(overall)}</span>
  </header>

  <section class="summary">
    <div class="panel"><div class="score {_escape(overall)}">{_escape(score_text)}</div>
      <p>Score pondéré du portefeuille</p><div class="counts">{count_cards}</div></div>
    <div class="panel guard"><strong>Supervision humaine obligatoire</strong>
      <p>L'agent calcule, sélectionne l'option, prépare l'action et la place dans Atlas.
      Aucune publication, dépense, modification de délégation ou action irréversible
      n'est exécutée automatiquement.</p><p><strong>État :</strong> {_escape(dashboard.get('publication_status'))}</p></div>
  </section>

  <h2>Huit dimensions d'alignement</h2>
  <table><thead><tr><th>Dimension</th><th>Score</th><th>État</th><th>Écart</th><th>Usages à traiter</th><th>Action proposée</th></tr></thead>
    <tbody>{dimension_rows}</tbody></table>

  <h2>Actions prioritaires proposées</h2>
  <table><thead><tr><th>#</th><th>Dimension</th><th>État</th><th>Action</th><th>Validation</th></tr></thead>
    <tbody>{action_rows}</tbody></table>

  <h2>File d'arbitrage du portefeuille</h2>
  <table><thead><tr><th>Usage</th><th>Score</th><th>Option proposée</th><th>Justification</th><th>Preuves</th><th>État</th></tr></thead>
    <tbody>{decision_rows}</tbody></table>

  <footer>Politique {_escape(dashboard.get('policy_id'))} · empreinte {_escape(str(dashboard.get('policy_sha256',''))[:12])}… · page locale sans ressource externe.</footer>
</main>
<script type="application/json" id="flow-scout-dashboard-data">{payload}</script>
</body>
</html>
"""


def _dimension_row(item: dict[str, Any]) -> str:
    score = item.get("score")
    score_text = "—" if score is None else f"{float(score):.1f}"
    width = 0 if score is None else max(0, min(100, float(score)))
    affected = ", ".join(str(value) for value in item.get("items_below_target", [])) or "—"
    return (
        "<tr>"
        f'<td><strong>{_escape(item.get("label"))}</strong><div class="small">{_escape(item.get("question"))}</div></td>'
        f'<td class="metric"><strong>{_escape(score_text)}</strong><div class="bar"><span style="width:{width:.1f}%"></span></div></td>'
        f'<td><span class="badge {_escape(item.get("status"))}">{_escape(item.get("status"))}</span></td>'
        f'<td>{_escape(item.get("gap_to_target"))}</td>'
        f'<td>{_escape(affected)}</td>'
        f'<td>{_escape(item.get("recommended_action"))}</td>'
        "</tr>"
    )


def _action_row(item: dict[str, Any]) -> str:
    reviewers = ", ".join(str(value) for value in item.get("reviewers", []))
    return (
        "<tr>"
        f'<td>{_escape(item.get("priority"))}</td>'
        f'<td><strong>{_escape(item.get("dimension"))}</strong></td>'
        f'<td><span class="badge {_escape(item.get("status"))}">{_escape(item.get("status"))}</span></td>'
        f'<td>{_escape(item.get("action"))}<div class="small">{_escape(", ".join(item.get("affected_items", [])))}</div></td>'
        f'<td>{_escape(reviewers)}</td>'
        "</tr>"
    )


def _decision_row(item: dict[str, Any]) -> str:
    score = item.get("portfolio_score")
    evidence = ", ".join(str(value) for value in item.get("evidence_refs", []))
    agent_action = _dict(item.get("agent_action"))
    return (
        "<tr>"
        f'<td><strong>{_escape(item.get("item_id"))}</strong></td>'
        f'<td>{_escape("—" if score is None else score)}</td>'
        f'<td class="option">{_escape(item.get("recommended_option"))}<div class="small">{_escape(item.get("recommended_label"))}</div></td>'
        f'<td>{_escape(item.get("rationale"))}</td>'
        f'<td class="small">{_escape(evidence)}</td>'
        f'<td>{_escape(agent_action.get("status"))}</td>'
        "</tr>"
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)
