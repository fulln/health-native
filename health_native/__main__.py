"""Loopback-only, read-only HealthNative server."""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfoNotFoundError

from . import __version__
from .reader import HealthReader, default_data_dirs


class Handler(BaseHTTPRequestHandler):
    server_version = "HealthNative/" + __version__

    def _allowed(self):
        if len(self.headers.get_all("Host", [])) != 1:
            return False
        try:
            host = urlsplit("http://" + self.headers["Host"])
            if (host.hostname not in ("127.0.0.1", "localhost") or
                    (host.port or 80) != self.server.server_port or
                    host.username or host.password or host.path or host.query or host.fragment):
                return False
        except ValueError:
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {
                "http://127.0.0.1:%d" % self.server.server_port,
                "http://localhost:%d" % self.server.server_port}:
            return False
        return self.headers.get("Sec-Fetch-Site", "none") in ("same-origin", "none")

    def _send(self, code, body=b"", content_type="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; "
                         "style-src 'self'; img-src 'self' data:; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if content_type == "application/octet-stream":
            self.send_header("Content-Disposition",
                             'attachment; filename="HealthNativeDated.shortcut"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        self._dispatch()

    def do_HEAD(self):
        self._dispatch()

    def _dispatch(self):
        if not self._allowed():
            self._send(403, b"forbidden")
            return
        try:
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc:
                self._send(400, b"invalid request target")
                return
            if parsed.path == "/api/health":
                if parsed.query:
                    self._send(400, b"API parameters are not supported")
                    return
                payload = self.server.reader.read()
                self._send(200, json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(),
                           "application/json; charset=utf-8")
                return
            relative = unquote(parsed.path, errors="strict").lstrip("/") or "index.html"
            if relative.startswith("api/") or "\\" in relative or "\x00" in relative:
                self._send(404, b"not found")
                return
            root = self.server.web_dir.resolve()
            target = (root / relative).resolve()
            if root not in target.parents or not target.is_file():
                self._send(404, b"not found")
                return
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type == "application/javascript":
                content_type += "; charset=utf-8"
            self._send(200, target.read_bytes(), content_type)
        except (OSError, ValueError, UnicodeError):
            self._send(500, b"Local files could not be read; refresh after iCloud sync.")

    def do_POST(self):
        self._send(405, b"read-only")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST

    def log_message(self, *_):
        # Do not write user file names or health records to request logs.
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="HealthNative local iCloud dashboard")
    parser.add_argument("--data-dir", action="append", help="Read-only data directory; repeat to merge")
    parser.add_argument("--port", type=int, default=8764)
    parser.add_argument("--timezone", default="Asia/Shanghai", help="IANA timezone used for daily grouping")
    parser.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    if not 1 <= options.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        reader = HealthReader(options.data_dir or default_data_dirs(), options.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        parser.error("unknown timezone")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", options.port), Handler)
    except OSError:
        parser.error("port unavailable; use --port to choose another local port")
    server.reader = reader
    server.web_dir = Path(__file__).resolve().parents[1] / "web"
    print("HealthNative: http://127.0.0.1:%d/dashboard.html" % server.server_port, flush=True)
    print("Read-only local data. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
