#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量清洗格式硬伤：ASCII 直引号 → 中文弯引号、整行 --- 分隔线 → 删除、阿拉伯数字 → 汉字数字。

默认 **dry-run**：只报告将要改什么，不写盘。
确认无误后加 --apply 才真改，且每个文件先存 .bak。

用法：
  <python> batch_clean.py [路径 ...]              # 预览
  <python> batch_clean.py [路径 ...] --apply      # 落盘（自动 .bak）
  <python> batch_clean.py --apply --no-digits     # 只处理引号与分隔线
不给路径时扫仓库自带的 novel-source/。
"""
import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIGITS = "零一二三四五六七八九"


def cn_num(s):
    """把 0–9999 的整数字符串转成汉字数字；超出范围或含前导零则原样返回。"""
    if not s.isdigit() or (len(s) > 1 and s[0] == "0"):
        return s
    n = int(s)
    if n > 9999:
        return s
    if n == 0:
        return "零"
    units = [(1000, "千"), (100, "百"), (10, "十")]
    out, zero = "", False
    rest = n
    for base, name in units:
        q, rest = divmod(rest, base)
        if q:
            if zero and out:
                out += "零"
            out += (DIGITS[q] if q > 1 else ("十" if name == "十" else "一")) + name
            zero = False
        elif out:
            zero = True
    if rest:
        if zero and out:
            out += "零"
        out += DIGITS[rest]
    return out or "零"


def convert_quotes(text):
    """成对替换 ASCII 双引号为中文弯引号。"""
    out, in_quote = [], False
    for ch in text:
        if ch == '"':
            out.append("\u201d" if in_quote else "\u201c")
            in_quote = not in_quote
        else:
            out.append(ch)
    return "".join(out)


def remove_separators(text):
    """删除独立成行的 --- 分隔线（不做全局字符串替换，避免伤及正文内容）。"""
    return re.sub(r"(?m)^[ \t]*---+[ \t]*\r?\n?", "", text)


def convert_digits(text):
    """阿拉伯数字 → 汉字数字。只在「数词」语境替换：连续数字整体转，不逐位拆。"""
    return re.sub(r"\d+", lambda m: cn_num(m.group(0)), text)


def clean_text(text, do_digits=True):
    t = convert_quotes(text)
    t = remove_separators(t)
    if do_digits:
        t = convert_digits(t)
    return t


def diff_summary(old, new):
    items = []
    dq = len(re.findall(r'"', old))
    if dq:
        items.append("直引号 %d 处" % dq)
    sep = len(re.findall(r"(?m)^[ \t]*---+[ \t]*$", old))
    if sep:
        items.append("分隔线 %d 行" % sep)
    nd = len(re.findall(r"\d+", old))
    if nd:
        items.append("数字 %d 处" % nd)
    return items


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


def default_targets():
    for name in ("novel-source", "正文_精修版"):
        p = os.path.join(HERE, name)
        if os.path.isdir(p):
            return [p]
    return [HERE]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="要清洗的 .md 文件或目录")
    ap.add_argument("--apply", action="store_true", help="真正写盘（默认只预览）")
    ap.add_argument("--no-digits", action="store_true", help="跳过阿拉伯数字转换")
    args = ap.parse_args()

    targets = collect(args.paths or default_targets())
    if not targets:
        print("未找到 .md 文件")
        return 1

    do_digits = not args.no_digits
    print("%s：%d 个文件（数字转换：%s）"
          % ("落盘模式" if args.apply else "预览模式（不改盘，加 --apply 才写）",
             len(targets), "开" if do_digits else "关"))

    changed = 0
    for p in targets:
        try:
            with open(p, encoding="utf-8") as f:
                old = f.read()
            new = clean_text(old, do_digits)
            if new == old:
                continue
            changed += 1
            rel = os.path.relpath(p, HERE)
            print("  %s  ← %s" % (rel, "、".join(diff_summary(old, new)) or "内容变化"))
            if args.apply:
                shutil.copyfile(p, p + ".bak")
                with open(p, "w", encoding="utf-8", newline="\n") as f:
                    f.write(new)
        except Exception as e:
            print("  [错误] %s: %s" % (p, e))

    print("\n%s：%d/%d 个文件%s"
          % ("已改写（原文件存 .bak）" if args.apply else "待改",
             changed, len(targets), "" if args.apply else "，确认无误后加 --apply"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
