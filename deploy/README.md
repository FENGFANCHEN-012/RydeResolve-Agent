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

## Undo

```bash
sudo systemctl disable --now ryderesolve
sudo cp /etc/caddy/Caddyfile.bak-default /etc/caddy/Caddyfile && sudo systemctl reload caddy
```
