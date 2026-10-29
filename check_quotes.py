#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, os

dir_path = r"F:\F05_Projects_Hub\穿越之我是杨广\正文_精修版\卷一_龙潜于渊"
f = os.path.join(dir_path, "001_三更火起刀未落.md")

with open(f, encoding='utf-8') as fp:
    text = fp.read()

ascii_dq = len(re.findall(r'"', text))
ascii_sq = len(re.findall(r"'", text))
cn_dq_open = text.count('“')
cn_dq_close = text.count('”')

print(f"ASCII双引号: {ascii_dq}")
print(f"ASCII单引号: {ascii_sq}")
print(f"中文左双引号: {cn_dq_open}")
print(f"中文右双引号: {cn_dq_close}")

# 找出ASCII双引号的位置
if ascii_dq > 0:
    matches = list(re.finditer(r'"', text))[:5]
    for m in matches:
        start = max(0, m.start()-20)
        end = min(len(text), m.end()+20)
        print(f"  位置{m.start()}: ...{text[start:end]}...")
