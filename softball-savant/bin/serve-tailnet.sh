#!/bin/zsh
set -euo pipefail

cd /Users/openclaw/ausl/softball-savant

while true; do
  TS_IP=$(/usr/local/bin/tailscale ip -4 2>/dev/null | head -n 1 || true)
  if [[ -n "${TS_IP}" ]]; then
    exec /usr/bin/python3 -m http.server 8043 --bind "${TS_IP}"
  fi
  sleep 5
done
