# -*- coding: utf-8 -*-
"""多线程HTTP服务器，避免单连接阻塞。"""
import http.server, socketserver, os, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(WEB_DIR)

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 静默

with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print("Serving %s on port %d" % (WEB_DIR, PORT), flush=True)
    httpd.serve_forever()
