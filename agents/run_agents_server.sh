#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

AGENT="${1:-all}"
BACKEND_URL="${CIVILAI_BACKEND_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${CIVILAI_FRONTEND_URL:-https://civilai.willcloudlab.com}"
REPORT_DIR="${CIVILAI_AGENT_REPORT_DIR:-$SCRIPT_DIR/reports/server}"
PYTHON_BIN="${CIVILAI_PYTHON:-$REPO_ROOT/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

cd "$SCRIPT_DIR"
"$PYTHON_BIN" -m civilai_agents.runner \
  --repo-root "$REPO_ROOT" \
  --agent "$AGENT" \
  --backend-url "$BACKEND_URL" \
  --frontend-url "$FRONTEND_URL" \
  --report-dir "$REPORT_DIR"
