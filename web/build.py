# -*- coding: utf-8 -*-
"""
构建脚本：把工作台全部 markdown / json / 正文稿 打包成 web/data.js（前端内嵌加载）。
用法：python build.py
- 改完任何 .md 或正文稿后跑一次
- server.py 保存时会自动调用本脚本（实现"写盘即刷新"）
- 若存在 docs/，构建后自动同步 data.js 与 index.html（GitHub Pages 只发布 docs/）
"""
import os, json, re, sys, time, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
OUT = os.path.join(WEB, "data.js")
DOCS = os.path.join(ROOT, "docs")

# 真实项目根（规划层散文件 + 精修正文均在此，独立于工作台 ROOT）
# 可用环境变量 NOVEL_PROJECT_ROOT 覆盖；默认取「工作台根目录的同级目录 / 穿越之我是杨广」
PROJECT_ROOT = os.environ.get("NOVEL_PROJECT_ROOT") or os.path.join(
    os.path.dirname(ROOT), "穿越之我是杨广")

# 分组与排序（文件相对路径）
GROUPS = [
    ("platform", "平台总览", [
        "README.md",
        "00-流水线总览与路由.md",
        "01-题材锚定与考据清单.md",
        "02-毒士主角人物卡模板.md",
        "03-文风编码prompt模板.md",
        "04-权谋关系网与伏笔矩阵.md",
        "05-质检清单（对接自进化控制台）.md",
        "06-顶流对标·范文提炼与拆解.md",
    ]),
    ("project", "创作项目 · 规划层（精修正文配套）", [
        "01_总纲.md",
        "02_人物剧集库.md",
        "04_写作规范.md",
        "06_十卷提纲表.md",
        "07_逐章大纲_前30章.md",
        "07_逐章大纲_卷二_111-140.md",
        "11_谋略体系库.md",
    ]),
    ("benchmark", "对标基准包", [
        "benchmark/README_基准包索引.md",
        "benchmark/文风向量_最强毒士_高阳.md",
        "benchmark/ENGINE_README.md",
        "benchmark/拆解实例_最强毒士_临江平粮价.json",
        "benchmark/拆解实例_最强毒士_戏猴局.json",
        "benchmark/拆解实例_最强毒士_改良推恩令.json",
        "benchmark/拆解实例_最强毒士_贪官赈灾一石三雕.json",
        "benchmark/拆解实例_庆余年_第12章.json",
        "benchmark/engine.py",
    ]),
]

def resolve_ms_root():
    """正文源目录：优先「项目根/正文_精修版」，缺失则回退仓库自带 novel-source/。
    作者本机走精修版正稿；克隆者不改任何配置也能直接构建。"""
    primary = os.path.join(PROJECT_ROOT, "正文_精修版")
    if os.path.isdir(primary):
        return primary
    fallback = os.path.join(ROOT, "novel-source")
    if os.path.isdir(fallback):
        return fallback
    return primary


MS_ROOT = resolve_ms_root()
OUTLINE = os.path.join(PROJECT_ROOT, "07_逐章大纲_前30章.md")
OUTLINE_J2 = os.path.join(PROJECT_ROOT, "07_逐章大纲_卷二_111-140.md")
CH_RE = re.compile(r"^(\d{3})_(.+)\.md$")
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
SKIP_PREFIX = ("README", "基调样章", "_")


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def title_of(md, fallback):
    for line in md.splitlines():
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()
    return fallback


def _parse_outline_file(path):
    """解析单个细纲文件，返回 {ch: {name, point, axis, foreshadow, vol, act}}。
    支持两种格式：
    1) 管道表：| 001 | 章名 | 局点 | 轴 | 伏笔 |（旧版）
    2) 叙事版：## 第001章：章名 + - **主载事件**：… / - **伏笔**：…（当前 07_逐章大纲）"""
    if not os.path.exists(path):
        return {}
    text = read_text(path)

    # 先试管道表
    meta = {}
    vol, act = "", ""
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^##\s+(卷[^·]*·\s*[^（(]+)[（(]", s)
        if m:
            vol, act = m.group(1).strip(), ""
            continue
        m = re.match(r"^###\s+(幕[^（(]+)[（(]", s)
        if m:
            act = m.group(1).strip()
            continue
        if s.startswith("|") and s.count("|") >= 5:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 5 and re.fullmatch(r"\d{3}", cells[0]):
                meta[cells[0]] = {"name": cells[1], "point": cells[2],
                                  "axis": cells[3], "foreshadow": cells[4],
                                  "vol": vol, "act": act}
    if meta:
        return meta

    # 叙事版
    cur = None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^##\s+第(\d{3})章[：:]\s*(.+)$", s)
        if m:
            cur = m.group(1)
            meta[cur] = {"name": m.group(2).strip(), "point": "",
                         "axis": "", "foreshadow": "", "vol": "卷一", "act": ""}
            continue
        if cur:
            m = re.match(r"^-\s*\*\*([^*]+)\*\*[：:]\s*(.+)$", s)
            if m:
                k, v = m.group(1).strip(), m.group(2).strip()
                if k == "主载事件":
                    meta[cur]["point"] = v
                elif k == "伏笔":
                    meta[cur]["foreshadow"] = v
                elif k == "本章爽点":
                    meta[cur]["axis"] = v
    return meta


def parse_outline():
    """合并全部细纲文件（前30章 + 卷二111-140）为统一映射。"""
    meta = _parse_outline_file(OUTLINE)
    meta.update(_parse_outline_file(OUTLINE_J2))
    return meta


def scan_manuscript():
    """扫描正文章节文件，返回 (rels, chapters)。"""
    rels, chapters = [], []
    if not os.path.isdir(MS_ROOT):
        print("[WARN] 正文源目录不存在：%s" % MS_ROOT)
        return rels, chapters
    outline = parse_outline()
    for dirpath, dirnames, filenames in os.walk(MS_ROOT):
        # 跳过备份目录与下划线隐藏目录；卷目录名不限（卷一… / Volume1 / 任意名均可）
        dirnames[:] = sorted(d for d in dirnames if ("备份" not in d) and (not d.startswith("_")))
        vol_name = os.path.basename(dirpath) or os.path.basename(MS_ROOT)
        for fn in sorted(filenames):
            if fn.startswith(SKIP_PREFIX):
                continue
            m = CH_RE.match(fn)
            if not m:
                continue
            ab = os.path.join(dirpath, fn)
            rel = "manuscript/" + fn  # 统一逻辑键，避免跨盘相对路径
            txt = read_text(ab)
            ch = m.group(1)
            om = outline.get(ch, {})
            words = len(HAN_RE.findall(txt))
            first = ""
            for ln in txt.splitlines():
                if ln.strip() and not ln.strip().startswith("#"):
                    first = ln.strip()[:60]
                    break
            chapters.append({
                "ch": ch,
                "name": m.group(2).strip(),
                "path": rel,
                "words": words,
                "bytes": len(txt.encode("utf-8")),
                "vol": om.get("vol") or vol_name,
                "act": om.get("act") or "",
                "point": om.get("point") or "",
                "axis": om.get("axis") or "",
                "foreshadow": om.get("foreshadow") or "",
                "lead": first,
                "content": txt,
                "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(ab))),
            })
            rels.append(rel)
    chapters.sort(key=lambda x: x["ch"])
    rels.sort(key=lambda p: os.path.basename(p)[:3])
    return rels, chapters


def build():
    files, groups = {}, []
    for gid, gname, plist in GROUPS:
        base = PROJECT_ROOT if gid == "project" else ROOT
        gfiles = []
        for rel in plist:
            ab = os.path.join(base, rel.replace("/", os.sep))
            # project 组的逻辑键统一加命名空间前缀，与前端路由约定一致
            key = ("projects/穿越之我是杨广/" + rel) if gid == "project" else rel
            if not os.path.exists(ab):
                sys.stderr.write("[WARN] missing: %s\n" % rel)
                continue
            txt = read_text(ab)
            ext = os.path.splitext(rel)[1].lower()
            entry = {
                "path": key,
                "name": os.path.basename(rel),
                "ext": ext,
                "bytes": len(txt.encode("utf-8")),
                "content": txt,
            }
            if ext == ".md":
                entry["title"] = title_of(txt, os.path.splitext(os.path.basename(rel))[0])
                entry["kind"] = "md"
            elif ext == ".json":
                try:
                    obj = json.loads(txt)
                    entry["content"] = json.dumps(obj, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                entry["title"] = os.path.splitext(os.path.basename(rel))[0]
                entry["kind"] = "json"
            else:
                entry["title"] = os.path.splitext(os.path.basename(rel))[0]
                entry["kind"] = "code"
            files[key] = entry
            gfiles.append(key)
        groups.append({"id": gid, "name": gname, "files": gfiles})

    # 正文稿（content 已在 scan_manuscript 内读出，直接落 files，不再跨盘二次打开）
    ms_rels, chapters = scan_manuscript()
    ms_files = []
    for c in chapters:
        rel = c["path"]
        txt = c.pop("content")
        ch = c["ch"]
        files[rel] = {
            "path": rel,
            "name": os.path.basename(rel),
            "ext": ".md",
            "bytes": len(txt.encode("utf-8")),
            "content": txt,
            "title": "%s %s" % (ch, c.get("name") or os.path.splitext(os.path.basename(rel))[0]),
            "kind": "md",
            "chapter": ch,
        }
        ms_files.append(rel)
    if ms_files:
        vols = sorted(set(c["vol"] for c in chapters))
        vlabel = "、".join(v.split("_")[0] for v in vols)
        groups.insert(1, {"id": "manuscript",
                          "name": "正文 · %s（%d 章）" % (vlabel, len(ms_files)),
                          "files": ms_files})

    outline = parse_outline()
    total_words = sum(c["words"] for c in chapters)
    total_bytes = sum(f["bytes"] for f in files.values())
    md_bytes = sum(f["bytes"] for f in files.values() if f["kind"] == "md")
    data = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "groups": groups,
        "files": files,
        "chapters": chapters,
        "outline": outline,
        "stats": {
            "fileCount": len(files),
            "totalBytes": total_bytes,
            "mdBytes": md_bytes,
            "chapterCount": len(chapters),
            "totalWords": total_words,
            "outlineCount": len(outline),
        },
    }
    js = "/* auto-generated by build.py — do not edit */\nwindow.WB_DATA = " + \
         json.dumps(data, ensure_ascii=False, indent=1) + ";\n"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(js)
    print("OK -> %s" % OUT)
    print("正文源: %s" % MS_ROOT)
    print("files: %d, total: %.1f KB, md: %.1f KB" % (len(files), total_bytes / 1024, md_bytes / 1024))
    print("chapters: %d, words: %d, outline: %d" % (len(chapters), total_words, len(outline)))
    sync_docs()


def sync_docs():
    """把阅读器两件套同步到 docs/（GitHub Pages 只发布 docs/ 目录）。
    docs/ 不存在则跳过——是否启用 Pages 由使用者决定，不擅自建目录。"""
    if not os.path.isdir(DOCS):
        print("skip docs sync: %s 不存在（未启用 Pages）" % DOCS)
        return
    changed = []
    for name in ("data.js", "index.html"):
        src = os.path.join(WEB, name)
        dst = os.path.join(DOCS, name)
        if not os.path.isfile(src):
            continue
        if os.path.isfile(dst):
            with open(src, "rb") as fa, open(dst, "rb") as fb:
                if fa.read() == fb.read():
                    continue
        shutil.copyfile(src, dst)
        changed.append(name)
    print("docs: %s" % ("已是最新" if not changed else "已同步 " + "、".join(changed)))


if __name__ == "__main__":
    build()
