# -*- coding: utf-8 -*-
"""
智能网文小说创作工作台 · 本地服务（实时模式）
- 静态托管 web/ 目录
- /api/ping     探测（前端据此判断能否直写磁盘）
- /api/version  返回 data.js 版本戳（前端轮询，实现"谁改了都能实时看到"）
- /api/save     POST {path, content} → 写回项目文件（自动 .bak 备份）+ 重建 data.js
用法：
  F:/F03_Deps_Hub/Python_Local/bin/python.exe server.py [端口]
默认 http://127.0.0.1:8770
"""
import os, sys, json, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

WEB = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(WEB)
DATA_JS = os.path.join(WEB, "data.js")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
BUILD = os.path.join(WEB, "build.py")

CTYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


def rebuild():
    subprocess.run([sys.executable, BUILD], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def version_stamp():
    try:
        st = os.stat(DATA_JS)
        return "%d-%d" % (int(st.st_mtime), st.st_size)
    except OSError:
        return "0-0"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/ping":
            return self._send(200, json.dumps({"ok": True, "mode": "server"}))
        if path == "/api/version":
            return self._send(200, json.dumps({"ok": True, "v": version_stamp()}))
        if path == "/":
            path = "/index.html"
        fp = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not fp.startswith(WEB):
            return self._send(403, "forbidden")
        if os.path.isfile(fp):
            ext = os.path.splitext(fp)[1].lower()
            with open(fp, "rb") as f:
                data = f.read()
            return self._send(200, data, CTYPES.get(ext, "application/octet-stream"))
        return self._send(404, "not found")

    def do_POST(self):
        if urlparse(self.path).path != "/api/save":
            return self._send(404, "not found")
        ln = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(ln).decode("utf-8", "replace")
        try:
            obj = json.loads(raw)
        except Exception:
            return self._send(400, json.dumps({"ok": False, "err": "bad json"}))
        rel = (obj.get("path") or "").strip()
        content = obj.get("content", "")
        if not rel:
            return self._send(400, json.dumps({"ok": False, "err": "empty path"}))
        fp = os.path.normpath(os.path.join(ROOT, rel.replace("/", os.sep)))
        if not fp.startswith(ROOT):
            return self._send(403, json.dumps({"ok": False, "err": "forbidden"}))
        try:
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    old = f.read()
                with open(fp + ".bak", "wb") as f:
                    f.write(old)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            rebuild()
            return self._send(200, json.dumps({"ok": True, "v": version_stamp()}))
        except Exception as e:
            return self._send(500, json.dumps({"ok": False, "err": str(e)}))

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    rebuild()
    print("工作台服务启动： http://127.0.0.1:%d" % PORT)
    print("（Ctrl+C 停止）")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
