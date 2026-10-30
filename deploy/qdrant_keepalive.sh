#!/usr/bin/env bash
# Keeps the Qdrant Cloud free cluster awake: it suspends after a period with no requests, and the
# first request after that fails, which breaks a live demo (/api/health does not touch Qdrant).
# Reads QDRANT_URL and QDRANT_API_KEY from the app's .env and lists the collections once.
#
# Install on the server (every 5 minutes, log kept small):
#   (crontab -l 2>/dev/null; echo '*/5 * * * * ~/ryderesolve/deploy/qdrant_keepalive.sh >> ~/qdrant_keepalive.log 2>&1') | crontab -
#   tail -n 200 ~/qdrant_keepalive.log
set -u
ENV_FILE="${1:-$HOME/ryderesolve/.env}"
url=$(grep -E '^QDRANT_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r"')
key=$(grep -E '^QDRANT_API_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r"')
if [ -z "$url" ]; then
  echo "$(date '+%F %T') no QDRANT_URL in $ENV_FILE"
  exit 1
fi
code=$(curl -s -o /dev/null -m 20 -w '%{http_code}' -H "api-key: $key" "$url/collections")
echo "$(date '+%F %T') qdrant $code"
[ "$code" = "200" ]
