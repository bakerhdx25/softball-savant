#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
SITE_ROOT="${SCRIPT_DIR:h}"
REPO_ROOT="${SITE_ROOT:h}"
WAR_ROOT="${REPO_ROOT}/ausl-war"
LOG_ROOT="${SITE_ROOT}/logs"
VENV_ROOT="${REPO_ROOT}/.venv-softball-savant"

mkdir -p "${LOG_ROOT}"
if [[ ! -x "${VENV_ROOT}/bin/python" ]]; then
  python3 -m venv "${VENV_ROOT}"
fi
source "${VENV_ROOT}/bin/activate"

cd "${WAR_ROOT}"
python -m pip install -q -r requirements.txt
PYTHONPATH=src python -m ausl_war.cli build-official-pipeline "$@"

cd "${SITE_ROOT}"
python build.py
python -m unittest -v test_build.py

if [[ -n "${NETLIFY_AUTH_TOKEN:-}" && -n "${NETLIFY_SITE_ID:-}" ]]; then
  if command -v netlify >/dev/null 2>&1; then
    netlify deploy --prod --dir "${SITE_ROOT}" --site "${NETLIFY_SITE_ID}" --auth "${NETLIFY_AUTH_TOKEN}"
  else
    npx --yes netlify-cli deploy --prod --dir "${SITE_ROOT}" --site "${NETLIFY_SITE_ID}" --auth "${NETLIFY_AUTH_TOKEN}"
  fi
else
  echo "Netlify deploy skipped: set NETLIFY_AUTH_TOKEN and NETLIFY_SITE_ID to deploy."
fi
