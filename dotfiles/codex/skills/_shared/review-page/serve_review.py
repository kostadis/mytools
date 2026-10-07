#!/usr/bin/env python3
"""Serve one Codex review page and save its decisions on the VM.

The random URL is a capability: the server exposes no directory listing and
accepts writes only to the configured decisions file. It is intended for a
Tailscale tailnet or another trusted private network, not the public internet.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from read_decisions import DecisionError, normalize

MAX_BODY = 2 * 1024 * 1024
HOSTED_MARKER = b'<meta name="codex-review-save" content="enabled">'


@dataclass(frozen=True)
class ReviewConfig:
    page: Path
    items: Path
    output: Path
    token: str
    spec: dict

    @property
    def base_path(self) -> str:
        return f"/r/{self.token}/"


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


class Handler(BaseHTTPRequestHandler):
    server_version = "codex-review/1"

    @property
    def config(self) -> ReviewConfig:
        return self.server.review_config  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: object) -> None:
        if self.command != "GET":
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(
            status,
            (json.dumps(payload, ensure_ascii=True) + "\n").encode("utf-8"),
            "application/json",
        )

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == self.config.base_path:
            try:
                page = self.config.page.read_bytes()
            except OSError as exc:
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            if b"</head>" not in page:
                return self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "review page has no </head> marker"},
                )
            page = page.replace(b"</head>", HOSTED_MARKER + b"</head>", 1)
            return self._send(HTTPStatus.OK, page, "text/html")
        if path == self.config.base_path.rstrip("/"):
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", self.config.base_path)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_PUT(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path != self.config.base_path + "decisions":
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid Content-Length"})
        if length <= 0 or length > MAX_BODY:
            return self._json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE if length > MAX_BODY else HTTPStatus.BAD_REQUEST,
                {"error": f"request body must be 1-{MAX_BODY} bytes"},
            )
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            normalized = normalize(payload, self.config.spec)
        except (json.JSONDecodeError, UnicodeError) as exc:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": f"unreadable JSON: {exc}"})
        except DecisionError as exc:
            return self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
        try:
            atomic_write(self.config.output, normalized)
        except OSError as exc:
            return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"cannot save: {exc}"})
        self._json(HTTPStatus.OK, {
            "saved": str(self.config.output),
            "decided": normalized["decided"],
        })


def make_server(config: ReviewConfig, host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), partial(Handler))
    server.review_config = config  # type: ignore[attr-defined]
    return server


def tailscale_ip() -> str | None:
    if not shutil.which("tailscale"):
        return None
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True,
            timeout=2, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()), None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", required=True, type=Path, help="generated review HTML")
    parser.add_argument("--items", required=True, type=Path, help="review_items JSON used to build it")
    parser.add_argument("--out", required=True, type=Path, help="exact decisions JSON destination")
    parser.add_argument("--host", default="0.0.0.0", help="bind address (default: all interfaces)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    try:
        page = args.page.expanduser().resolve(strict=True)
        items = args.items.expanduser().resolve(strict=True)
        spec = json.loads(items.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    output = args.out.expanduser().resolve()
    config = ReviewConfig(page, items, output, secrets.token_urlsafe(18), spec)
    server = make_server(config, args.host, args.port)
    port = server.server_address[1]
    address = tailscale_ip()
    if not address:
        address = args.host if args.host not in {"0.0.0.0", "::"} else socket.gethostname()
    print(f"Review URL: http://{address}:{port}{config.base_path}", flush=True)
    print(f"Saves to:   {output}", flush=True)
    print("Keep this terminal open while reviewing. Intended for a tailnet or trusted LAN.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
