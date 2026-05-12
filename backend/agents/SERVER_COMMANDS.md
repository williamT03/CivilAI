# CivilAI Agent Server Commands

Common commands for running, checking, resetting, and troubleshooting the CivilAI agentic engineering service on the Linux server.

## Locations

```bash
cd ~/CivilAI
```

Agent reports:

```bash
ls -lah ~/CivilAI/backend/agents/reports/server
```

Agent environment file:

```bash
cat /etc/civilai/agents.env
sudo nano /etc/civilai/agents.env
```

## Run Agents Manually

Run the default server-safe group:

```bash
./backend/agents/run_agents_server.sh
```

Run the server-safe group explicitly:

```bash
./backend/agents/run_agents_server.sh server-safe
```

Run deeper runtime checks:

```bash
./backend/agents/run_agents_server.sh runtime-deep
```

Run frontend checks:

```bash
./backend/agents/run_agents_server.sh frontend
```

Run one agent:

```bash
./backend/agents/run_agents_server.sh security
./backend/agents/run_agents_server.sh deployment-gate
./backend/agents/run_agents_server.sh server-connections
./backend/agents/run_agents_server.sh server-runtime
./backend/agents/run_agents_server.sh data-leak
./backend/agents/run_agents_server.sh tenant-isolation
./backend/agents/run_agents_server.sh llm-safety
```

Run LLM safety probes intentionally:

```bash
CIVILAI_RUN_LLM_SAFETY=true ./backend/agents/run_agents_server.sh llm-safety
```

## Automatic Service

Install or refresh the systemd timer:

```bash
cd ~/CivilAI
chmod +x ./backend/agents/install_server_timer.sh ./backend/agents/uninstall_server_timer.sh ./backend/agents/run_agents_server.sh
sudo ./backend/agents/install_server_timer.sh
```

Start a run immediately:

```bash
sudo systemctl start civilai-agents.service
```

Check timer:

```bash
systemctl status civilai-agents.timer --no-pager -l
systemctl list-timers civilai-agents.timer
```

Check latest service status:

```bash
systemctl status civilai-agents.service --no-pager -l
```

Read logs:

```bash
journalctl -u civilai-agents.service -n 120 --no-pager
journalctl -xeu civilai-agents.service --no-pager -n 160
```

Stop automatic runs:

```bash
sudo systemctl stop civilai-agents.timer
```

Start automatic runs:

```bash
sudo systemctl enable --now civilai-agents.timer
```

Uninstall the timer/service:

```bash
sudo ./backend/agents/uninstall_server_timer.sh
```

## Review Reports

Show failures:

```bash
grep -R '"status": "fail"' backend/agents/reports/server/*.json -n
```

Show warnings:

```bash
grep -R '"status": "warn"' backend/agents/reports/server/*.json -n
```

Print readable failure and warning summaries:

```bash
python - <<'PY'
import json
from pathlib import Path

for path in sorted(Path("backend/agents/reports/server").glob("*.json")):
    data = json.loads(path.read_text())
    bad = [r for r in data["results"] if r["status"] in {"fail", "warn"}]
    if not bad:
        continue

    print(f"\n{path.name}")
    for r in bad:
        print(f"  {r['status'].upper()} {r['name']}: {r['summary']}")
        if r.get("details"):
            print(f"    details: {r['details']}")
PY
```

Open one report:

```bash
cat backend/agents/reports/server/security.json
cat backend/agents/reports/server/deployment-gate.json
cat backend/agents/reports/server/server-connections.json
```

## Clean Reset

Reset only the agent service state:

```bash
sudo systemctl reset-failed civilai-agents.service
```

Clear reports and run fresh:

```bash
cd ~/CivilAI
sudo systemctl stop civilai-agents.timer
sudo systemctl stop civilai-agents.service

sudo rm -rf /home/will/CivilAI/backend/agents/reports/server
mkdir -p /home/will/CivilAI/backend/agents/reports/server
sudo chown -R will:will /home/will/CivilAI/backend/agents/reports

sudo systemctl daemon-reload
sudo systemctl reset-failed civilai-agents.service
sudo systemctl enable --now civilai-agents.timer
sudo systemctl start civilai-agents.service
```

Verify reset:

```bash
systemctl status civilai-agents.timer --no-pager -l
systemctl status civilai-agents.service --no-pager -l
journalctl -u civilai-agents.service -n 120 --no-pager
ls -lah /home/will/CivilAI/backend/agents/reports/server
```

## Backend Health Checks

Check local backend:

```bash
curl -i http://127.0.0.1:8000/health | head -40
curl -s http://127.0.0.1:8000/api/v1/health | python -m json.tool
```

Check security headers:

```bash
curl -i http://127.0.0.1:8000/health | grep -Ei 'x-content-type-options|x-frame-options|referrer-policy|permissions-policy'
```

Check public backend through Cloudflare:

```bash
curl -i https://api.yourdomain.com/health | head -40
```

Check jurisdictions:

```bash
curl -s http://127.0.0.1:8000/api/custom/jurisdictions | python -m json.tool
```

Check metrics:

```bash
curl -s http://127.0.0.1:8000/metrics | head -40
```

## Backend Service

Restart backend:

```bash
sudo systemctl restart civilai-backend
```

Check backend status:

```bash
systemctl status civilai-backend --no-pager -l
```

Read backend logs:

```bash
journalctl -u civilai-backend -n 160 --no-pager
```

Follow backend logs:

```bash
journalctl -u civilai-backend -f
```

## Cloudflare Tunnel

Check tunnel status:

```bash
systemctl status cloudflared --no-pager -l
```

Restart tunnel:

```bash
sudo systemctl restart cloudflared
```

Read tunnel logs:

```bash
journalctl -u cloudflared -n 160 --no-pager
```

## Dependency And Security Audit

Install dependencies:

```bash
cd ~/CivilAI
.venv/bin/python -m pip install -r requirements.txt
```

Install `pip-audit`:

```bash
.venv/bin/python -m pip install pip-audit
```

Run dependency audit directly:

```bash
.venv/bin/python -m pip_audit -r requirements.txt
```

Run security agent:

```bash
./backend/agents/run_agents_server.sh security
```

## Git Update Flow

Pull latest changes:

```bash
cd ~/CivilAI
git pull
.venv/bin/python -m pip install -r requirements.txt
sudo systemctl restart civilai-backend
sudo ./backend/agents/install_server_timer.sh
sudo systemctl start civilai-agents.service
```

If local server edits block pull:

```bash
git status --short
git stash push -m "server local edits"
git pull
```

Reapply a stash only if needed:

```bash
git stash list
git stash show -p stash@{0}
git stash pop stash@{0}
```

## Agent Environment Settings

Edit:

```bash
sudo nano /etc/civilai/agents.env
```

Useful defaults:

```env
CIVILAI_AGENT_SET=server-safe
CIVILAI_BACKEND_URL=http://127.0.0.1:8000
CIVILAI_FRONTEND_URL=https://civilai.willcloudlab.com
CIVILAI_AGENT_REPORT_DIR=/home/will/CivilAI/backend/agents/reports/server
CIVILAI_PYTHON=/home/will/CivilAI/.venv/bin/python
CIVILAI_RUN_LLM_SAFETY=false
CIVILAI_AGENT_HTTP_TIMEOUT_SECONDS=30
CIVILAI_AGENT_EXIT_ZERO=true
```

Apply env changes:

```bash
sudo systemctl daemon-reload
sudo systemctl start civilai-agents.service
```

## Common Fixes

Fix report permissions:

```bash
sudo mkdir -p /home/will/CivilAI/backend/agents/reports/server
sudo chown -R will:will /home/will/CivilAI/backend/agents/reports
```

Fix placeholder paths in agent env:

```bash
sudo sed -i 's|/home/YOUR_LINUX_USER/CivilAI|/home/will/CivilAI|g' /etc/civilai/agents.env
sudo sed -i 's|YOUR_LINUX_USER|will|g' /etc/civilai/agents.env
```

Increase endpoint timeout:

```bash
sudo sed -i 's|CIVILAI_AGENT_HTTP_TIMEOUT_SECONDS=.*|CIVILAI_AGENT_HTTP_TIMEOUT_SECONDS=60|' /etc/civilai/agents.env
```

Temporarily run only policy checks:

```bash
sudo sed -i 's|CIVILAI_AGENT_SET=.*|CIVILAI_AGENT_SET=policy-gate|' /etc/civilai/agents.env
sudo systemctl start civilai-agents.service
```

Restore normal automatic checks:

```bash
sudo sed -i 's|CIVILAI_AGENT_SET=.*|CIVILAI_AGENT_SET=server-safe|' /etc/civilai/agents.env
```

## Suggested Routine

Daily quick look:

```bash
systemctl list-timers civilai-agents.timer
grep -R '"status": "fail"' backend/agents/reports/server/*.json -n
```

After deploy:

```bash
sudo systemctl restart civilai-backend
sudo systemctl start civilai-agents.service
journalctl -u civilai-agents.service -n 120 --no-pager
```

Weekly deeper check:

```bash
./backend/agents/run_agents_server.sh runtime-deep
```
