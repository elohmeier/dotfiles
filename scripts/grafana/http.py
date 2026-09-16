from __future__ import annotations

import ssl

import httpx
import rich_click as click

from .common import REQUEST_EXTENSIONS


def client(
    url: str,
    token: str | None,
    username: str | None,
    password: str | None,
    host: str | None,
    sni_hostname: str | None,
    verify: bool,
    timeout: float,
    ca_file: str | None = None,
) -> httpx.Client:
    if token and (username is not None or password is not None):
        raise click.UsageError("--token cannot be combined with basic authentication")
    if (username is None) != (password is None):
        raise click.UsageError(
            "basic authentication requires both --username and --password"
        )
    auth = (
        httpx.BasicAuth(username, password)
        if username is not None and password is not None
        else None
    )
    REQUEST_EXTENSIONS.clear()
    if sni_hostname:
        REQUEST_EXTENSIONS["sni_hostname"] = sni_hostname
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if host:
        headers["Host"] = host
    return httpx.Client(
        base_url=url.rstrip("/"),
        headers=headers,
        auth=auth,
        verify=ssl.create_default_context(cafile=ca_file)
        if verify and ca_file
        else verify,
        timeout=timeout,
    )
