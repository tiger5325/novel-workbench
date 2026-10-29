#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
引号体检：统计 ASCII 直引号 / 直角引号「」/ 弯引号配对情况，并给出问题位置。

用法：
  <python> check_quotes.py [路径 ...] [--only-bad]
路径可为 .md 文件或目录（目录递归扫 .md）。
不给参数时扫仓库自带的 novel-source/（克隆者开箱可用）。
退出码：0 = 全部干净，1 = 发现问题。
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def default_targets():
    for name in ("novel-source", "正文_精修版"):
        p = os.path.join(HERE, name)
        if os.path.isdir(p):
            return [p]
    return [HERE]


def collect(paths):
    out = []
    for p in paths:
        if os.path.isfile(p):
            out.append(p)
        elif os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames[:] = sorted(d for d in dirnames
                                     if not d.startswith("_") and "备份" not in d)
                for fn in sorted(filenames):
                    if fn.endswith(".md"):
                        out.append(os.path.join(dirpath, fn))
        else:
            sys.stderr.write("[skip] 不存在：%s\n" % p)
    return out


def scan(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return {
        "ascii_dq": len(re.findall(r'"', text)),
        "ascii_sq": len(re.findall(r"'", text)),
        "corner": len(re.findall(r"[「」]", text)),
        "cn_open": text.count("\u201c"),
        "cn_close": text.count("\u201d"),
        "_text": text,
    }


def positions(text, pattern, limit=3, width=20):
    out = []
    for m in list(re.finditer(pattern, text))[:limit]:
        s = max(0, m.start() - width)
        e = min(len(text), m.end() + width)
        out.append("第%d字符 …%s…" % (m.start(), text[s:e].replace("\n", " ")))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="要检查的 .md 文件或目录")
    ap.add_argument("--only-bad", action="store_true", help="只列出有问题的文件")
    args = ap.parse_args()

    targets = collect(args.paths or default_targets())
    if not targets:
        print("未找到 .md 文件")
        return 1

    bad_files = 0
    total = {"ascii_dq": 0, "ascii_sq": 0, "corner": 0, "unpaired": 0}

    for p in targets:
        try:
            r = scan(p)
        except Exception as e:
            print("[错误] %s: %s" % (p, e))
            bad_files += 1
            continue
        unpaired = r["cn_open"] != r["cn_close"]
        opened_sq = r["ascii_sq"] % 2
        problems = []
        if r["ascii_dq"]:
            problems.append("ASCII双引号 %d 处" % r["ascii_dq"])
        if r["ascii_sq"]:
            problems.append("ASCII单引号 %d 处%s" % (r["ascii_sq"], "（奇数，疑似未闭合）" if opened_sq else ""))
        if r["corner"]:
            problems.append("直角引号「」%d 处" % r["corner"])
        if unpaired:
            problems.append("弯引号不成对（“ %d / ” %d）" % (r["cn_open"], r["cn_close"]))

        total["ascii_dq"] += r["ascii_dq"]
        total["ascii_sq"] += r["ascii_sq"]
        total["corner"] += r["corner"]
        total["unpaired"] += 1 if unpaired else 0

        if not problems:
            if not args.only_bad:
                print("[OK]   %s" % os.path.relpath(p, HERE))
            continue

        bad_files += 1
        print("[问题] %s" % os.path.relpath(p, HERE))
        for msg in problems:
            print("       - %s" % msg)
        if r["ascii_dq"]:
            for loc in positions(r["_text"], r'"'):
                print("         %s" % loc)
        if r["corner"]:
            for loc in positions(r["_text"], r"[「」]"):
                print("         %s" % loc)

    print("\n扫描 %d 个文件：干净 %d，有问题 %d" % (len(targets), len(targets) - bad_files, bad_files))
    print("合计 ASCII双引号 %d ｜ ASCII单引号 %d ｜ 直角引号 %d ｜ 弯引号不成对 %d 个文件"
          % (total["ascii_dq"], total["ascii_sq"], total["corner"], total["unpaired"]))
    return 1 if bad_files else 0


if __name__ == "__main__":
    sys.exit(main())
