#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能网文小说创作工作台 · 顶流对标原生引擎
=========================================
把「小说连载工坊」的 文风提炼 + 拆解模仿 方法论，原生实现为本工作台自有能力。
不再需要登录任何远程 app，也不再需要在浏览器里点按钮。

用法（两种模式）：
  1) 自动模式（需配置 LLM 后端）：
       export LLM_BASE="https://your-endpoint/v1"
       export LLM_KEY="sk-xxxx"
       export LLM_MODEL="gpt-4o-mini"   # 或任意 OpenAI 兼容模型
       python engine.py --fanwen path/to/范文.md --name "最强毒士" --out .
  2) 手动模式（无 API 也能用）：
       python engine.py --fanwen path/to/范文.md --manual
     → 脚本打印「文风提炼 prompt」和「拆解 prompt」，你贴进任意 AI 对话，
       把返回结果存成 md/json，脚本负责归档到 benchmark/。

产出：
  - benchmark/文风向量_<name>.md
  - benchmark/拆解实例_<name>_<seg>.json  （每个片段一个）
"""

import argparse
import json
import os
import sys

# ───────────────────────── 提示词（源自 06 模块，已融合） ─────────────────────────

STYLE_EXTRACT_PROMPT = """请对以下顶流范文做「文风特征提取」，按 6 个维度输出结构化标签：

{text}

要求：
1. 叙事视角 / 语言节奏 / 心理描写 / 智斗铺陈 / 留白反讽 / 禁用气质 —— 每维给 1 句定性 + 1 个原文例句佐证；
2. 标注「毒士向可迁移度」：哪些维度本项目(穿越毒士爽文)可直接借用，哪些需改造；
3. 输出「文风向量」(6 维打分 0~10) + 3 条「可迁移语言铁律」；
4. 输出 Markdown 格式，文风向量用表格呈现。"""

DISSECT_PROMPT = """请对以下范文片段做「通读拆解」，聚焦 5 层，输出 JSON：

{text}

JSON 结构（务必合法可解析）：
{{
  "source": "{name}",
  "segment": "片段标识",
  "structure": {{ "起": "", "承": "", "转": "", "合": "" }},
  "character_moves": [
    "主角动作：算计/留后手的具体描写",
    "对手反应：未被降智的证据"
  ],
  "hook": "章末钩子原文或改写",
  "tension": "高/中/低",
  "reusable_skill": "本段可模仿的 1 个技法（只记怎么写，不记写了什么）"
}}

只拆技法，不抄剧情（红线）。"""


# ───────────────────────── LLM 调用（OpenAI 兼容） ─────────────────────────

def call_llm(prompt: str) -> str:
    base = os.environ.get("LLM_BASE")
    key = os.environ.get("LLM_KEY")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    if not (base and key):
        raise RuntimeError("未配置 LLM_BASE / LLM_KEY，请改用 --manual 模式。")
    try:
        import urllib.request
        import ssl
        req = urllib.request.Request(
            base.rstrip("/") + "/chat/completions",
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            }).encode("utf-8"),
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa
        raise RuntimeError(f"LLM 调用失败：{e}")


# ───────────────────────── 主流程 ─────────────────────────

def read_fanwen(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def manual_mode(name: str, text: str, out: str):
    os.makedirs(out, exist_ok=True)
    print("=" * 70)
    print("【手动模式】把下面两段 prompt 分别贴进任意 AI 对话，")
    print("把返回结果存为：")
    print(f"  - {out}/文风向量_{name}.md")
    print(f"  - {out}/拆解实例_{name}_<片段>.json")
    print("=" * 70)
    print("\n----- 文风提炼 prompt -----\n")
    print(STYLE_EXTRACT_PROMPT.format(text=text[:8000]))
    print("\n----- 拆解 prompt -----\n")
    print(DISSECT_PROMPT.format(text=text[:8000], name=name))
    print("\n（如需拆分多片段，请自行按片段分别跑拆解 prompt。）")


def auto_mode(name: str, text: str, out: str):
    os.makedirs(out, exist_ok=True)
    print(f"[engine] 跑文风提炼（{name}）...")
    style_md = call_llm(STYLE_EXTRACT_PROMPT.format(text=text[:8000]))
    sp = os.path.join(out, f"文风向量_{name}.md")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(f"# 文风向量 · {name}\n\n> 由 engine.py 自动跑出（{name}）\n\n")
        f.write(style_md)
    print(f"[engine] 已写 {sp}")

    print(f"[engine] 跑拆解（{name}）...")
    dissect = call_llm(DISSECT_PROMPT.format(text=text[:8000], name=name))
    # 尝试从返回里捞 JSON
    try:
        j = json.loads(dissect[dissect.find("{"): dissect.rfind("}") + 1])
        jp = os.path.join(out, f"拆解实例_{name}_auto.json")
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(j, f, ensure_ascii=False, indent=2)
        print(f"[engine] 已写 {jp}")
    except Exception:
        dp = os.path.join(out, f"拆解实例_{name}_auto.md")
        with open(dp, "w", encoding="utf-8") as f:
            f.write(dissect)
        print(f"[engine] 拆解返回非标准 JSON，已存为 {dp}（请人工整理为 json）")


def main():
    ap = argparse.ArgumentParser(description="顶流对标原生引擎")
    ap.add_argument("--fanwen", required=True, help="范文文件路径（.md/.txt）")
    ap.add_argument("--name", default="顶流样本", help="样本名，用于产出文件名")
    ap.add_argument("--out", default=".", help="产出目录，默认当前目录")
    ap.add_argument("--manual", action="store_true", help="手动模式：只打印 prompt")
    args = ap.parse_args()

    text = read_fanwen(args.fanwen)
    if args.manual:
        manual_mode(args.name, text, args.out)
    else:
        try:
            auto_mode(args.name, text, args.out)
        except RuntimeError as e:
            print(f"[engine] {e}", file=sys.stderr)
            print("[engine] 已切换到手动模式，打印 prompt：\n", file=sys.stderr)
            manual_mode(args.name, text, args.out)


if __name__ == "__main__":
    main()
