# Deploying RydeResolve on the Tencent server

Server: Tencent Cloud, Singapore, 2 vCPU / 1.9 GB, Ubuntu 24.04, Caddy on port 80.
The app runs as a systemd service on 127.0.0.1:8000; Caddy proxies port 80 to it.

Remote access needs an access code: with `API_DEMO_KEY` / `API_ADMIN_KEY` set, every `/api/`
call except `/api/health` must send `Authorization: Bearer <code>`; without them, remote access is
refused (`src/api/access.py`). One review runs at a time.

## Already on the server (2026-10-12)

- Code in `~/ryderesolve` (from `git archive` of feature/rule-engine).
- Virtualenv `~/ryderesolve/.venv` with `requirements.txt` installed.
- `~/ryderesolve/.env` (mode 600) with only the variables the server needs and fresh access
  codes; the codes are kept on the developer laptop, not in the repo.

## Steps left

```bash
ssh ryde
cd ~/ryderesolve
sed -i 's/\r$//' .env                         # the env file was written on Windows
sudo cp deploy/ryderesolve.service /etc/systemd/system/
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-default
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl daemon-reload
sudo systemctl enable --now ryderesolve
sudo systemctl reload caddy
curl -s 127.0.0.1:8000/api/health             # expect {"status":"healthy"}
```

Then open http://43.134.17.192 and enter the demo access code.

## Update to a newer commit

From the laptop, in the repo:

```bash
git archive --format=tar HEAD | ssh ryde 'tar -x -C ~/ryderesolve'
ssh ryde 'sudo systemctl restart ryderesolve'
```

If `requirements.txt` changed, install it before the restart:
`ssh ryde 'cd ~/ryderesolve && .venv/bin/pip install -q -r requirements.txt'`.

## Checks after each update

Faults found on 2026-10-13 that the laptop tests did not show (docs/08 D44):

```bash
ssh ryde 'cd ~/ryderesolve && curl -s 127.0.0.1:8000/api/health && echo'          # service up
ssh ryde 'cd ~/ryderesolve && .venv/bin/python -c "from src.core.workflow import build_dispute_graph; build_dispute_graph(); print(\"graph ok\")"'
```

Then run one case from the dashboard. If every LLM step fails with HTTP 402, the server's
`CEREBRAS_API_KEY` has no credit left: put another key in `~/ryderesolve/.env` and restart.

## Keep Qdrant awake before a live demo

The Qdrant Cloud free cluster suspends after a period with no requests, and the first request after
that fails; `/api/health` does not touch Qdrant, so the service looks healthy while the policy lookup
is broken. `deploy/qdrant_keepalive.sh` lists the collections once, reading the URL and key from
`~/ryderesolve/.env`. Run it every 5 minutes from cron (once, on the server):

```bash
chmod +x ~/ryderesolve/deploy/qdrant_keepalive.sh
(crontab -l 2>/dev/null; echo '*/5 * * * * ~/ryderesolve/deploy/qdrant_keepalive.sh >> ~/qdrant_keepalive.log 2>&1') | crontab -
~/ryderesolve/deploy/qdrant_keepalive.sh      # expect "... qdrant 200"
```

## Which cases the dashboard lists

`EXTRA_DISPUTE_DIRS` in `~/ryderesolve/.env` (colon-separated, relative to the repo) adds evaluation
folders to the dashboard's case list. For the Demo Day build it should include the harassment and
driver-award sets:

```
EXTRA_DISPUTE_DIRS=data/eval_cases/fresh2_sonnet:data/eval_cases/images:data/eval_cases/harassment_routing:data/eval_cases/harassment_routing3:data/eval_cases/driver_award
```

## Undo

```bash
sudo systemctl disable --now ryderesolve
sudo cp /etc/caddy/Caddyfile.bak-default /etc/caddy/Caddyfile && sudo systemctl reload caddy
```
