"""Live mitmweb with authenticated approvals and sanitized display copies.

The small web-handler adapter is tied to the mitmproxy image pinned in Dockerfile.
The underlying live flows remain available for native editing/resume/replay.
"""

import os
from pathlib import Path
import socket
import sys
import time

from mitmproxy.tools import cmdline, main
from mitmproxy.tools.web import app
from mitmproxy.tools.web.master import WebMaster
from mitmproxy.addons import export

from pi_egress import DECISIONS_DIR, PENDING_DIR, STATE_DIR, PiEgress, load_policy

ASSETS = Path(__file__).parent


class Approvals(app.RequestHandler):
    def get(self) -> None:  # ty: ignore[invalid-method-override]
        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.write(
            (ASSETS / "approvals.html")
            .read_text()
            .replace("XSRF_TOKEN", self.xsrf_token.decode())
        )


class ApprovalScript(app.RequestHandler):
    def get(self) -> None:  # ty: ignore[invalid-method-override]
        self.set_header("Content-Type", "text/javascript")
        self.write((ASSETS / "approvals.js").read_text())


class Pending(app.RequestHandler):
    def get(self) -> None:  # ty: ignore[invalid-method-override]
        policy = load_policy()
        requests = []
        for path in sorted(Path(PENDING_DIR).iterdir()):
            if path.is_file() and not (Path(DECISIONS_DIR) / path.name).exists():
                requests.append(
                    dict(
                        id=path.name,
                        target=path.read_text().strip(),
                        expires=path.stat().st_mtime + policy.timeout_s,
                    )
                )
        self.write(dict(requests=requests, mode=policy.mode, record=policy.record))


class Decision(app.RequestHandler):
    def post(self, request_id) -> None:  # ty: ignore[invalid-method-override]
        path = Path(PENDING_DIR) / request_id
        if not path.is_file() or (Path(DECISIONS_DIR) / request_id).exists():
            raise app.APIError(409, "Request expired or already answered")
        choice = self.json.get("choice")
        if choice not in (
            "allow",
            "deny",
            "allow-session",
            "deny-session",
            "allow-always",
            "deny-always",
        ):
            raise app.APIError(400, "Unknown decision")
        if time.time() >= path.stat().st_mtime + load_policy().timeout_s:
            raise app.APIError(409, "Request expired")
        if choice.endswith("-always"):
            choice = choice.split("-")[0]
            with open(Path(STATE_DIR) / f"rules.{choice}", "a") as rules:
                rules.write(path.read_text())
        (Path(DECISIONS_DIR) / request_id).write_text(choice)
        self.write(dict(ok=True))


class EgressMaster(WebMaster):
    def __init__(self, opts):
        super().__init__(opts)
        self.egress = PiEgress()
        # Last: native browser interception and edits precede policy checks
        # and injection. Display handlers always sanitize independent copies.
        self.addons.add(self.egress)
        redact = self.egress.redacted_copy
        original_json = app.flow_to_json

        def safe_json(flow):
            result = original_json(redact(flow))
            result["modified"] = flow.modified()
            return result

        setattr(app, "flow_to_json", safe_json)
        original_flow = app.RequestHandler.flow.fget
        setattr(
            app.RequestHandler,
            "flow",
            property(
                lambda handler: (
                    redact(original_flow(handler))
                    if handler.request.method == "GET"
                    else original_flow(handler)
                )
            ),
        )
        for name, formatter in export.formats.items():
            export.formats[name] = lambda flow, formatter=formatter: formatter(
                redact(flow)
            )
        # These built-in writers bypass our redaction/rotation policy.
        for name in ("save", "savehar"):
            self.addons.remove(self.addons.get(name))

        class SafeDump(app.DumpFlows):
            @property
            def view(handler):
                view = handler.master.view
                return (
                    [redact(flow) for flow in view]
                    if handler.request.method == "GET"
                    else view
                )

        self.app.add_handlers(
            r".*",
            [
                (r"/flows/dump", SafeDump),
                (r"/egress", Approvals),
                (r"/egress/app.js", ApprovalScript),
                (r"/egress/pending", Pending),
                (r"/egress/decision/([0-9a-f]{16})", Decision),
            ],
        )

    async def running(self):
        await super().running()
        url = self.web_url.replace("/?", "/egress?")
        Path(STATE_DIR, "web-url").write_text(url + "\n")
        os.chmod(Path(STATE_DIR, "web-url"), 0o600)


if __name__ == "__main__":
    # Selecting a route sends no packets. Only the external interface has a
    # default route; binding there keeps the listener off the internal network.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
        route.connect(("192.0.2.1", 9))
        web_host = route.getsockname()[0]
    os.environ["PI_EGRESS_WEB_HOST"] = web_host
    main.run(
        EgressMaster,
        cmdline.mitmweb,
        [
            *sys.argv[1:],
            "--web-host",
            web_host,
            "--web-port",
            "8081",
            "--set",
            "web_open_browser=false",
        ],
    )
