# Pi container egress

Open a shell, then open its network controls from a second terminal:

```sh
mise run pi:shell
mise run pi:egress web
```

`pi:shell` defaults to interactive egress filtering, HTTPS inspection for all
hosts, and HTTP flow recording. Unknown hosts wait for approval and are denied
after 60 seconds. Provider endpoints detected from credentials and the npm
registry are allowed automatically. Explicit deny rules take precedence.

The web command opens an authenticated approval page. Choose Allow/Deny once,
for the session, or always. Persistent browser decisions apply to the exact
host and port. “Open live traffic” opens mitmweb in another tab, with live
requests, native interception, editing, resume and replay. Destination rules
and credential scopes are checked after request edits. The approval page can
be opened before any traffic or recordings exist. `pi:egress watch` remains
available for terminal approvals.

All shells share one proxy. Session decisions last until `pi:egress stop` or a
proxy restart; each new Pi task updates the shared configuration and active
secret scopes. Placeholder identities survive subsequent launches. Opening
the web UI preserves an existing configuration. Closing the browser does not
stop filtering or recording.

## Overrides

```sh
PI_EGRESS_RECORD=0 mise run pi:shell       # disable disk recording
PI_EGRESS_INSPECT= mise run pi:shell       # tunnel HTTPS, except active secret scopes
PI_EGRESS=allowlist mise run pi:shell      # deny unknown hosts without prompting
PI_EGRESS= mise run pi:shell               # disable the proxy entirely
```

`PI_EGRESS_RECORD=1` enables recording; `0` disables it. Recording and TLS
inspection are separate: without inspection, HTTPS bodies cannot be recorded.
Other Pi tasks retain their opt-in behavior. Persist settings with `pi-config`
or the project's mise environment. `PI_EGRESS_WEB_PORT` changes the host web
port (default 8081). `PI_LOCAL_MODELS` requires disabling egress explicitly
because host networking bypasses the internal network.

Uncompressed server-sent events stream incrementally and are recorded when the
response completes. Compressed event streams are buffered for body redaction.

## State, credentials and recordings

Proxy state lives in `~/.local/state/pi-egress`, outside the mounted Pi agent
directory. On first use, existing `~/.pi/agent/egress` state is moved there;
rules, the CA and recordings are preserved. If both directories already exist,
resolve that conflict before launching. `PI_EGRESS_DIR` overrides the location.
Workspace and extra mounts exposing the state directory are rejected.

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
mise run pi:egress web --file ~/.local/state/pi-egress/flows.mitm.1
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
  uv run --with mitmproxy==12.2.3 pytest -q tests/test_pi_egress.py
```

Tests create temporary proxy/upstream containers and networks, exercise browser
APIs and shell defaults, and remove their containers and networks on completion.
They require the Pi container image to be built already. After changing the
proxy, apply its managed files and rebuild with `mise run pi:build`.
