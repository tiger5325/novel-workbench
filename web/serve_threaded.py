# -*- coding: utf-8 -*-
"""静态文件服务（多线程，避免单连接阻塞）。

与 server.py 的区别：本脚本只托管静态文件，不含 /api/save 写盘接口。
默认只绑 127.0.0.1:8771（server.py 用 8770，两者可同时开）。
确需给局域网设备看，再显式加 --host 0.0.0.0——那会把你本机目录暴露到局域网。

用法：
  <python> serve_threaded.py [--host 127.0.0.1] [--port 8771] [--dir web]
"""
import argparse
import http.server
import os
import socketserver

WEB_DIR = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 静默


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1", help="绑定地址，默认仅本机")
    ap.add_argument("--port", type=int, default=8771, help="端口，默认 8771")
    ap.add_argument("--dir", default=None, help="托管目录，默认本脚本所在目录")
    args = ap.parse_args()

    root = os.path.abspath(args.dir) if args.dir else WEB_DIR
    if not os.path.isdir(root):
        raise SystemExit("目录不存在：%s" % root)
    os.chdir(root)

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("⚠ 绑定 %s：本目录将对局域网可见，确认这是你要的" % args.host)

    with socketserver.ThreadingTCPServer((args.host, args.port), Handler) as httpd:
        httpd.daemon_threads = True
        print("Serving %s on http://%s:%d" % (root, args.host, args.port), flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
