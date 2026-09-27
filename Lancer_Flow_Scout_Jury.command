#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_file="${project_dir}/docs/references/Flow_Scout_Assureur_Demo_Donnees.xlsx"
portfolio_input="${project_dir}/docs/examples/portfolio-decision-input-demo.json"
portfolio_output="${project_dir}/outputs/portfolio-decision-demo"
jury_root="${project_dir}/outputs/jury-mode"
latest_dir="${jury_root}/latest"
archive_dir="${jury_root}/archives"
log_file="${jury_root}/last-launch.log"

clear 2>/dev/null || true
echo ""
echo "FLOW SCOUT — JURY MODE"
echo "========================"
echo ""
echo "1/6  Vérification du dossier assureur…"
if [[ ! -f "${source_file}" ]]; then
  echo "ERREUR : fichier de démonstration introuvable."
  echo "Attendu : ${source_file}"
  read -r -n 1 -p "Appuyez sur une touche pour fermer."
  exit 1
fi
if [[ ! -f "${portfolio_input}" ]]; then
  echo "ERREUR : portefeuille de démonstration introuvable."
  echo "Attendu : ${portfolio_input}"
  read -r -n 1 -p "Appuyez sur une touche pour fermer."
  exit 1
fi

mkdir -p "${jury_root}" "${archive_dir}"
if [[ -d "${latest_dir}" ]]; then
  archive_stamp="$(date '+%Y%m%d-%H%M%S')-$$"
  mv "${latest_dir}" "${archive_dir}/${archive_stamp}"
fi
mkdir -p "${latest_dir}"

echo "2/6  Exécution réelle de Flow Scout, cinq passages…"
if ! "${project_dir}/scripts/run_winner_demo.sh" \
  "${source_file}" \
  "${latest_dir}" >"${log_file}" 2>&1; then
  echo "ERREUR : la démonstration n'a pas terminé ses contrôles."
  echo "Journal : ${log_file}"
  read -r -n 1 -p "Appuyez sur une touche pour fermer."
  exit 1
fi

echo "3/6  Arbitrage du portefeuille et dashboard d'alignement…"
python3 "${project_dir}/scripts/run_portfolio_decision.py" \
  --input "${portfolio_input}" \
  --output-dir "${portfolio_output}" >>"${log_file}" 2>&1

echo "4/6  Construction de l'interface guidée hors ligne…"
python3 "${project_dir}/scripts/build_jury_mode.py" \
  --result "${latest_dir}/winner-demo-result.json" \
  --output "${latest_dir}/index.html"

echo "5/6  Empreintes et manifeste de traçabilité…"
python3 "${project_dir}/scripts/build_jury_manifest.py" \
  --project "${project_dir}" \
  --run "${latest_dir}"

summary="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("{}/{} contrôles · {}/5 passages · {} appel payant".format(d["passed_checks"], d["check_count"], d["replay_count"], d["external_service_calls"]))' "${latest_dir}/evaluation-scorecard.json")"
alignment="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("alignement {}/100 · {}".format(d["portfolio_alignment_score"], d["overall_status"]))' "${portfolio_output}/alignment-dashboard.json")"
echo "6/6  ${summary} · ${alignment}"
echo ""
echo "Jury Mode prêt."
echo "Le fichier source, les résultats et le journal sont conservés localement."

if [[ "${FLOW_SCOUT_SERVE:-1}" = "0" || "${FLOW_SCOUT_NO_OPEN:-0}" = "1" ]]; then
  echo ""
  echo "Exécution terminée sans ouvrir l’interface."
  exit 0
fi

echo ""
echo "Démarrage de la console locale…"
exec python3 "${project_dir}/scripts/serve_jury_mode.py" \
  --project "${project_dir}" \
  --open-browser
