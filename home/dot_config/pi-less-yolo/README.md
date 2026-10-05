# Shared agent sandbox

Pi, Codex CLI, and Claude Code use one development image and the same container
isolation, egress filtering, credential injection, and approval UI:

```sh
mise run agent:build
mise run agent:pi
mise run agent:codex
mise run agent:claude
AGENT=codex mise run agent:shell
AGENT=codex mise run agent:egress web
```

`agent:pi`, `agent:codex`, and `agent:claude` select their own agent regardless of
`AGENT`. Shell and egress commands use `AGENT=pi|codex|claude`, defaulting to Pi.
Run egress commands from the same project as the agent. All launchers default to
interactive egress filtering; shells also default to TLS inspection and recording.
An explicitly empty `PI_EGRESS` disables filtering. Docker DNS blocking remains
opt-in with `PI_EGRESS_BLOCK_DNS=1`; Podman does not support that option.

The existing `pi` / `pi:*` commands, `PI_*` settings, image names, and storage
locations remain available. `agent-config` (also available as `pi-config`) edits
the shared settings. The installed files remain under `~/.config/pi-less-yolo`.
`run.sh`, `container.sh`, `runtime.sh`, and `egress.sh` contain the shared runner;
`profile.sh` defines the agent-specific mounts and environment. CLI versions are
pinned in `Dockerfile`; update those pins and run `agent:build` to upgrade.

## Configuration and authentication

Pi retains its existing `~/.pi/agent` mount. Codex and Claude each get a dedicated
container home under `${XDG_DATA_HOME:-~/.local/share}/agent-sandbox/<agent>`,
mounted at `/home/piuser`. Their settings, logins, plugins, and sessions persist
there, separately from the host's normal `~/.codex` and `~/.claude` directories.
Codex settings live in `codex/.codex/config.toml`; Claude settings live in
`claude/.claude/settings.json` beneath that base. Host credentials, hooks, MCP
configurations, and skills are not imported automatically. Install the desired
skills into these homes or explicitly mount their directories read-only with
`PI_EXTRA_MOUNTS` (including targets of any skill symlinks).

For subscription login:

```sh
mise run agent:codex login --device-auth
mise run agent:claude
```

Follow the displayed browser login instructions. OAuth credentials stored in the
container home are readable by that agent; proxy injection does not hide them.
Codex device login requires account support. Additional authentication hosts can
be approved through the selected agent's egress UI.

For API keys, export `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` on the host. Codex's
launcher selects an environment-key provider when `OPENAI_API_KEY` is set, avoiding
writing the key or a project-specific placeholder into `auth.json`. Unset it to
use the subscription login. Claude also accepts `CLAUDE_CODE_OAUTH_TOKEN`.
To keep real keys outside the agent container, configure scopes before launching:

```sh
mise run agent:egress secrets add OPENAI_API_KEY api.openai.com
mise run agent:egress secrets add ANTHROPIC_API_KEY api.anthropic.com
```

Codex runs with its internal approvals and sandbox bypassed because the outer
container supplies isolation. Claude retains its permission prompts. Neither
launcher publishes ports or mounts the Docker socket. Both inherit proxy settings
and trust the proxy CA, including Codex HTTPS/WebSocket certificate verification.
Native desktop/browser integrations and host-only MCP executables need separate
configuration; these commands launch the Linux CLIs.

## Shared rules, separate runtime state

Saved global and project rules are shared across agents. Approved project rule
changes propagate only the approved delta to running contexts; they do not load
unapproved edits from the workspace. Each agent has its own proxy, CA, credentials,
pending requests, and recordings. Codex and Claude append `-codex` / `-claude` to
the project context directory (or `global` outside a project), and use automatically
allocated ports and subnets. Pi retains its previous context identity.

Multiple sessions of the **same agent in the same project** still share a proxy
and its launch settings. For independent session policies, use a distinct
`PI_EGRESS_DIR` and `PI_EGRESS_NAME` plus non-conflicting network/port overrides.
Explicit `PI_EGRESS_DIR` selects exactly that directory regardless of agent.

## Pi egress commands

Open a shell, then open its network controls from a second terminal in the same project:

```sh
mise run pi:shell
mise run pi:egress web
```

To print the authenticated URL for copying, without opening a browser or
starting/restarting the proxy:

```sh
mise run pi:egress url
```

The saved `web-url` in the context's state directory uses `127.0.0.1` and the published
host port. The `url` command also corrects older files containing a Docker
network address. For an older file with a custom port, supply the original
`PI_EGRESS_WEB_PORT` when correcting it. Repeated `web` calls print the URL and
open the browser without restarting a ready, running proxy. A saved URL becomes
invalid when the proxy stops; start it with `web` to obtain a current URL.

`pi:shell` defaults to interactive egress filtering, HTTPS inspection for all
hosts, and HTTP flow recording. Unknown hosts wait for approval and are denied
after 60 seconds. Provider endpoints detected from credentials and the npm
registry are allowed automatically. Explicit deny rules take precedence.

The web command opens an authenticated approval page. Choose Allow/Deny once,
for the session, or save to the displayed scope. Persistent browser decisions apply to the exact
host and port. “Open live traffic” opens mitmweb in another tab, with live
requests, native interception, editing, resume and replay. Destination rules
and credential scopes are checked after request edits. The approval page can
be opened before any traffic or recordings exist. `pi:egress watch` remains
available for terminal approvals.

Shells in the same project share a proxy; different projects/worktrees have
separate proxies, internal networks, approval queues, credentials and recordings.
The nearest ancestor containing `mise.toml` or `.git` defines the project root;
commands in its subdirectories use that context. `PI_EGRESS_PROJECT_ROOT` can
select an explicit root (empty selects the global context).
Session decisions last until that project's `pi:egress stop` or a proxy restart;
each new Pi task updates only that context's configuration and active secrets.
Placeholder identities survive subsequent launches. Opening
the web UI preserves an existing configuration. Closing the browser does not
stop filtering or recording.

## Shared project rules

Keep general personal allowances in the global user list; commit project-specific
rules in `mise.toml`:

```toml
[env]
PI_EGRESS = "interactive"
PI_EGRESS_RULE_SCOPE = "project"
PI_EGRESS_ALLOW = """
grafana.example.com:443
artifacts.example.com:443
"""
PI_EGRESS_DENY = "blocked.example:443"
```

Global and project allowances are additive, alongside automatic provider/npm
defaults and active secret scopes. A persistent deny in either scope wins over
all allows, including temporary approvals. An unmatched request prompts in
interactive mode and is denied in allowlist mode.

```sh
mise run pi:egress watch --scope project
mise run pi:egress web --scope project
mise run pi:egress allow --scope project api.example.com:443
mise run pi:egress deny --scope global blocked.example:443
mise run pi:egress remove --scope project allow api.example.com:443
mise run pi:egress list
```

The scope option follows the command and precedes its arguments. It overrides
`PI_EGRESS_RULE_SCOPE`; the default remains `global`. `watch` shows the project
and destination file before prompting. `A`/`N` save the exact host and port to
that scope; once/session choices do not edit files. Global changes through the
CLI or browser propagate to all existing context snapshots. Removal affects
only the selected scope; another allowance may still grant access. `list`
separates defaults, global rules and active project/environment snapshots.

Project saves preserve unrelated TOML settings and comments, deduplicate rules,
and activate only the explicitly saved rule. They never evaluate TOML templates.
Rule values must be literal strings for automatic editing, and symlinked
`mise.toml` files are rejected. Commit project changes to share them with the team.

The proxy never reads the writable project file. Rules are snapshotted by a host
launch or an explicit `mise run pi:egress reload`; file edits by the agent cannot
expand the running policy. Reload uses the current resolved host environment,
so invoke it through mise after manual config changes. It refreshes rule lists,
not proxy mode, credentials or interception settings. Starting a new shell is
also an explicit reload boundary, including for existing shells in that project.

`web` starts a small host approval bridge that exits when its proxy stops. Browser
save buttons show the selected scope and are disabled without a live bridge;
run `web` again to reconnect it. Once/session approvals require no bridge. The
bridge validates pending requests and writes the project file on the host;
neither the repository nor other projects' state is mounted into the proxy.
The most recent `web --scope …` selects the browser's save scope; `watch` retains
its own explicitly displayed scope.

`mise.local.toml` retains normal mise override semantics: setting
`PI_EGRESS_ALLOW` there replaces that variable from `mise.toml`, rather than
adding a third list. Additive project-local rules are not implemented yet.

## Overrides

```sh
PI_EGRESS_RECORD=0 mise run pi:shell       # disable disk recording
PI_EGRESS_INSPECT= mise run pi:shell       # tunnel HTTPS, except active secret scopes
PI_EGRESS=allowlist mise run pi:shell      # deny unknown hosts without prompting
PI_EGRESS= mise run pi:shell               # disable the proxy entirely
```

`PI_EGRESS_RECORD=1` enables recording; `0` disables it. Recording and TLS
inspection are separate: without inspection, HTTPS bodies cannot be recorded.
All agent tasks default to filtering. Persist settings with `agent-config`
or the project's mise environment. `PI_EGRESS_WEB_PORT` changes the host web
port (automatically allocated for projects; 8081 for the global context).
`url` always prints the allocated localhost URL. `PI_LOCAL_MODELS` requires disabling egress explicitly
because host networking bypasses the internal network.

Uncompressed server-sent events stream incrementally and are recorded when the
response completes. Compressed event streams are buffered for body redaction.

## State, credentials and recordings

Global rules and secret-scope definitions live in `~/.local/state/pi-egress`.
Project runtime state lives under `projects/<root-hash>[-<agent>]/`; the non-project
context uses `global[-<agent>]/` (Pi omits the suffix). `status` prints the selected state path. Keys, tokens,
credentials and recordings stay outside the repository and mounted Pi agent
directory. Global secret scopes are compiled separately with each launch's host
credentials; real secret values are never shared between context mounts.
Workspace and extra mounts exposing the global state tree are rejected.

`PI_EGRESS_GLOBAL_DIR` overrides the base directory. `PI_EGRESS_DIR` selects an
explicit standalone state directory, disabling automatic project discovery;
it is primarily useful for tests. On first use, old `~/.pi/agent/egress` state
is moved to the default base directory; an existing destination requires manual
conflict resolution. Existing recordings/keys at the base are preserved, but
new isolated contexts get their own CA and recordings. When upgrading from the
single-proxy setup, stop the old proxy first from outside a project:
`PI_EGRESS_PROJECT_ROOT= mise run pi:egress stop`.

The Pi container has only an internal network and trusts the proxy's public
CA certificate. The web listener binds to the proxy's external interface,
is published on host loopback, and requires authentication. Proxy requests
targeting that administration address are rejected even with an allow rule.
Do not share the authenticated URL printed by `pi:egress web`.

For corporate upstream certificates, set `PI_CA_CERT` to the trusted PEM CA
bundle when running `mise run pi:build`. Both images include those CAs; the
proxy retains mitmproxy's public roots and verifies upstream certificates.
Rebuild after changing the bundle. A proxy-generated 502 saying “Certificate
verify failed” indicates missing upstream trust even when curl successfully
verifies the proxy's interception certificate.

Configured secret values are replaced with placeholders in live displays,
exports and recordings. Common credential headers, such as Authorization,
Cookie and X-API-Key, are also masked unless they carry a configured placeholder.
Upstream requests retain their credentials. Recorded bodies and URLs can still
contain other sensitive data; these are not a general-purpose data scrubber.
An unconfigured credential shown as `[redacted]` is not recoverable from an
export. The web UI is a trusted local administrative interface.

`flows.mitm` rotates to `flows.mitm.1` before the next flow once it reaches
100 MiB, replacing the previous backup. A single large flow can exceed that
threshold. The live view retains up to about 2,000 completed flows, plus active
requests. View a historical recording separately on port 8082:

```sh
mise run pi:egress web --file /path/from/status/flows.mitm.1
```

This viewer does not control live requests. The proxy's custom writer handles
redaction and rotation; mitmproxy's alternative save addons are disabled in the
live proxy.

## Development

The web adapter uses APIs from the mitmproxy image pinned in `proxy/Dockerfile`.
Run the integration tests when updating that image:

```sh
docker build -t pi-less-yolo-proxy:egress-test home/dot_config/pi-less-yolo/proxy
PI_EGRESS_TEST_IMAGE=pi-less-yolo-proxy:egress-test \
  uv run --with mitmproxy==12.2.3 python -m pytest -q tests/test_pi_egress.py tests/test_pi_egress_control.py tests/test_agent_sandbox.py
```

Tests create temporary proxy/upstream containers and networks, exercise browser
APIs and shell defaults, and remove their containers and networks on completion.
They require the Pi container image to be built already. After changing the
proxy, apply its managed files and rebuild with `mise run pi:build`. The new
host helper `pi-egress-control` is installed through
`home/.chezmoiscripts/run_onchange_after_install-uv-tools.sh.tmpl` along with
the other Python CLIs.
