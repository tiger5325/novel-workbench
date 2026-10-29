# -*- coding: utf-8 -*-
"""
智能网文小说创作工作台 · 本地服务（实时模式）
- 静态托管 web/ 目录
- GET  /api/ping     探测（前端据此判断能否直写磁盘）
- GET  /api/version  返回 data.js 版本戳（前端轮询，实现"谁改了都能实时看到"）
- POST /api/save     {path, content} → 写回真实文件（自动 .bak 备份）+ 重建 data.js

写回路径约定：
  - "manuscript/NNN_章名.md" 是阅读器里的逻辑键，映射到真实正文源里的同名文件；
    找不到就报错，不新建——避免散落孤儿副本。
  - 其余相对路径按工作台根解析，且限定在根目录内、只允许内容类扩展名。

安全边界（本服务只为本机单人使用设计）：
  - 默认只绑 127.0.0.1
  - 写接口要求 application/json + 自定义头 X-WB-Client（跨源网页发不出自定义头，
    预检拿不到 CORS 响应 → 等价于同源校验），并校验 Host 防 DNS rebinding
  - 路径用 commonpath 校验；不写代码类文件（.py/.js/.html）

用法：
  <python> server.py [端口]
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

# 只允许写内容类文件：代码与前端资源必须走编辑器，防止在线编辑面变成后门
WRITABLE_EXT = {".md", ".markdown", ".txt", ".json"}
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

CTYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


def inside(path, base):
    """path 是否真在 base 之内（commonpath 判定，挡掉 web_x/ 这类前缀绕过）。"""
    try:
        return os.path.commonpath([os.path.abspath(path),
                                   os.path.abspath(base)]) == os.path.abspath(base)
    except (ValueError, OSError):
        return False


def project_root():
    """正文项目根：NOVEL_PROJECT_ROOT → 工作台同级中带「正文_精修版」的目录 → 工作台根。"""
    env = os.environ.get("NOVEL_PROJECT_ROOT")
    if env and os.path.isdir(env):
        return env
    if os.path.isdir(os.path.join(ROOT, "正文_精修版")):
        return ROOT
    parent = os.path.dirname(ROOT)
    try:
        for name in sorted(os.listdir(parent)):
            cand = os.path.join(parent, name)
            if os.path.isdir(os.path.join(cand, "正文_精修版")):
                return cand
    except OSError:
        pass
    return ROOT


def corpora():
    """候选正文源目录（按优先级）。"""
    out = []
    for cand in (os.path.join(project_root(), "正文_精修版"),
                 os.path.join(ROOT, "novel-source")):
        if os.path.isdir(cand):
            out.append(cand)
    return out


def resolve_target(rel):
    """逻辑键 → 真实文件绝对路径。返回 (abs_path, err)。"""
    rel = (rel or "").replace("\\", "/").strip().lstrip("/")
    if not rel:
        return None, "empty path"

    if rel.startswith("manuscript/"):
        fn = rel.split("/", 1)[1]
        if "/" in fn or not fn.endswith(".md"):
            return None, "bad chapter key"
        hits = []
        for base in corpora():
            try:
                vols = sorted(os.listdir(base))
            except OSError:
                continue
            for vol in vols:
                p = os.path.join(base, vol, fn)
                if os.path.isfile(p):
                    hits.append(p)
        if not hits:
            return None, "章节文件不存在：%s（不新建，避免散落孤儿副本）" % fn
        if len(hits) > 1:
            return None, "存在同名异稿 %d 份，拒绝写入：%s" % (
                len(hits), "；".join(os.path.relpath(h, project_root()) for h in hits))
        return hits[0], None

    fp = os.path.normpath(os.path.join(ROOT, rel.replace("/", os.sep)))
    if not inside(fp, ROOT):
        return None, "forbidden"
    if os.path.splitext(fp)[1].lower() not in WRITABLE_EXT:
        return None, "该类型文件不支持在线保存（仅限 %s）" % "、".join(sorted(WRITABLE_EXT))
    return fp, None


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

    def _host_ok(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0] or ""
        return host.lower() in ALLOWED_HOSTS

    def _write_guard(self):
        """写接口放行条件；返回 None 表示通过，否则返回拒绝原因。"""
        if not self._host_ok():
            return "host not allowed"
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return "requires application/json"
        if self.headers.get("X-WB-Client") != "workbench":
            return "missing X-WB-Client header"
        origin = self.headers.get("Origin")
        if origin:
            o = urlparse(origin)
            if (o.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
                return "cross-origin rejected"
        return None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/ping":
            return self._send(200, json.dumps({"ok": True, "mode": "server",
                                               "projectRoot": project_root()}))
        if path == "/api/version":
            return self._send(200, json.dumps({"ok": True, "v": version_stamp()}))
        if path == "/":
            path = "/index.html"
        fp = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not inside(fp, WEB):
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

        denied = self._write_guard()
        if denied:
            return self._send(403, json.dumps({"ok": False, "err": denied}))

        ln = int(self.headers.get("Content-Length", "0") or 0)
        if ln <= 0 or ln > 32 * 1024 * 1024:
            return self._send(400, json.dumps({"ok": False, "err": "bad content length"}))
        raw = self.rfile.read(ln).decode("utf-8", "replace")
        try:
            obj = json.loads(raw)
        except Exception:
            return self._send(400, json.dumps({"ok": False, "err": "bad json"}))
        content = obj.get("content", "")
        if not isinstance(content, str):
            return self._send(400, json.dumps({"ok": False, "err": "content must be string"}))

        fp, err = resolve_target(obj.get("path"))
        if err:
            code = 403 if err in ("forbidden",) else 400
            return self._send(code, json.dumps({"ok": False, "err": err}))

        try:
            parent = os.path.dirname(fp)
            if not os.path.isdir(parent):
                return self._send(400, json.dumps(
                    {"ok": False, "err": "目标目录不存在，拒绝新建目录：%s" % parent}))
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    old = f.read()
                with open(fp + ".bak", "wb") as f:
                    f.write(old)
            tmp = fp + ".tmp-save"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            os.replace(tmp, fp)
            rebuild()
            return self._send(200, json.dumps({"ok": True, "path": os.path.relpath(fp, ROOT),
                                               "v": version_stamp()}))
        except Exception as e:
            return self._send(500, json.dumps({"ok": False, "err": str(e)}))

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    rebuild()
    print("工作台服务启动： http://127.0.0.1:%d" % PORT)
    print("正文项目根： %s" % project_root())
    print("（Ctrl+C 停止）")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
