import http.server, functools, os
class H(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, p):
        p = super().translate_path(p)
        if os.path.isdir(p): return os.path.join(p, "index.html")
        if not os.path.exists(p) and os.path.exists(p + ".html"): return p + ".html"
        return p
http.server.HTTPServer(("127.0.0.1", 8765), functools.partial(H, directory=os.path.join(os.path.dirname(__file__), "site"))).serve_forever()
