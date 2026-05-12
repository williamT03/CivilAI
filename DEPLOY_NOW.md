# Civil AI Publish Guide

This is the fastest stable way to publish Civil AI right now:

- Linux server runs the backend
- Cloudflare Tunnel exposes the backend publicly
- Cloudflare Pages hosts the frontend

## 1. Server prerequisites

Install Python, git, and create the app environment:

```bash
sudo apt update
sudo apt install -y git python3.11 python3.11-venv python3-pip
git clone https://github.com/williamT03/CivilAI.git
cd CivilAI
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Backend environment

Create `backend/.env` on the server:

```env
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_API_BASE=https://api.deepseek.com
CUSTOM_RAG_BASE_URL=https://civilai-api.willcloudlab.com/api/custom
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3
```

## 3. Parse and verify data

Make sure your ordinance PDFs are in `backend/Data/PDF`, then run:

```bash
cd ~/CivilAI
source .venv/bin/activate
export PARSE_MAX_WORKERS=1
export PARSE_EMBED_BATCH_SIZE=2
export PARSE_EMBED_CHUNK_GROUP_SIZE=32
export PARSE_CHROMA_BATCH_SIZE=100
python -m backend.Features.Pipeline_management.Parser.parser_run
```

## 4. Run backend as a service

Copy [civilai-backend.service](/Users/drago/Documents/Coding assignments/CivilAI/deploy/civilai-backend.service) to `/etc/systemd/system/civilai-backend.service` and replace `YOUR_LINUX_USER`.

Then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable civilai-backend
sudo systemctl start civilai-backend
sudo systemctl status civilai-backend
```

Check the API:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/custom/jurisdictions
```

## 5. Expose backend with Cloudflare Tunnel

Cloudflare’s docs recommend a named tunnel for published services and allow routing a public hostname to a local origin service.

Install `cloudflared` on the Linux server, then authenticate:

```bash
cloudflared tunnel login
cloudflared tunnel create civilai-api
cloudflared tunnel route dns civilai-api api.yourdomain.com
```

Create `~/.cloudflared/config.yml` using [cloudflared-config.yml.example](/Users/drago/Documents/Coding assignments/CivilAI/deploy/cloudflared-config.yml.example) and replace:

- `YOUR_TUNNEL_UUID`
- `YOUR_LINUX_USER`
- `api.yourdomain.com`

Install and start the service:

```bash
sudo cloudflared --config /home/YOUR_LINUX_USER/.cloudflared/config.yml service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared
```

Test the public API:

```bash
curl https://api.yourdomain.com/health
curl https://api.yourdomain.com/api/custom/jurisdictions
```

## 6. Deploy frontend to Cloudflare Pages

Create a Cloudflare Pages project from this repo with these settings:

- Root directory: `frontend/Website/civil-ai-web`
- Framework preset: `Next.js (Static HTML Export)`
- Build command: `npx next build`
- Build output directory: `out`

Set these environment variables in Pages:

```env
NEXT_PUBLIC_CUSTOM_API_BASE=https://api.yourdomain.com/api/custom
NEXT_PUBLIC_LLAMA_API_BASE=https://api.yourdomain.com/api/llama
NEXT_PUBLIC_ENABLE_LLAMA=false
```

## 7. Final smoke test

After Pages deploys:

1. Open the site.
2. Run a Custom RAG query.
3. Confirm the code-focus dropdown loads.
4. Upload a PDF.
5. Confirm the uploaded PDF appears in the filter after processing.
6. Open one of the returned source links and confirm it lands on the correct PDF page.

## 7.5. Enable automatic agentic checks

Install the automated server-side agent checks:

```bash
cd ~/CivilAI
chmod +x ./backend/agents/install_server_timer.sh ./backend/agents/uninstall_server_timer.sh
sudo ./backend/agents/install_server_timer.sh
sudo systemctl start civilai-agents.service
```

Configure URLs and agent behavior:

```bash
sudo nano /etc/civilai/agents.env
```

Check status and logs:

```bash
systemctl list-timers civilai-agents.timer
journalctl -u civilai-agents.service -n 100 --no-pager
```

Reports are written to `backend/agents/reports/server/` by default.

## 8. Updating later

On the server:

```bash
cd ~/CivilAI
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart civilai-backend
sudo systemctl restart cloudflared
```

Cloudflare Pages will rebuild automatically when you push frontend changes.
