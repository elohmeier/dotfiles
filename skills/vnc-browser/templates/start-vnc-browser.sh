#!/usr/bin/env bash
# Start the vnc-browser noVNC stack inside the distrobox.
#
# Run this *inside* the container:
#   distrobox enter vnc-browser -- bash /path/to/start-vnc-browser.sh
#
# Override defaults via env vars:
#   DISPLAY_NUM=99    Xvfb display number
#   SCREEN=1440x900x24
#   VNC_PORT=5900     local-only x11vnc port
#   PORT=6080         noVNC web port
#   BIND_IP=...       interface for websockify to bind (auto-detects Tailscale CGNAT, falls back to 127.0.0.1)
set -euo pipefail

DISPLAY_NUM="${DISPLAY_NUM:-99}"
SCREEN="${SCREEN:-1440x900x24}"
VNC_PORT="${VNC_PORT:-5900}"
PORT="${PORT:-6080}"

if [[ -z "${BIND_IP:-}" ]]; then
  # Tailscale assigns IPs from 100.64.0.0/10 (CGNAT). distrobox shares the
  # host network namespace, so a tailnet IP on the host is visible here too.
  BIND_IP="$(ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -E '^100\.' | head -1 || true)"
  BIND_IP="${BIND_IP:-127.0.0.1}"
fi

mkdir -p /tmp/vnc-browser-logs
cd /tmp/vnc-browser-logs

# Kill prior run (idempotent)
pkill -f "Xvfb :${DISPLAY_NUM}\b" 2>/dev/null || true
pkill -f "x11vnc.*rfbport ${VNC_PORT}" 2>/dev/null || true
pkill -f "websockify.*:${PORT}" 2>/dev/null || true
pkill -f 'fluxbox' 2>/dev/null || true
sleep 0.5

setsid Xvfb ":${DISPLAY_NUM}" -screen 0 "${SCREEN}" >Xvfb.log 2>&1 < /dev/null &
sleep 0.3
DISPLAY=":${DISPLAY_NUM}" setsid fluxbox >fluxbox.log 2>&1 < /dev/null &
sleep 0.3
setsid x11vnc -display ":${DISPLAY_NUM}" -forever -shared -rfbport "${VNC_PORT}" -nopw -localhost \
  >x11vnc.log 2>&1 < /dev/null &
sleep 0.3
setsid websockify --web=/usr/share/novnc "${BIND_IP}:${PORT}" "localhost:${VNC_PORT}" \
  >websockify.log 2>&1 < /dev/null &
sleep 1

echo "Display:    :${DISPLAY_NUM}"
echo "noVNC URL:  http://${BIND_IP}:${PORT}/vnc.html"
echo
echo "Listening:"
ss -ltnp 2>/dev/null | grep -E ":${VNC_PORT}\b|:${PORT}\b" || true
echo
echo "Logs in /tmp/vnc-browser-logs/{Xvfb,fluxbox,x11vnc,websockify}.log"
echo
echo "Next (run on the host, not inside the container):"
echo "  DISPLAY=:${DISPLAY_NUM} agent-browser --session vnc --headed open <url>"
