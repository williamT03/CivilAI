#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_ROOT="$REPO_ROOT/frontend/Website/civil-ai-web"
PYTHON_BIN="${CIVILAI_PYTHON:-$REPO_ROOT/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

cd "$REPO_ROOT"
"$PYTHON_BIN" -m isort backend agents scripts
"$PYTHON_BIN" -m black backend agents scripts

cd "$FRONTEND_ROOT"
npm run format
