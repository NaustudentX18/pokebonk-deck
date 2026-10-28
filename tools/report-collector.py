#!/usr/bin/env python3
"""Collect a hardware-verification report from the Steam Deck.

The Deck posts the output of tools/deck-verify.sh here so the results can be
read back without the user having to copy and paste anything.

    python3 tools/report-collector.py --port 8100 --out /data/deck-reports

Endpoints:
    POST /report   body is the report text; stored as <out>/<timestamp>.txt
    GET  /         lists the stored reports
    GET  /latest   prints the newest report
"""

from __future__ import annotations

import argparse
import datetime
import http.server
import json
import os
import pathlib
import socketserver
import sys


class Handler(http.server.BaseHTTPRequestHandler):
    out_dir: pathlib.Path = pathlib.Path("/tmp")

    def _send(self, code: int, body: str, content_type="text/plain; charset=utf-8"):
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/report":
            self._send(404, "not found\n")
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace")
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.out_dir / f"deck-report-{stamp}.txt"
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        except OSError as error:
            self._send(500, f"could not store the report: {error}\n")
            return
        print(f"[collector] stored {target} ({len(body)} bytes)", flush=True)
        self._send(200, f"stored {target.name}\n")

    def do_GET(self):  # noqa: N802
        path = self.path.rstrip("/") or "/"
        if path == "/":
            reports = sorted(self.out_dir.glob("deck-report-*.txt"))
            listing = "\n".join(r.name for r in reports) or "(none yet)"
            self._send(200, listing + "\n")
            return
        if path == "/latest":
            reports = sorted(self.out_dir.glob("deck-report-*.txt"))
            if not reports:
                self._send(404, "no reports yet\n")
                return
            self._send(200, reports[-1].read_text(encoding="utf-8"))
            return
        if path == "/health":
            self._send(200, "ok\n", "application/json")
            return
        self._send(404, "not found\n")

    def log_message(self, fmt, *args):
        sys.stderr.write("[collector] " + (fmt % args) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--out", default="/data/deck-reports")
    args = parser.parse_args()

    Handler.out_dir = pathlib.Path(args.out)
    Handler.out_dir.mkdir(parents=True, exist_ok=True)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((args.bind, args.port), Handler) as server:
        print(f"[collector] listening on {args.bind}:{args.port}, storing in {Handler.out_dir}",
              flush=True)
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
