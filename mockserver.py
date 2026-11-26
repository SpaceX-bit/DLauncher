"""Мини-HTTP-сервер для тестов + подмена внешних адресов.

    srv = MockServer()
    srv.route('GET', '/mc/manifest.json', json={'a': 1})
    srv.route('GET', '/file.bin', body=b'...')
    srv.route('POST', '/token', json=lambda req: {...})     # req: dict(method, path, query, headers, body)
    srv.route('GET', '/x', status=404)
    srv.map_host('https://api.modrinth.com', prefix='/modrinth')  # https://api.modrinth.com/v2/x -> /modrinth/v2/x
    ... srv.stop()
"""
import json as _json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dlauncher.core import util


class MockServer:
    def __init__(self):
        self.routes = {}
        self.hosts = {}
        self.log = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _do(self):
                u = urllib.parse.urlparse(self.path)
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                req = {"method": self.command, "path": u.path, "query": dict(urllib.parse.parse_qsl(u.query)),
                       "headers": dict(self.headers), "body": body}
                outer.log.append(req)
                r = outer.routes.get((self.command, u.path)) or outer.routes.get(("*", u.path))
                if r is None:
                    self.send_response(404); self.end_headers(); self.wfile.write(b"not found"); return
                status = r.get("status", 200)
                if "json" in r:
                    j = r["json"](req) if callable(r["json"]) else r["json"]
                    data = _json.dumps(j).encode()
                    ctype = "application/json"
                elif "body" in r:
                    data = r["body"](req) if callable(r["body"]) else r["body"]
                    ctype = r.get("ctype", "application/octet-stream")
                else:
                    data = b""; ctype = "text/plain"
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                for k, v in r.get("headers", {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_DELETE = _do

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        util.set_rewrite(self._rewrite)

    def route(self, method, path, **kw):
        self.routes[(method, path)] = kw

    def map_host(self, origin, prefix=""):
        self.hosts[origin.rstrip("/")] = prefix

    def _rewrite(self, url):
        for origin, prefix in self.hosts.items():
            if url.startswith(origin):
                return self.base + prefix + url[len(origin):]
        return url

    def stop(self):
        util.set_rewrite(None)
        self.httpd.shutdown()
        self.httpd.server_close()
