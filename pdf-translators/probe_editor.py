#!/usr/bin/env python3
"""probe_editor.py — diagnostic client for the markdown_editor (or any of the
sibling Flask UIs). Hits each endpoint and reports a per-phase timing breakdown
so you can see *where* "slow" actually is: TCP connect, server think time
(time-to-first-byte), or body transfer.

Usage:
    python3 probe_editor.py                       # default http://127.0.0.1:5107
    python3 probe_editor.py --port 5107
    python3 probe_editor.py --host 127.0.0.1 --port 5107 --file ~/markdown.md
    python3 probe_editor.py --url http://127.0.0.1:5107 --repeat 3

Pure stdlib (http.client) — no external deps, so it runs anywhere the server does.
"""
from __future__ import annotations

import argparse
import http.client
import os
import sys
import time
from urllib.parse import quote, urlsplit


def probe(host: str, port: int, path: str, timeout: float = 30.0) -> dict:
    """Make one GET and time each phase separately.

    Phases:
      connect : open the TCP socket to the server
      ttfb    : send request → first byte of the response (server think time)
      read    : stream the rest of the body to completion (transfer time)
    """
    result: dict = {"path": path}
    t0 = time.perf_counter()
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.connect()
        t_connect = time.perf_counter()

        conn.request("GET", path)
        resp = conn.getresponse()
        # Reading 1 byte forces the server to have produced the status line +
        # headers + at least the first body byte → true time-to-first-byte.
        first = resp.read(1)
        t_ttfb = time.perf_counter()

        rest = resp.read()
        t_done = time.perf_counter()

        body_len = len(first) + len(rest)
        result.update(
            status=resp.status,
            ctype=resp.getheader("Content-Type", "?"),
            bytes=body_len,
            connect_ms=(t_connect - t0) * 1000,
            ttfb_ms=(t_ttfb - t_connect) * 1000,
            read_ms=(t_done - t_ttfb) * 1000,
            total_ms=(t_done - t0) * 1000,
        )
    except Exception as e:  # noqa: BLE001 — diagnostic tool, report anything
        result.update(error=f"{type(e).__name__}: {e}",
                      total_ms=(time.perf_counter() - t0) * 1000)
    finally:
        conn.close()
    return result


def fmt(r: dict) -> str:
    if "error" in r:
        return f"  {r['path']:<28} ERROR after {r['total_ms']:7.1f}ms  {r['error']}"
    return (f"  {r['path']:<28} {r['status']}  "
            f"{r['bytes']:>8} B  "
            f"connect={r['connect_ms']:6.1f}  "
            f"ttfb={r['ttfb_ms']:7.1f}  "
            f"read={r['read_ms']:7.1f}  "
            f"total={r['total_ms']:7.1f}ms  "
            f"[{r['ctype'].split(';')[0]}]")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=None,
                   help="Base URL (overrides --host/--port), e.g. http://127.0.0.1:5107")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5107)
    p.add_argument("--file", default=None,
                   help="Path to probe via /api/load (defaults to ~/markdown.md if present)")
    p.add_argument("--repeat", type=int, default=1,
                   help="Probe each endpoint N times (to see warm-vs-cold variance)")
    args = p.parse_args(argv)

    if args.url:
        u = urlsplit(args.url)
        host = u.hostname or "127.0.0.1"
        port = u.port or 5107
    else:
        host, port = args.host, args.port

    load_file = args.file or os.path.expanduser("~/markdown.md")
    endpoints = ["/", "/bootstrap.min.css"]
    if load_file and os.path.exists(os.path.expanduser(load_file)):
        endpoints.append("/api/load?file=" + quote(os.path.expanduser(load_file)))

    print(f"Probing http://{host}:{port}  (file={load_file})")
    print(f"{'─' * 100}")
    any_err = False
    for rep in range(args.repeat):
        if args.repeat > 1:
            print(f"pass {rep + 1}/{args.repeat}")
        for ep in endpoints:
            r = probe(host, port, ep)
            any_err = any_err or ("error" in r)
            print(fmt(r))
    print(f"{'─' * 100}")
    print("Reading the columns:")
    print("  connect high → network/socket setup is the cost (WSL2 bridge, firewall).")
    print("  ttfb    high → the SERVER is slow producing the response (Python handler).")
    print("  read    high → body transfer is the cost (large payload over a slow link).")
    return 1 if any_err else 0


if __name__ == "__main__":
    sys.exit(main())
