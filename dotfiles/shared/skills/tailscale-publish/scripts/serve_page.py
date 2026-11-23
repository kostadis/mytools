#!/usr/bin/env python3
"""Serve one local file at a Tailscale-only capability URL."""

from __future__ import annotations

import argparse
import mimetypes
import secrets
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


class Handler(BaseHTTPRequestHandler):
    server_version = "codex-tailscale-page/1"

    def log_message(self, fmt: str, *args: object) -> None:
        if self.command != "GET":
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        base_path = self.server.base_path  # type: ignore[attr-defined]
        if path == base_path.rstrip("/"):
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", base_path)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path != base_path:
            self._send(HTTPStatus.NOT_FOUND, b"not found\n", "text/plain; charset=utf-8")
            return
        page = self.server.page  # type: ignore[attr-defined]
        try:
            body = page.read_bytes()
        except OSError as exc:
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"cannot read page: {exc}\n".encode("utf-8"),
                "text/plain; charset=utf-8",
            )
            return
        content_type = mimetypes.guess_type(page.name)[0] or "application/octet-stream"
        if content_type.startswith("text/"):
            content_type += "; charset=utf-8"
        self._send(HTTPStatus.OK, body, content_type)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", required=True, type=Path)
    parser.add_argument("--host", required=True, help="exact Tailscale IPv4 address")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    page = args.page.expanduser().resolve(strict=True)
    if not page.is_file():
        parser.error(f"not a file: {page}")

    token = secrets.token_urlsafe(18)
    base_path = f"/p/{token}/"
    server = ThreadingHTTPServer((args.host, args.port), partial(Handler))
    server.page = page  # type: ignore[attr-defined]
    server.base_path = base_path  # type: ignore[attr-defined]
    port = server.server_address[1]

    print(f"Page URL: http://{args.host}:{port}{base_path}", flush=True)
    print(f"Serving:  {page}", flush=True)
    print("Keep this terminal open while the page is published.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
