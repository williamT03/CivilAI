#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo ./agents/uninstall_server_timer.sh" >&2
  exit 1
fi

systemctl disable --now civilai-agents.timer 2>/dev/null || true
systemctl stop civilai-agents.service 2>/dev/null || true
rm -f /etc/systemd/system/civilai-agents.timer
rm -f /etc/systemd/system/civilai-agents.service
systemctl daemon-reload

echo "Removed civilai-agents systemd service and timer."
echo "Reports and /etc/civilai/agents.env were left in place."
