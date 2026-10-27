---
name: vnc-browser
description: Share a headed agent-browser session over noVNC so a human can watch or take over mid-flow. Use when the user wants to remote-control a browser the agent is driving (2FA handoff, CAPTCHA, pair debugging, observing automation live), needs noVNC/VNC/web-based browser sharing, asks to "share my browser session", "let me take over", "watch the agent", or sets up Tailscale-scoped browser handoff. Builds on the agent-browser skill — that one covers the actual browser commands.
allowed-tools: Bash(distrobox:*), Bash(agent-browser:*), Bash(tailscale:*), Bash(curl:*), Bash(xdg-open:*), Bash(ip:*), Bash(ss:*), Bash(pkill:*)
---

# vnc-browser

Run agent-browser **headed** inside a Fedora distrobox with Xvfb + fluxbox +
x11vnc + noVNC. The container's `/tmp/.X11-unix` is auto-shared, so the host
can drive Chrome with `DISPLAY=:99 agent-browser …` while a human watches or
takes over via noVNC in any browser.

agent-browser uses CDP DOM events, not OS input, so the human's mouse and
the agent's clicks **don't fight for focus** — you can both be active in
the same Chrome at once.

Load the `agent-browser` skill for the actual `snapshot`/`click`/`fill`
commands. This skill covers only the shared-display plumbing.

## One-time setup

```bash
# Create the container (Fedora 44 confirmed working; 43 works too)
distrobox create --yes --name vnc-browser --image registry.fedoraproject.org/fedora:44

# Install the display + VNC stack inside it
distrobox enter vnc-browser -- sudo dnf install -y \
  xorg-x11-server-Xvfb x11vnc novnc python3-websockify fluxbox xdotool procps-ng
```

Copy the start script from `templates/start-vnc-browser.sh` (in this skill)
to somewhere stable on disk — `/tmp/` is fine for ad-hoc use; `~/.local/bin/`
if you want it to persist across reboots.

## Start the stack

```bash
distrobox enter vnc-browser -- bash /path/to/start-vnc-browser.sh
```

Output looks like:

```
Display:    :99
noVNC URL:  http://100.x.y.z:6080/vnc.html

Listening:
LISTEN ... 127.0.0.1:5900 ...
LISTEN ... 100.x.y.z:6080 ...
```

The script:

- Auto-detects a Tailscale IP (CGNAT `100.x`) for `BIND_IP`; falls back to
  `127.0.0.1`. Override with `BIND_IP=0.0.0.0` (or any interface IP) if you
  want to expose differently.
- Uses `setsid … >log 2>&1 < /dev/null &` so all four daemons survive the
  `distrobox enter` exiting.
- Is idempotent — re-running kills old daemons and starts fresh.

## Launch agent-browser on the shared display

From the **host**, not inside the container:

```bash
DISPLAY=:99 agent-browser --session vnc --headed open https://example.com
DISPLAY=:99 agent-browser --session vnc snapshot -i
DISPLAY=:99 agent-browser --session vnc click @e3
```

The `--session vnc` flag isolates this session from any other agent-browser
sessions you have running.

Then open `http://<bind-ip>:6080/vnc.html` in any browser to watch or
take over.

## Handoff patterns

### 2FA / CAPTCHA

Agent drives the flow up to the prompt, then waits for a post-handoff
condition:

```bash
DISPLAY=:99 agent-browser --session vnc fill @e3 "user@example.com"
DISPLAY=:99 agent-browser --session vnc fill @e4 "password"
DISPLAY=:99 agent-browser --session vnc click @e5
# Human completes 2FA in noVNC; agent resumes when URL changes:
DISPLAY=:99 agent-browser --session vnc wait --url "**/dashboard" --timeout 120000
DISPLAY=:99 agent-browser --session vnc snapshot -i
```

### Pair debugging

Tell the user the noVNC URL, leave the session running, and `snapshot` /
`screenshot` between manual steps to capture state for the conversation.

### Persistent login

Add `--profile /path/to/profile` (or `--session-name <name>`) to the
agent-browser launch so the human's login survives container/stack restarts.

## Stopping

```bash
distrobox enter vnc-browser -- pkill -f 'Xvfb|fluxbox|x11vnc|websockify'
agent-browser --session vnc close
```

Or destroy everything (loses installed packages too):

```bash
distrobox rm --force vnc-browser
```

## Troubleshooting

**"Chrome window vanished after restarting the stack"**
Killing Xvfb kills every X client, including Chrome. Re-launch with
`agent-browser --session vnc close` then `DISPLAY=:99 agent-browser
--session vnc --headed open <url>`.

**"noVNC page loads but Connect fails"**
Check `ss -ltnp` inside the container — websockify must be bound to the IP
in the URL you're hitting. If `BIND_IP` auto-detection picked the wrong
interface, re-run with `BIND_IP=<ip> distrobox enter vnc-browser -- env
BIND_IP=$BIND_IP bash start-vnc-browser.sh`.

**"Chrome window opens at default size, leaving black space on the right"**
fluxbox doesn't auto-maximize. Click maximize in noVNC, or add this after
launch (needs `wmctrl` installed in the container):

```bash
distrobox enter vnc-browser -- env DISPLAY=:99 wmctrl -r chrome -b add,maximized_vert,maximized_horz
```

**"Permission denied on `/tmp/.X11-unix`"**
distrobox shares it automatically; if it's missing, you're either not in a
distrobox-managed shell or the container was created with `--no-x11`.
Recreate without that flag.

**"Anyone on my tailnet can drive my browser"**
That's the default — `-nopw` for low-friction handoff. To require a VNC
password, edit the start script's `x11vnc` line: drop `-nopw`, add
`-passwd $(cat /tmp/vncpw)` (and create `/tmp/vncpw` first). Tailscale ACLs
are the better lever for restricting which devices can connect.

**"Exposed on 0.0.0.0 — is this safe?"**
No. `-nopw` + `0.0.0.0` is full RCE-equivalent for anyone who can route to
the port. Either keep `BIND_IP` on a tailnet/loopback IP, or add a VNC
password, or front it with an authenticated reverse proxy.
