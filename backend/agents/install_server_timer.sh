#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo ./backend/agents/install_server_timer.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_USER="${CIVILAI_SERVICE_USER:-${SUDO_USER:-$(logname 2>/dev/null || whoami)}}"
APP_DIR="${CIVILAI_APP_DIR:-$REPO_ROOT}"
ENV_DIR="/etc/civilai"
ENV_FILE="$ENV_DIR/agents.env"

install -d "$ENV_DIR"
install -d "$APP_DIR/backend/agents/reports/server"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR/backend/agents/reports" || true

SOURCE_RUNNER="$(realpath "$SCRIPT_DIR/run_agents_server.sh")"
TARGET_RUNNER="$(realpath -m "$APP_DIR/backend/agents/run_agents_server.sh")"
if [[ "$SOURCE_RUNNER" != "$TARGET_RUNNER" ]]; then
  install -m 0755 "$SOURCE_RUNNER" "$TARGET_RUNNER"
else
  chmod 0755 "$TARGET_RUNNER"
fi

sed \
  -e "s|YOUR_LINUX_USER|$APP_USER|g" \
  -e "s|/home/$APP_USER/CivilAI|$APP_DIR|g" \
  "$SCRIPT_DIR/Features/Deploy_management/Templates/civilai-agents.service" > /etc/systemd/system/civilai-agents.service

install -m 0644 "$SCRIPT_DIR/Features/Deploy_management/Templates/civilai-agents.timer" /etc/systemd/system/civilai-agents.timer

if [[ ! -f "$ENV_FILE" ]]; then
  sed \
    -e "s|YOUR_LINUX_USER|$APP_USER|g" \
    -e "s|/home/$APP_USER/CivilAI|$APP_DIR|g" \
    "$SCRIPT_DIR/Features/Deploy_management/Templates/agents.env.example" > "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
fi

if ! grep -q "^CIVILAI_AGENT_EXIT_ZERO=" "$ENV_FILE"; then
  {
    echo ""
    echo "# Keep systemd timer healthy even when agents report findings."
    echo "CIVILAI_AGENT_EXIT_ZERO=true"
  } >> "$ENV_FILE"
fi

systemctl daemon-reload
systemctl enable --now civilai-agents.timer

echo "Installed civilai-agents.timer."
echo "Edit $ENV_FILE to change URLs, report path, or agent set."
echo "Run once now: sudo systemctl start civilai-agents.service"
echo "View logs: journalctl -u civilai-agents.service -n 100 --no-pager"
