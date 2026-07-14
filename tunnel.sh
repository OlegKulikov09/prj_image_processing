#!/usr/bin/env bash
# Ensure the backend is up, then start a FRESH Cloudflare quick tunnel and print
# the public URL. Run this after each reboot / laptop-sleep.
#   ./tunnel.sh
cd "$(dirname "$0")"

# 1. Backend up? (start it and wait for model warmup if not)
if ! curl -s -o /dev/null --max-time 3 http://127.0.0.1:8000/ ; then
  echo "Backend down — starting it…"
  nohup ./.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 \
    > data/server.log 2>&1 &
  for i in $(seq 1 45); do
    curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/dres/status 2>/dev/null \
      | grep -q 200 && break
    sleep 1
  done
fi
echo "Backend: up on http://127.0.0.1:8000"

# 2. Fresh tunnel
pkill -f "cloudflared tunnel" 2>/dev/null
sleep 1
nohup cloudflared tunnel --url http://localhost:8000 > data/tunnel.log 2>&1 &
echo "Starting Cloudflare tunnel…"
URL=""
for i in $(seq 1 30); do
  URL=$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' data/tunnel.log | head -1)
  [ -n "$URL" ] && break
  sleep 1
done

echo
if [ -n "$URL" ]; then
  echo "  ✅ Public URL:  $URL"
else
  echo "  ⚠️  URL not found yet — check data/tunnel.log"
fi
echo
