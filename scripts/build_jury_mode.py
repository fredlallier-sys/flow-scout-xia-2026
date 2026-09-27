#!/usr/bin/env python3
"""Build the self-contained, offline Flow Scout Jury Mode page."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ORAL_BY_TITLE = {
    "Dépôt client": (
        "Je pars du travail réel, pas d'une liste déclarative d'outils. "
        "Le dossier assureur contient l'organisation, les activités, les décisions, "
        "les systèmes, les usages IA et les mesures disponibles."
    ),
    "Reconnaissance": (
        "Flow Scout reconnaît chaque source, conserve sa provenance et refuse de "
        "transformer une cellule vide en zéro. Rien n'est conclu sans preuve."
    ),
    "Cartographie": (
        "L'agent relie ces sources dans sept cartes : travail, décisions, connaissances, "
        "systèmes, usage réel de l'IA, valeur et possibilités de transformation."
    ),
    "Paiement sans validation humaine": (
        "Ici, Flow Scout montre un problème concret : l'IA a déclenché douze paiements "
        "tests sans validation humaine, alors que la règle de l'entreprise exige l'accord "
        "d'une personne avant chaque paiement. Chaque constat remonte à sa cellule source."
    ),
    "Maïeutique": (
        "Il ne corrige pas seul une décision de gouvernance. Il demande au responsable "
        "quel niveau d'autonomie est acceptable et quel contrôle humain sera appliqué."
    ),
    "Réponse ambiguë": (
        "Une réponse vague ne suffit pas. Dire que l'on regardera le sujet ne fournit "
        "ni décision, ni responsable, ni remédiation vérifiable."
    ),
    "Blocage maintenu": (
        "Le contrôle reste donc en échec et Atlas reste bloqué. C'est un comportement "
        "essentiel : Flow Scout préfère une information insuffisante à une fausse certitude."
    ),
    "Validation humaine": (
        "Le responsable confirme une règle compréhensible : l'IA peut préparer le paiement, "
        "mais une personne doit le vérifier et l'autoriser avant son envoi. Cette validation "
        "est conservée dans le journal."
    ),
    "Recalcul AI-002": (
        "Après validation explicite, l'agent recalcule le contrôle. AI-002 passe à PASS, "
        "sans effacer l'état initial ni la réponse ambiguë."
    ),
    "Compétences ACT-012": (
        "Flow Scout traite aussi l'alignement humain. Pour ACT-012, il qualifie l'écart de "
        "compétences et la formation nécessaire avant de valider le contrôle."
    ),
    "Valeur": (
        "Enfin, l'agent sépare strictement le temps libéré d'une économie budgétaire. "
        "Cent quatre-vingts heures gagnées ne deviennent pas automatiquement une réduction de coût."
    ),
    "Atlas Bridge": (
        "Le résultat alimente un Atlas v3 versionné. Le moteur de portefeuille choisit "
        "ensuite l'option à préparer et le dashboard montre les écarts d'alignement. "
        "Les arbitrages finaux restent soumis à une validation humaine explicite."
    ),
}


# Repères de présentation. Le moteur conserve sa chronologie d'origine, mais le
# Jury Mode réserve volontairement les vingt dernières secondes à Atlas et à la
# conclusion orale.
JURY_SECONDS = (0, 30, 50, 75, 115, 140, 160, 180, 205, 225, 245, 260)


JURY_QA = [
    {
        "q": "Qu'est-ce qui est réellement agentique ici ?",
        "a": "Flow Scout enchaîne de façon reproductible la détection, l'extraction, le croisement, les contrôles, la maïeutique, le recalcul et le chargement Atlas. Il sait aussi s'arrêter et demander une validation humaine.",
    },
    {
        "q": "Pourquoi ne pas utiliser simplement un tableau de bord ?",
        "a": "Un tableau de bord affiche des données déjà structurées. Flow Scout construit le modèle, applique les règles d'arbitrage, conserve la preuve cellule par cellule, puis produit un dashboard d'alignement et une file de validation humaine.",
    },
    {
        "q": "Comment empêchez-vous les hallucinations ?",
        "a": "Chaque constat doit référencer une preuve. Une valeur manquante reste inconnue. Sans preuve suffisante, la réponse est « information insuffisante » et aucun contrôle bloquant n'est validé automatiquement.",
    },
    {
        "q": "Que signifie votre niveau de confiance ?",
        "a": "Il exprime la solidité de l'association entre le constat et ses preuves disponibles. Il ne remplace jamais la preuve ni la validation humaine lorsque la décision est bloquante.",
    },
    {
        "q": "Pourquoi l'espace Atlas reste-t-il bloqué à la fin ?",
        "a": "Parce que la démonstration ne résout volontairement que les cas montrés. Les autres questions ouvertes restent visibles. Publier malgré elles contredirait le principe de gouvernance du produit.",
    },
    {
        "q": "Le chargement dans Atlas est-il simulé ?",
        "a": "Le prototype construit et charge réellement un espace Atlas local versionné avec sept cartes, un instantané actif, un journal d'événements et une fonction de retour arrière. La connexion à une plateforme Atlas de production reste hors périmètre du hackathon.",
    },
    {
        "q": "Comment rejouez-vous une décision ?",
        "a": "Le journal conserve l'état initial, la question, la réponse, la validation humaine, le recalcul et l'identifiant de version Atlas. Une version antérieure peut être réactivée sans supprimer l'historique.",
    },
    {
        "q": "Pourquoi sept cartes ?",
        "a": "Elles relient le travail humain, les décisions, les connaissances, les systèmes, l'usage réel de l'IA, la valeur et les possibilités de transformation. La valeur vient surtout des liens entre ces dimensions.",
    },
    {
        "q": "Comment mesurez-vous la qualité du résultat ?",
        "a": "Le jeu de référence vérifie treize critères, dont les quatre cas majeurs, la preuve cellule, le refus de l'ambiguïté, les scores bornés et l'absence de finalisation automatique. Cinq exécutions doivent produire la même empreinte sémantique.",
    },
    {
        "q": "Pourquoi distinguer temps libéré et économie ?",
        "a": "Le temps gagné peut améliorer la capacité ou la qualité sans réduire les dépenses. Flow Scout interdit de monétiser automatiquement un gain de temps sans preuve comptable ou décision de redéploiement.",
    },
    {
        "q": "Qu'apporte la maïeutique ?",
        "a": "Les fichiers montrent une partie du réel. La maïeutique qualifie les décisions, les exceptions, les compétences et les responsabilités manquantes, puis fait confirmer la compréhension avant arbitrage.",
    },
    {
        "q": "Que se passe-t-il si une réponse humaine est fausse ?",
        "a": "Elle reste identifiée comme déclaration humaine, distincte d'un fait source. Lorsqu'une preuve est exigée, la déclaration seule ne suffit pas à valider le contrôle.",
    },
    {
        "q": "Comment protégez-vous les données clients ?",
        "a": "Le pilote commence par minimisation, anonymisation, dépôt contrôlé et traçabilité. Cette version jury fonctionne localement et n'envoie aucun fichier à un service externe.",
    },
    {
        "q": "Quels formats sont déjà pris en charge ?",
        "a": "Le moteur actuel traite les tableaux Excel et CSV prévus par le prototype. Les documents et connecteurs profonds constituent une étape d'industrialisation, pas une promesse cachée du hackathon.",
    },
    {
        "q": "Combien de temps faut-il pour un premier client ?",
        "a": "Le pilote proposé dure quinze jours ouvrés : cadrage, dépôt, cartographie, ateliers de validation et restitution dans Atlas, avant toute intégration profonde au SI.",
    },
    {
        "q": "Qui est l'acheteur ?",
        "a": "Le sponsor naturel est un COMEX, un Chief AI Officer, une direction transformation, risques ou contrôle interne qui doit arbitrer un portefeuille IA dispersé avec des preuves.",
    },
    {
        "q": "Quelle est votre différenciation ?",
        "a": "Flow Scout ne se limite ni à l'inventaire d'IA ni à l'adoption. Il relie l'IA au travail, aux décisions, aux compétences, aux connaissances, aux coûts et aux responsabilités, puis alimente un jumeau cognitif vivant.",
    },
    {
        "q": "Est-ce prêt pour la production ?",
        "a": "Non. Le prototype démontre la chaîne de valeur et les garde-fous. Le SSO, les connecteurs SI profonds, la sécurité de production et le passage à l'échelle sont explicitement hors périmètre du hackathon.",
    },
    {
        "q": "Quel est le risque principal après le hackathon ?",
        "a": "La variété réelle des sources clients. Le prochain travail consiste à éprouver le modèle sur un pilote limité, mesurer les écarts de schéma et renforcer progressivement les adaptateurs sans perdre la traçabilité.",
    },
    {
        "q": "Que demandez-vous au jury ?",
        "a": "De juger la capacité de l'agent à produire une gouvernance utile et vérifiable : montrer ses preuves, reconnaître l'incertitude, provoquer la bonne décision humaine et conserver une trace rejouable.",
    },
]


def build_payload(result: dict[str, object]) -> dict[str, object]:
    evaluation = result["evaluation"]
    workspace = result["atlas_workspace"]
    cockpit = workspace["cockpit"]
    findings = cockpit.get("top_findings", [])
    ai002 = next(
        (
            finding
            for finding in findings
            if finding.get("finding_type") == "delegation_overrun"
        ),
        None,
    )
    value_finding = next(
        (
            finding
            for finding in findings
            if finding.get("finding_type") == "time_without_budget_savings"
        ),
        None,
    )
    timeline = []
    for index, step in enumerate(result["timeline"], start=1):
        enriched = dict(step)
        enriched["number"] = index
        enriched["engine_second"] = enriched.get("at_second")
        enriched["at_second"] = JURY_SECONDS[index - 1]
        next_second = JURY_SECONDS[index] if index < len(JURY_SECONDS) else 280
        enriched["target_duration_seconds"] = next_second - JURY_SECONDS[index - 1]
        enriched["oral"] = ORAL_BY_TITLE.get(
            str(step.get("title")), str(step.get("message", ""))
        )
        timeline.append(enriched)
    return {
        "schema_version": "flow-scout-jury-mode-v1",
        "generated_from": result.get("run_id"),
        "promise": result.get("promise"),
        "source": result.get("source"),
        "timeline": timeline,
        "evaluation": evaluation,
        "xia_readiness": result.get("xia_readiness", {}),
        "workspace": {
            "status": workspace.get("workspace_status"),
            "import_id": workspace.get("import_id"),
            "scores": cockpit.get("scorecard"),
            "counts": cockpit.get("counts"),
            "traceability": cockpit.get("traceability"),
            "ai002": ai002,
            "value": value_finding,
        },
        "ambiguous": result.get("ambiguous_answer_result"),
        "insufficient": result.get("information_insufficient_example"),
        "qa": JURY_QA,
    }


HTML_TEMPLATE = r'''<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Flow Scout — Jury Mode</title>
  <style>
    :root { color-scheme: dark; --bg:#061019; --panel:#0d1b26; --panel2:#122735; --line:#294654; --text:#f5f7f8; --muted:#9fb2bd; --mint:#48dfc3; --blue:#67b8ff; --amber:#ffc561; --red:#ff7075; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; font:16px/1.45 Arial,sans-serif; color:var(--text); background:radial-gradient(circle at 88% 4%,#16414e 0,transparent 29%),var(--bg); }
    button,input { font:inherit; }
    button,.button { border:1px solid var(--line); background:var(--panel2); color:var(--text); border-radius:9px; padding:10px 14px; font-weight:700; cursor:pointer; text-decoration:none; }
    button:hover,.button:hover { transform:translateY(-1px); }
    button.primary { background:var(--mint); color:#04110e; border-color:var(--mint); }
    button.active { border-color:var(--mint); color:var(--mint); }
    main { width:min(1380px,calc(100% - 32px)); margin:auto; padding:24px 0 40px; }
    header { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; }
    .eyebrow { color:var(--mint); font-weight:700; font-size:12px; letter-spacing:.12em; text-transform:uppercase; }
    h1 { margin:7px 0 8px; font-size:clamp(30px,4vw,52px); line-height:1.02; }
    .sub { margin:0; color:var(--muted); max-width:820px; }
    .badges { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:8px; }
    .badge { border:1px solid var(--line); border-radius:999px; padding:7px 11px; font-size:12px; white-space:nowrap; }
    .ok { color:var(--mint); border-color:color-mix(in srgb,var(--mint) 55%,var(--line)); }
    .warn { color:var(--amber); border-color:color-mix(in srgb,var(--amber) 55%,var(--line)); }
    nav,.controls { display:flex; flex-wrap:wrap; gap:9px; }
    nav { margin:24px 0 12px; }
    .view { display:none; }
    .view.active { display:block; }
    .metrics { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin:12px 0; }
    .metric,.card { background:color-mix(in srgb,var(--panel) 94%,transparent); border:1px solid var(--line); border-radius:14px; }
    .metric { padding:13px 15px; }
    .metric strong { display:block; color:var(--mint); font-size:24px; }
    .metric span { color:var(--muted); font-size:12px; }
    .controls { margin:14px 0; align-items:center; }
    .keyboard { color:var(--muted); font-size:12px; margin-left:auto; }
    .grid { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(360px,.85fr); gap:12px; }
    .card { padding:19px; }
    .step-head { display:flex; align-items:center; gap:12px; }
    .step-no { display:grid; place-items:center; min-width:46px; height:46px; border-radius:50%; background:var(--mint); color:#03110e; font-size:20px; font-weight:800; }
    h2,h3 { margin:0; }
    h2 { font-size:28px; }
    h3 { font-size:18px; }
    .kind { margin-top:5px; color:var(--blue); text-transform:uppercase; letter-spacing:.08em; font-size:12px; }
    .message { margin:26px 0 16px; min-height:72px; font-size:23px; line-height:1.28; }
    .proof { margin:14px 0; padding:13px; border-left:3px solid var(--mint); background:#0a1720; }
    .proof code { display:inline-block; margin:5px 9px 0 0; color:var(--mint); }
    .teleprompter { font-size:20px; line-height:1.48; color:#edf4f6; min-height:188px; }
    .teleprompter::before { content:'À DIRE'; display:block; color:var(--mint); font-size:11px; font-weight:700; letter-spacing:.13em; margin-bottom:12px; }
    .progress { height:8px; border-radius:99px; background:#172c37; overflow:hidden; margin-top:18px; }
    .bar { height:100%; width:0; background:linear-gradient(90deg,var(--mint),var(--blue)); transition:width .18s linear; }
    .ticks { display:grid; grid-template-columns:repeat(12,1fr); gap:4px; margin-top:8px; }
    .tick { height:6px; border-radius:8px; background:#1c3542; }
    .tick.done { background:var(--mint); } .tick.current { background:var(--amber); }
    .state-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:12px; }
    .state { padding:13px; border:1px solid var(--line); border-radius:11px; background:#0b1821; }
    .state b { display:block; margin-top:5px; }
    .pass { color:var(--mint); } .fail { color:var(--red); } .blocked { color:var(--amber); }
    .score-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:8px; margin-top:12px; }
    .score { background:#102431; border-radius:9px; padding:10px; text-align:center; }
    .score strong { display:block; font-size:20px; }
    .qa-tools { display:flex; gap:10px; margin:14px 0; }
    .qa-tools input { flex:1; color:var(--text); background:var(--panel2); border:1px solid var(--line); border-radius:9px; padding:11px 13px; }
    .qa-list { display:grid; gap:9px; }
    .qa-practice { margin:12px 0; padding:18px; border:1px solid var(--mint); border-radius:12px; background:#0a1c24; }
    .qa-practice .question { font-size:22px; font-weight:700; margin:8px 0 14px; }
    .qa-practice .answer { color:var(--muted); margin:14px 0 0; }
    .rehearsal-result { margin-top:12px; border-color:var(--mint); }
    .lap-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:7px; margin-top:12px; }
    .lap { padding:8px; border-radius:8px; background:#102431; font-size:12px; }
    .lap.good { border:1px solid var(--mint); }
    .lap.over { border:1px solid var(--red); }
    .lap.under { border:1px solid var(--amber); }
    details { border:1px solid var(--line); border-radius:11px; background:var(--panel); padding:13px 15px; }
    summary { cursor:pointer; font-weight:700; }
    details p { color:var(--muted); margin:10px 0 0; }
    .checks { display:grid; grid-template-columns:repeat(2,1fr); gap:8px; margin-top:14px; }
    .check { border:1px solid var(--line); border-radius:9px; padding:10px 12px; }
    footer { color:var(--muted); font-size:12px; margin-top:13px; display:flex; justify-content:space-between; gap:12px; }
    @media(max-width:900px){ header,footer{display:block}.badges{justify-content:flex-start;margin-top:14px}.metrics{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.state-grid,.score-grid{grid-template-columns:repeat(2,1fr)}.keyboard{width:100%;margin-left:0}.checks{grid-template-columns:1fr} }
  </style>
</head>
<body>
<main>
  <header>
    <div><div class="eyebrow">The Flow Fabric · Hackathon X-IA</div><h1>Flow Scout Jury Mode</h1><p class="sub" id="promise"></p></div>
    <div class="badges"><span class="badge ok">Scénario pré-calculé</span><span class="badge ok">Rejeu hors ligne</span><span class="badge ok">Aucun service externe utilisé</span><span class="badge warn" id="workspaceBadge"></span></div>
  </header>
  <nav><button class="active" data-view="demo">Démonstration</button><button data-view="proof">Résultats et preuves</button><button data-view="qa">Questions du jury</button><a class="button" href="../../portfolio-decision-demo/alignment-dashboard.html" target="_blank" rel="noreferrer">Dashboard d'alignement</a></nav>

  <section id="demo" class="view active">
    <div class="metrics" id="metrics"></div>
    <div class="controls">
      <button class="primary" id="play">Démarrer la démonstration</button><button id="rehearse">Démarrer une répétition</button><button id="pause">Pause</button><button id="next">Étape suivante</button><button id="reset">Remettre à zéro</button><button id="speed">Mode express 60 s</button>
      <span class="keyboard">Espace : pause · → : suivant · R : remise à zéro · Q : questions</span>
    </div>
    <div class="grid">
      <article class="card">
        <div class="step-head"><div class="step-no" id="stepNo"></div><div><h2 id="stepTitle"></h2><div class="kind" id="stepKind"></div></div></div>
        <div class="message" id="stepMessage"></div><div class="proof" id="stepProof" hidden></div>
        <div class="progress"><div class="bar" id="bar"></div></div><div class="ticks" id="ticks"></div>
      </article>
      <aside class="card"><div class="teleprompter" id="oral"></div><div class="badge" id="clock"></div></aside>
    </div>
    <div class="state-grid"><div class="state">Paiements assistés<b id="aiState"></b></div><div class="state">Compétences à préparer<b id="skillState"></b></div><div class="state">Valeur<b id="valueState">Temps ≠ économie</b></div><div class="state">Atlas<b class="blocked" id="atlasState"></b></div></div>
    <div class="card rehearsal-result" id="rehearsalResult" hidden><h3 id="rehearsalTitle"></h3><p class="sub" id="rehearsalSummary"></p><div class="lap-grid" id="rehearsalLaps"></div><div class="controls"><button id="downloadRehearsal">Télécharger le résultat</button></div></div>
  </section>

  <section id="proof" class="view">
    <div class="grid"><article class="card"><h2>Résultats mesurés</h2><div class="checks" id="checks"></div></article><aside class="card"><h2>Scores Atlas</h2><div class="score-grid" id="scores"></div><p class="sub" id="scoreMethod"></p></aside></div>
    <article class="card" style="margin-top:12px"><h2>Préparation X-IA</h2><p class="sub" id="xiaDisclaimer"></p><div class="score-grid" id="xiaScores"></div><div class="proof" id="xiaGap"></div></article>
    <article class="card" style="margin-top:12px"><h2>Preuves du paiement non validé</h2><div class="proof" id="allProofs"></div><p class="sub" id="aiStatement"></p></article>
  </section>

  <section id="qa" class="view"><article class="card"><h2>Questions probables du jury</h2><div class="qa-tools"><input id="qaSearch" placeholder="Rechercher : hallucination, Atlas, client, sécurité…" /><button id="randomQa">Question aléatoire</button></div><div class="qa-practice" id="qaPractice" hidden><span class="badge" id="qaTimer">30 s</span><div class="question" id="qaQuestion"></div><button id="revealQa">Afficher la réponse</button><p class="answer" id="qaAnswer" hidden></p></div><div class="qa-list" id="qaList"></div></article></section>
  <footer><span id="runId"></span><span>Les faits, déclarations humaines, déductions et estimations restent distingués.</span></footer>
</main>
<script>
const DATA=__JURY_DATA__;
const $=id=>document.getElementById(id);
let current=0,timer=null,duration=280,startedAt=0,rehearsalTimer=null,rehearsalStartedAt=0,stepStartedAt=0,rehearsalLaps=[],rehearsalActive=false,lastRehearsal=null,qaTimerHandle=null,currentQa=-1;
const kindLabel={fact:'Fait',deduction:'Déduction',question:'Question',human_declaration:'Déclaration humaine',control:'Contrôle',human_validation:'Validation humaine'};
$('promise').textContent=DATA.promise;$('workspaceBadge').textContent=DATA.workspace.status;$('runId').textContent=`Run ${DATA.generated_from} · ${DATA.source?.name||'dossier assureur'}`;
const ev=DATA.evaluation,tr=DATA.workspace.traceability;
$('metrics').innerHTML=[['Exécutions',`${ev.replay_count}/${ev.replay_count}`],['Contrôles',`${ev.passed_checks}/${ev.check_count}`],['Constats sourcés',`${tr.finding_rate_percent}%`],['Preuves cellule',`${tr.source_localization_rate_percent}%`],['Services externes utilisés',ev.external_service_calls]].map(([l,v])=>`<div class="metric"><strong>${v}</strong><span>${l}</span></div>`).join('');
DATA.timeline.forEach(()=>{const t=document.createElement('div');t.className='tick';$('ticks').appendChild(t)});
function render(i){current=Math.max(0,Math.min(i,DATA.timeline.length-1));const s=DATA.timeline[current];$('stepNo').textContent=s.number;$('stepTitle').textContent=s.title;$('stepKind').textContent=kindLabel[s.statement_kind]||s.statement_kind;$('stepMessage').textContent=s.message;$('oral').textContent=s.oral;$('clock').textContent=`Repère jury : ${s.at_second} s`;
 const proofs=s.evidence||[];$('stepProof').hidden=!proofs.length;$('stepProof').innerHTML=proofs.length?'<b>Preuves affichées</b><br>'+proofs.map(p=>`<code>${p.locator} = ${String(p.quote)}</code>`).join(''):'';
 [...$('ticks').children].forEach((n,x)=>n.className=`tick ${x<current?'done':x===current?'current':''}`);$('bar').style.width=`${current/(DATA.timeline.length-1)*100}%`;
 $('aiState').textContent=current<3?'À contrôler':current<8?'FAIL — bloqué':'PASS — validé';$('aiState').className=current>=8?'pass':current>=3?'fail':'blocked';$('skillState').textContent=current<9?'Écart à qualifier':'PASS — validé';$('skillState').className=current>=9?'pass':'blocked';$('atlasState').textContent=current===DATA.timeline.length-1?`${DATA.workspace.status} · versionné`:DATA.workspace.status;
}
function stopAuto(){if(timer){clearInterval(timer);timer=null}}
function stopRehearsal(){if(rehearsalTimer){clearInterval(rehearsalTimer);rehearsalTimer=null}rehearsalActive=false}
function stopAll(){stopAuto();stopRehearsal()}
function play(){stopAll();startedAt=Date.now();render(0);$('rehearsalResult').hidden=true;$('play').textContent='Rejouer depuis le début';timer=setInterval(()=>{const elapsed=(Date.now()-startedAt)/1000;const nominal=Math.min(280,elapsed*280/duration);let idx=0;DATA.timeline.forEach((s,i)=>{if(s.at_second<=nominal)idx=i});render(idx);$('bar').style.width=`${Math.min(100,elapsed/duration*100)}%`;if(elapsed>=duration){render(DATA.timeline.length-1);stopAuto()}},200)}
function startRehearsal(){stopAll();rehearsalActive=true;rehearsalStartedAt=Date.now();stepStartedAt=rehearsalStartedAt;rehearsalLaps=[];$('rehearsalResult').hidden=true;render(0);rehearsalTimer=setInterval(()=>{const elapsed=(Date.now()-rehearsalStartedAt)/1000;$('clock').textContent=`Chrono : ${elapsed.toFixed(1)} s · repère ${DATA.timeline[current].at_second} s`},100)}
function finishRehearsal(){
 const now=Date.now();rehearsalLaps.push((now-stepStartedAt)/1000);const total=(now-rehearsalStartedAt)/1000;stopRehearsal();
 const stepSeconds=rehearsalLaps.map(x=>Number(x.toFixed(1))),targets=DATA.timeline.map(x=>x.target_duration_seconds),variances=stepSeconds.map((x,i)=>Number((x-targets[i]).toFixed(1))),within=variances.filter(x=>Math.abs(x)<=5).length;
 lastRehearsal={run_id:DATA.generated_from,completed_at:new Date().toISOString(),total_seconds:Number(total.toFixed(1)),target_seconds:280,maximum_seconds:290,target_met:total<=290,step_seconds:stepSeconds,target_step_seconds:targets,step_variances_seconds:variances,steps_within_five_seconds:within};
 let history=[];try{history=JSON.parse(localStorage.getItem('flow-scout-rehearsals')||'[]');history=[lastRehearsal,...history].slice(0,3);localStorage.setItem('flow-scout-rehearsals',JSON.stringify(history))}catch{history=[lastRehearsal]}
 $('rehearsalTitle').textContent=lastRehearsal.target_met?'Répétition terminée dans le temps':'Répétition à raccourcir';$('rehearsalTitle').className=lastRehearsal.target_met?'pass':'fail';
 $('rehearsalSummary').textContent=`${lastRehearsal.total_seconds} s · cible 280 s, maximum 290 s · ${within}/${targets.length} étapes à ±5 s · ${history.length}/3 répétition(s) conservée(s)`;
 $('rehearsalLaps').innerHTML=stepSeconds.map((x,i)=>{const delta=variances[i],state=Math.abs(delta)<=5?'good':delta>5?'over':'under',sign=delta>0?'+':'';return `<div class="lap ${state}">${i+1}. ${DATA.timeline[i].title}<br><b>${x} s / ${targets[i]} s</b><br><span>${sign}${delta} s</span></div>`}).join('');
 $('rehearsalResult').hidden=false;$('clock').textContent=`Répétition : ${lastRehearsal.total_seconds} s`;
}
function advance(){stopAuto();if(!rehearsalActive){render(current+1);return}const now=Date.now();if(current===DATA.timeline.length-1){finishRehearsal();return}rehearsalLaps.push((now-stepStartedAt)/1000);stepStartedAt=now;render(current+1)}
function resetDemo(){stopAll();render(0);$('rehearsalResult').hidden=true;$('play').textContent='Démarrer la démonstration'}
$('play').onclick=play;$('rehearse').onclick=startRehearsal;$('pause').onclick=stopAll;$('next').onclick=advance;$('reset').onclick=resetDemo;$('speed').onclick=()=>{duration=duration===280?60:280;$('speed').textContent=duration===60?'Mode jury 4 min 40':'Mode express 60 s'};$('downloadRehearsal').onclick=()=>{if(!lastRehearsal)return;const blob=new Blob([JSON.stringify(lastRehearsal,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`flow-scout-repetition-${Date.now()}.json`;a.click();URL.revokeObjectURL(url)};
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.view).classList.add('active')});
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;if(e.code==='Space'){e.preventDefault();if(rehearsalActive){stopRehearsal()}else{timer?stopAuto():play()}}if(e.key==='ArrowRight')advance();if(e.key.toLowerCase()==='r')resetDemo();if(e.key.toLowerCase()==='q')document.querySelector('[data-view="qa"]').click()});
$('checks').innerHTML=ev.checks.map(c=>`<div class="check"><span class="pass">PASS</span> · <b>${c.check_id.replaceAll('_',' ')}</b><br><span class="sub">${c.detail}</span></div>`).join('');
const dims=DATA.workspace.scores.dimensions;$('scores').innerHTML=Object.entries(dims).map(([k,v])=>`<div class="score"><strong>${v.score??'—'}</strong><span>${k}</span></div>`).join('');$('scoreMethod').textContent=DATA.workspace.scores.method;
const xia=DATA.xia_readiness||{},xiaCriteria=xia.criteria||{};$('xiaDisclaimer').textContent=`${xia.guardrail||'Scorecard de préparation, non officielle.'} Niveau actuel : ${xia.score_out_of_10??'—'}/10.`;$('xiaScores').innerHTML=Object.values(xiaCriteria).map(v=>`<div class="score"><strong>${v.score_out_of_10??'—'}</strong><span>${v.label} · ${v.weight_percent}%</span></div>`).join('');$('xiaGap').innerHTML=xia.top_gap?`<b>Prochaine amélioration prioritaire</b><br>${xia.top_gap.recommendation}`:'<b>Aucun écart documentaire détecté.</b>';
const ai=DATA.workspace.ai002;$('aiStatement').textContent=ai?.statement||'';$('allProofs').innerHTML=(ai?.evidence||[]).map(p=>`<code>${p.file} · ${p.locator} = ${String(p.quote)}</code>`).join('');
function stopQaTimer(){if(qaTimerHandle){clearInterval(qaTimerHandle);qaTimerHandle=null}}
function drawQA(){stopQaTimer();let next=Math.floor(Math.random()*DATA.qa.length);if(DATA.qa.length>1&&next===currentQa)next=(next+1)%DATA.qa.length;currentQa=next;const item=DATA.qa[currentQa];$('qaPractice').hidden=false;$('qaQuestion').textContent=item.q;$('qaAnswer').textContent=item.a;$('qaAnswer').hidden=true;$('revealQa').hidden=false;const start=Date.now();$('qaTimer').textContent='30 s';qaTimerHandle=setInterval(()=>{const left=Math.max(0,30-(Date.now()-start)/1000);$('qaTimer').textContent=left>0?`${left.toFixed(1)} s`:'Temps écoulé';if(left<=0)stopQaTimer()},100)}
function renderQA(term=''){const needle=term.trim().toLowerCase();$('qaList').innerHTML=DATA.qa.filter(x=>!needle||(x.q+' '+x.a).toLowerCase().includes(needle)).map((x,i)=>`<details ${i===0&&!needle?'open':''}><summary>${x.q}</summary><p>${x.a}</p></details>`).join('')}$('qaSearch').oninput=e=>renderQA(e.target.value);$('randomQa').onclick=drawQA;$('revealQa').onclick=()=>{stopQaTimer();$('qaAnswer').hidden=false;$('revealQa').hidden=true};renderQA();render(0);
</script>
</body>
</html>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = json.loads(args.result.read_text(encoding="utf-8"))
    if not result.get("evaluation", {}).get("passed"):
        raise SystemExit("Le scénario de référence n'a pas réussi ses contrôles.")
    payload = build_payload(result)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e")
    html = HTML_TEMPLATE.replace("__JURY_DATA__", encoded)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(html, encoding="utf-8")
    temporary.replace(args.output)
    print(f"Jury Mode prêt : {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
