#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_input="${1:-docs/references/Flow_Scout_Assureur_Demo_Donnees.xlsx}"
output_input="${2:-outputs/winner-demo}"

if [[ "${source_input}" = /* ]]; then
  source_file="${source_input}"
else
  source_file="${project_dir}/${source_input}"
fi

if [[ "${output_input}" = /* ]]; then
  output_dir="${output_input}"
else
  output_dir="${project_dir}/${output_input}"
fi

cd "${project_dir}/backend"
PYTHONPATH=. python3 -m app.flow_scout winner-demo \
  "${source_file}" \
  --output "${output_dir}" \
  --replay-count 5
