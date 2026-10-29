#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
质控机检脚本 · 智能网文小说创作工作台 v4
========================================
对「卷01 现行稿」逐章做【确定性】机检，不依赖任何 LLM / 远程技能，可无人值守运行。

v1 硬闸（全章适用，口径：projects/穿越之我是杨广/写作规范.md）：
  - 首行「# 七字章名」单标题行，标题七汉字，标题与文件名一致
  - 纯汉字字数 2600–3200
  - 禁 ASCII 直引号 / 直角引号「」；弯引号须成对
  - 禁阿拉伯数字（数字全汉字）
  - 禁违禁词：太极宫/太极殿/GDP/KPI/系统/互联网/蒸汽机/供应链/杠杆/鉴真/郑和/贾岛/近代火炮
  - 禁格式元素：小标题(#)/加粗(**)/分隔线(---)/列表(* -)
  - 跨章重复段落（≥25 汉字的段落全文比对）

v2 内容闸（仅对 --baseline 之后的新章生效；冻结章不追溯）：
  - 岁数直报（「十六岁」等；「三岁一易」制度语豁免）
  - 章内重复段落（≥10 汉字且出现≥2次）
  - 公式化措辞超限（原以为/没想到/愣了一下/说不出话/他知道/他明白/
    他清楚/叹了口气/深吸一口气/眉头一皱/心里一沉，单句上限各一；
    六项核心句合计上限三）
  - 章末套话（末八段出现「因为他是杨广/这是他的使命/越来越好」等）
  - 现代词（奶酪/蛋糕/起跑线/钢印/复盘/闭环…）
  - 人名错写（杨谦/杨先 → 杨谅）
  - 告警不判未过：短段占比过高、章末碎段堆叠、章内整句重复≥3次、软现代词

v4 增补（2026-10-29）：
  - 公式句只计叙述段（引号内台词另计为告警，不扣闸）
  - 二批「动作代偿型套话」九组：静场/停顿/半晌/看一眼/轻笑/指节指尖/喉头/没说话/「不是…是…」
  - 文风密度观测：段均/句均/台词句均/叙述句均/短句占比/对话占比，
    对标 benchmark/文风向量_最强毒士_高阳.md §5.1 范文实测带；只观测，不判未过
  - 句子统计过滤 0 汉字残片（收引号不单独成句），修 2026-10-29 查出的口径污染

v4 变更（2026-10-29 · 对标实测后收紧；闸门只对新章生效）：
  1. 公式句改为**只计叙述段**（以「“」起头的对话段不计入硬闸），对话内命中另报为告警。
     依据：对话里说「我知道」是人物口吻，不是作者套话；001–164 清洗后残余的 15 处全在台词内。
  2. 新增二批公式句（**动作代偿型套话**）：静了一息／顿了顿／半晌／看了他一眼／
     笑了一下／指节指尖／喉头／没说话／不是…是…。实测我方每章密度是范文的 5–14 倍
     （范文 10 章「不是…是…」仅 2 次＝0.2/章，我方 001–180 均 2.83/章）。
  3. 新增**文风密度告警**（不判未过）：句均、短句≤10 占比、段均、对话占比，
     按 `benchmark/文风向量_最强毒士_高阳.md` §五 的范文区间给提示。

产物：
  - projects/.../正文_重写稿/_生产/机检审校报告.md
  - projects/.../正文_重写稿/_生产/qc_audit_state.json

用法：
  python qc_audit.py [--root <项目根>] [--deep-seeded <已深度全维审校章数>]
                     [--baseline 164] [--strict]
退出码：默认 0（报告性质）；--strict 且有未过章时返回 1。
"""
import argparse
import os
import re
import json
import sys
import datetime
from collections import Counter

HAN = re.compile(r'[\u4e00-\u9fff]')
ASCII_QUOTE = re.compile(r'["\']')
CORNER = re.compile(r'[「」]')
ARABIC = re.compile(r'[0-9]')
FILENAME = re.compile(r'^(\d{3})_(.+)\.md$')
AGE = re.compile(r'([一二三四五六七八九十两]{1,3})岁(?!一易)')
QUOTED = re.compile(r'“[^”]*”')
# v4.1（2026-10-29）：月份/节气只做告警——场景锚点够用即可，堆成历书没人看
DATE_WORD = re.compile(
    r'正月|二月|三月|四月|五月|六月|七月|八月|九月|十月|十一月|十二月|腊月|冬月|'
    r'立春|雨水|惊蛰|春分|清明|谷雨|立夏|小满|芒种|夏至|小暑|大暑|'
    r'立秋|处暑|白露|秋分|寒露|霜降|立冬|小雪|大雪|冬至|小寒|大寒|'
    r'元日|上元|寒食|端午|七夕|中秋|重阳|除夕')
# 数据罗列：单句内「数词+量词」≥3 个，才算账目式铺陈（「三百人、二十车」式）
DATA_UNIT = re.compile(
    r'[一二三四五六七八九十百千万两]+'
    r'(?:人|骑|车|乘|石|斗|贯|文|钱|顷|亩|户|口|名|具|束|幅|瓮|箱|艘|面|处|所|座|间|匹|头|只|领|副|张|件|升|斤)')

BANNED = ['太极宫', '太极殿', 'GDP', 'KPI', '系统', '互联网', '蒸汽机',
          '供应链', '杠杆', '鉴真', '郑和', '贾岛', '近代火炮']

MODERN_HARD = ['奶酪', '蛋糕', '起跑线', '钢印', '公司', '董事长',
               '签字权', '付款权', '绩效', '第二选项', '管理层', '复盘', '闭环',
               '政策红利', '全员通告', '新老板', '总裁', '业绩', '风险点']
MODERN_WARN = ['底线', '赋能', '赛道', '颗粒度',
               '底层逻辑', '考核', '指标', '认知', '信息差', '用户', '产品']

NAME_TYPO = ['杨谦', '杨先']

FORMULA = {
    '原以为': 1, '没想到': 1, '愣了一下': 1, '说不出话': 1,
    '他知道': 1, '他也知道': 1, '他明白': 1, '他清楚': 1,
    '叹了口气': 1, '深吸一口气': 1, '眉头一皱': 1, '心里一沉': 1,
    '因为他是杨广': 0, '大隋的皇帝': 1, '一件一件': 1,
    '不能马虎': 0, '不敢马虎': 0, '这是他的使命': 0, '也是他的宿命': 0,
    '越来越好': 1, '不急': 1, '但不停': 0, '一步一步': 1,
}

# 六项合计上限：单句各一次也可能凑成一段套话，故另设合闸
FORMULA_CORE = ['他知道', '他也知道', '原以为', '没想到', '愣了一下', '说不出话']
FORMULA_CORE_CAP = 3

# v4 二批公式句：动作代偿型套话（用固定小动作替代具体观察）。
# 组名 -> (变体列表, 单章上限)。只统计叙述段，对话段不计入。
# 定标依据：benchmark §5.1 十篇范文实测，这些短语密度近零（0–1.1/章），
# 我方 001–180 却有 0.2–2.8/章 —— 差距最大的是「不是…是…」14 倍。
FORMULA2 = {
    '静场': (['静了一息', '静了一静', '沉默了一息', '沉默片刻'], 1),
    '停顿': (['顿了顿', '停了一停'], 1),
    '半晌': (['半晌'], 1),
    '看一眼': (['看了他一眼', '看了她一眼', '看了他们一眼', '看了一眼'], 1),
    '轻笑': (['笑了一下', '笑了一声', '笑了笑'], 2),
    '指节指尖': (['指节', '指尖'], 2),
    '喉头': (['喉头', '喉咙'], 1),
    '没说话': (['没说话', '没接话', '没有接话', '没有出声', '没出声'], 1),
    '不是是': (['不是'], 3),   # 用 NOT_A_B 正则单独计数，见 count_not_a_b
}
# 「不是…是…」对举：单句内出现「不是」与「，是」/「。是」的对照结构
NOT_A_B = re.compile(r'不是[^。！？；]{1,20}[，。]是')

# 文风密度参考带（benchmark §5.1 范文实测·10 章干净口径；仅供告警，不判未过）
# 2026-10-29 重定标：旧带 (13.0,18.5)/(30%,50%)/(20,29) 出自含 0 汉字残片的脏口径，作废。
STYLE_BAND = {
    'sent_avg': (18.5, 25.0),      # 句均汉字（范文 19.0–23.0，均值 20.5）
    'dialogue_avg': (16.5, 30.0),  # 台词句均（范文 18.6–27.3，均值 22.5）
    'narr_avg': (18.0, 26.0),      # 叙述句均（范文 19.0–24.5，均值 21.2）
    'short_sent': (0.15, 0.34),    # 短句≤10 汉字占比（范文 19.0–31.5%）
    'para_avg': (18.0, 25.0),      # 段均汉字（范文 18.9–23.2）
    'dialogue': (0.05, 0.48),      # 对话占比（范文 8.0–43.2%，场景变量）
}

END_MARKS = ['因为他是杨广', '大隋的皇帝', '这是他的使命', '也是他的宿命',
             '不能马虎', '不敢马虎', '一件一件', '一步一步', '但不停',
             '他要让这个天下', '这就是他要做的事']

EXCLUDE = re.compile(r'(README|说明|样章)')

# v5（2026-10-29）：路径指向真实精修版稿位（项目从工作台projects/迁出到F05_Hub根）
# v6（2026-10-29）：跨全部卷目录扫描（卷一/卷二/…），跳过备份目录
CORPUS_DIR = r'F:\F05_Projects_Hub\穿越之我是杨广\正文_精修版'
CHAPTER_DIR_REL = CORPUS_DIR   # 兼容旧报错文案
PROD_DIR_REL = r'F:\F05_Projects_Hub\穿越之我是杨广\_工单与报告\机检报告'


def chapter_files(root):
    files = []
    if not os.path.isdir(CORPUS_DIR):
        return files
    for vol in sorted(os.listdir(CORPUS_DIR)):
        vd = os.path.join(CORPUS_DIR, vol)
        if not os.path.isdir(vd) or ('备份' in vol) or vol.startswith('_'):
            continue
        for fn in sorted(os.listdir(vd)):
            if fn.endswith('.md') and not EXCLUDE.search(fn):
                files.append(os.path.join(vd, fn))
    return files


def paragraphs(text):
    return [p.strip() for p in text.split('\n') if p.strip()]


def check(path, baseline=0):
    """返回 (字汉字数, hard_issues, warnings, metrics)"""
    with open(path, encoding='utf-8') as f:
        text = f.read()
    lines = text.split('\n')
    paras = paragraphs(text)
    issues = []
    warns = []
    num = None
    m = FILENAME.match(os.path.basename(path))
    if m:
        num = int(m.group(1))
    is_new = num is not None and num > baseline

    # 首行标题
    first = lines[0] if lines else ''
    if not first.startswith('# '):
        issues.append('首行非「# 章名」格式')
    else:
        title = first[2:].strip()
        if '#' in title:
            issues.append('章名行含多余 #')
        tc = len(HAN.findall(title))
        if tc != 7:
            if num is not None and num > baseline:
                issues.append('标题非七字(%d)' % tc)
            else:
                warns.append('标题非七字(%d)，冻结章不追溯' % tc)
        if m and title != m.group(2):
            issues.append('标题与文件名不一致')

    # 字数
    hancount = len(HAN.findall(text))
    if hancount < 2600:
        issues.append('字数不足(%d<2600)' % hancount)
    elif hancount > 3200:
        issues.append('字数超限(%d>3200)' % hancount)

    # 引号
    if ASCII_QUOTE.search(text):
        issues.append('含ASCII直引号')
    if CORNER.search(text):
        issues.append('含直角引号「」')
    dq = text.count('“') + text.count('”')
    if dq % 2 != 0:
        issues.append('弯引号不成对')

    # 阿拉伯数字
    if ARABIC.search(text):
        issues.append('含阿拉伯数字')

    # 违禁词
    hit = [w for w in BANNED if w in text]
    if hit:
        issues.append('违禁词:' + ','.join(hit))

    # 格式禁用元素（跳过首行）
    for i, ln in enumerate(lines):
        if i == 0:
            continue
        s = ln.strip()
        if not s:
            continue
        if s.startswith('#'):
            issues.append('含小标题/分节(#)')
        elif s.startswith('**'):
            issues.append('含加粗(**)')
        elif s.startswith('---'):
            issues.append('含分隔线(---)')
        elif s.startswith('* ') or s.startswith('- '):
            issues.append('含列表(*/-)')

    metrics = {'paras': len(paras), 'short_ratio': 0.0, 'tail_avg': 0.0,
               'han': hancount, 'sent_avg': 0.0, 'short_sent': 0.0,
               'para_avg': 0.0, 'dialogue': 0.0,
               'dialogue_avg': 0.0, 'narr_avg': 0.0}
    if paras:
        short = sum(1 for p in paras[1:] if len(HAN.findall(p)) < 20)
        denom = max(1, len(paras) - 1)
        metrics['short_ratio'] = short / denom
        tail = paras[-20:]
        metrics['tail_avg'] = sum(len(HAN.findall(p)) for p in tail) / max(1, len(tail))
        metrics['para_avg'] = hancount / len(paras)
        dq_han = sum(len(HAN.findall(p)) for p in paras if p.startswith('“'))
        metrics['dialogue'] = dq_han / max(1, hancount)
        # 句＝按 。！？； 切分；⛔ 只认汉字数>0 的片段——否则「。”」这类
        # 收引号残片会以 0 汉字“句子”入场，把句均压低约两成、短句率抬高十点
        # （2026-10-29 实测：脏口径曾误判我方句均 11 vs 范文 16）。
        sents = []
        for p in paras:
            for s in re.split(r'(?<=[。！？；])', p):
                n = len(HAN.findall(s))
                if n:
                    sents.append(n)
        if sents:
            metrics['sent_avg'] = sum(sents) / len(sents)
            metrics['short_sent'] = sum(1 for x in sents if x <= 10) / len(sents)
        body = '\n'.join(paras)
        dq = [len(HAN.findall(s))
              for s in re.split(r'(?<=[。！？；])', ' '.join(QUOTED.findall(body)))
              if len(HAN.findall(s))]
        nr = [len(HAN.findall(s))
              for s in re.split(r'(?<=[。！？；])', QUOTED.sub('', body))
              if len(HAN.findall(s))]
        if dq:
            metrics['dialogue_avg'] = sum(dq) / len(dq)
        if nr:
            metrics['narr_avg'] = sum(nr) / len(nr)

    if not is_new:
        return hancount, issues, warns, metrics

    # ---- v4 内容闸（仅新章） ----
    # 岁数
    ages = [a + '岁' for a in AGE.findall(text)]
    if ages:
        issues.append('报岁数:' + ','.join(ages[:5]))

    # 章内重复段落
    norm = [re.sub(r'\s+', '', p) for p in paras if len(HAN.findall(p)) >= 10]
    dup_in = {k: v for k, v in Counter(norm).items() if v > 1}
    if dup_in:
        sample = list(dup_in.items())[:2]
        issues.append('章内重复段%d处(如「%s」×%d)' %
                      (len(dup_in), sample[0][0][:14], sample[0][1]))

    # ---- 公式化措辞（v4：只计叙述段；引号内台词另计为告警）----
    narr = QUOTED.sub('', text)
    over = []
    dlg_hits = []
    for w, cap in FORMULA.items():
        c = narr.count(w)
        if c > cap:
            over.append('%s×%d(上限%d)' % (w, c, cap))
        d = text.count(w) - c
        if d:
            dlg_hits.append('%s×%d' % (w, d))
    core_sum = sum(narr.count(w) for w in FORMULA_CORE)
    if core_sum > FORMULA_CORE_CAP:
        over.append('六项合计×%d(上限%d)' % (core_sum, FORMULA_CORE_CAP))
    for name, (variants, cap) in FORMULA2.items():
        if name == '不是是':
            continue
        c = sum(narr.count(v) for v in variants)
        if c > cap:
            over.append('%s×%d(上限%d)' % (name, c, cap))
    nab = len(NOT_A_B.findall(narr))
    if nab > 3:
        over.append('不是…是…×%d(上限3)' % nab)
    if over:
        issues.append('公式化:' + ','.join(over))
    if dlg_hits:
        warns.append('台词内公式句(不扣闸):' + ','.join(dlg_hits[:6]))

    # 章末套话
    tail_txt = ''.join(paras[-8:]) if len(paras) >= 8 else ''.join(paras)
    end_hit = [w for w in END_MARKS if w in tail_txt]
    if end_hit:
        issues.append('章末套话:' + ','.join(end_hit[:4]))

    # 现代词
    mh = [w for w in MODERN_HARD if w in text]
    if mh:
        issues.append('现代词:' + ','.join(mh))
    mw = [w for w in MODERN_WARN if w in text]
    if mw:
        warns.append('软现代词:' + ','.join(mw))

    # 人名错写
    nt = [w for w in NAME_TYPO if w in text]
    if nt:
        issues.append('人名错写:' + ','.join(nt))

    # ---- 告警（不判未过） ----
    # 「短段占比≥42%」告警已撤销（2026-10-29）：范文实测短段(<20汉字)占 51%–61%，
    # 均值 56%——该阈值是在拆句数碎片时定的，会把对标范文的正常分段判成病。
    # v4 文风密度告警（对标 benchmark §5.1 范文区间）
    lo, hi = STYLE_BAND['sent_avg']
    if metrics['sent_avg'] and not (lo <= metrics['sent_avg'] <= hi):
        warns.append('句均%.1f(范文%.0f–%.0f)' % (metrics['sent_avg'], lo, hi))
    lo, hi = STYLE_BAND['dialogue_avg']
    if metrics['dialogue_avg'] and not (lo <= metrics['dialogue_avg'] <= hi):
        warns.append('台词句均%.1f(范文%.1f–%.1f；过短＝台词被打成碎句)' %
                     (metrics['dialogue_avg'], lo, hi))
    lo, hi = STYLE_BAND['narr_avg']
    if metrics['narr_avg'] and not (lo <= metrics['narr_avg'] <= hi):
        warns.append('叙述句均%.1f(范文%.0f–%.0f)' %
                     (metrics['narr_avg'], lo, hi))
    lo, hi = STYLE_BAND['short_sent']
    if metrics['short_sent'] and metrics['short_sent'] > hi:
        warns.append('短句≤10占%.0f%%(范文≤%.0f%%)' %
                     (metrics['short_sent'] * 100, hi * 100))
    lo, hi = STYLE_BAND['para_avg']
    if metrics['para_avg'] and not (lo <= metrics['para_avg'] <= hi):
        warns.append('段均%.1f(范文%.0f–%.0f)' % (metrics['para_avg'], lo, hi))
    # 月份/节气与数据罗列：只告警，不扣闸（2026-10-29 Boss 口径：
    # 「别再列举数据，用谋略布局才有吸引力」——密度超标先提示，改法靠判例）
    d = len(DATE_WORD.findall(text))
    if d > 3:
        warns.append('月份/节气%d处(>3，场景锚点够用即可)' % d)
    dense = [s for s in re.split(r'(?<=[。！？；])', text)
             if len(DATA_UNIT.findall(s)) >= 3]
    if len(dense) > 2:
        warns.append('数据列举句%d句(>2，单句≥3个数量词)' % len(dense))
    if metrics['tail_avg'] < 18 and len(paras) >= 20:
        warns.append('章末二十段均长%.1f字(<18)' % metrics['tail_avg'])
    sents = [re.sub(r'\s+', '', s) for s in re.split(r'[。！？…]', text)]
    sents = [s for s in sents if len(HAN.findall(s)) >= 8]
    rep = {k: v for k, v in Counter(sents).items() if v >= 3}
    if rep:
        k0 = max(rep, key=rep.get)
        warns.append('整句重复%d处(如「%s」×%d)' % (len(rep), k0[:12], rep[k0]))

    return hancount, issues, warns, metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument('--deep-seeded', type=int, default=None,
                    help='已做过深度全维审校的章数')
    ap.add_argument('--baseline', type=int, default=0,
                    help='该章号及以前为冻结章，不套用 v2 内容闸')
    ap.add_argument('--strict', action='store_true',
                    help='有未过章时返回 1')
    args = ap.parse_args()

    files = chapter_files(args.root)
    if not files:
        print('未找到章节文件，检查路径：', CHAPTER_DIR_REL)
        return 1

    results = []
    for p in files:
        hc, issues, warns, metrics = check(p, args.baseline)
        results.append((os.path.basename(p), hc, issues, warns, metrics))

    # 跨章重复段落（≥25 汉字）
    all_paras = []
    for p in files:
        with open(p, encoding='utf-8') as f:
            txt = f.read()
        for para in txt.split('\n'):
            para = para.strip()
            if len(HAN.findall(para)) >= 25:
                all_paras.append((os.path.basename(p), para))
    cnt = Counter(p[1] for p in all_paras)
    dups = {k: v for k, v in cnt.items() if v > 1}

    # 章号连续性 + 标题重复
    nums = []
    titles = []
    for fn, _, _, _, _ in results:
        m = FILENAME.match(fn)
        if m:
            nums.append(int(m.group(1)))
            titles.append(m.group(2))
    gaps = []
    for a, b in zip(nums, nums[1:]):
        if b != a + 1:
            gaps.append('%03d→%03d' % (a, b))
    dup_titles = [k for k, v in Counter(titles).items() if v > 1]

    # 状态追踪
    prod = os.path.join(args.root, PROD_DIR_REL)
    os.makedirs(prod, exist_ok=True)
    state_path = os.path.join(prod, 'qc_audit_state.json')
    prev = {}
    if os.path.exists(state_path):
        try:
            prev = json.load(open(state_path, encoding='utf-8'))
        except Exception:
            prev = {}
    prev_files = set(prev.get('audited_files', []))
    cur_files = set(r[0] for r in results)
    new_files = sorted(cur_files - prev_files)

    deep_seeded = prev.get('deep_seeded')
    if args.deep_seeded is not None:
        deep_seeded = args.deep_seeded
    if deep_seeded is None:
        deep_seeded = prev.get('deep_seeded', 0)
    deep_backlog = max(0, len(cur_files) - deep_seeded)

    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    passed = [r for r in results if not r[2]]
    failed = [r for r in results if r[2]]
    warned = [r for r in results if r[3]]

    md = []
    md.append('# 机检审校报告（确定性 v4）\n')
    md.append('> 生成时间：%s　｜　范围：卷01 现行稿全 %d 章　｜　口径：写作规范.md 硬闸\n'
              % (now, len(results)))
    md.append('## 一、总览\n')
    md.append('| 项 | 数值 |')
    md.append('|---|---:|')
    md.append('| 章数 | %d |' % len(results))
    md.append('| 机检通过 | %d |' % len(passed))
    md.append('| 机检未过 | %d |' % len(failed))
    md.append('| 有告警 | %d |' % len(warned))
    md.append('| 跨章重复段 | %d |' % len(dups))
    md.append('| 待深度全维审校 | %d 章（已深度 %d） |' % (deep_backlog, deep_seeded))
    md.append('| 本次新增未覆盖章 | %d |' % len(new_files))
    md.append('| v4 内容闸基线 | 第 %d 章及以前豁免 |' % args.baseline)
    md.append('')
    md.append('## 二、未过章明细\n')
    if failed:
        md.append('| 章文件 | 字数 | 问题 |')
        md.append('|---|---:|---|')
        for fn, hc, iss, _, _ in failed:
            md.append('| %s | %d | %s |' % (fn, hc, '；'.join(iss)))
    else:
        md.append('全部通过。\n')
    md.append('\n## 三、告警明细（不判未过）\n')
    if warned:
        md.append('| 章文件 | 告警 |')
        md.append('|---|---|')
        for fn, _, _, ws, _ in warned:
            md.append('| %s | %s |' % (fn, '；'.join(ws)))
    else:
        md.append('无。\n')
    md.append('\n## 四、跨章重复段落\n')
    if dups:
        for para, c in dups.items():
            md.append('- 出现 %d 次：%s…' % (c, para[:40]))
    else:
        md.append('无。')
    md.append('\n## 五、结构与连续性\n')
    md.append('- 章号断档：%s' % ('、'.join(gaps) if gaps else '无'))
    md.append('- 重名章：%s' % ('、'.join(dup_titles) if dup_titles else '无'))
    md.append('\n## 六、本次新增（上轮未覆盖）\n')
    md.append('、'.join(new_files) if new_files else '无')
    md.append('\n## 七、文风密度观测（对标 benchmark §5.1 范文带·只观测不判未过）\n')
    md.append('| 章文件 | 段均 | 句均 | 台词句均 | 叙述句均 | 短句≤10 | 对话占比 |')
    md.append('|---|---:|---:|---:|---:|---:|---:|')
    for fn, hc, _, _, mt in results:
        m2 = FILENAME.match(fn)
        if m2 and int(m2.group(1)) > args.baseline:
            md.append('| %s | %.1f | %.1f | %.1f | %.1f | %.0f%% | %.0f%% |' % (
                fn, mt['para_avg'], mt['sent_avg'], mt['dialogue_avg'],
                mt['narr_avg'], mt['short_sent'] * 100, mt['dialogue'] * 100))
    md.append('')
    md.append('范文带：段均 18.9–23.2 ｜ 句均 19.0–23.0 ｜ 台词句均 18.6–27.3 ｜ '
              '叙述句均 19.0–24.5 ｜ 短句 19.0–31.5% ｜ 对话 8.0–43.2%')
    md.append('')
    with open(os.path.join(prod, '机检审校报告.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))

    json.dump({
        'gate_version': 4,
        'last_run': now,
        'baseline': args.baseline,
        'audited_files': sorted(cur_files),
        'deep_seeded': deep_seeded,
        'new_files': new_files,
    }, open(state_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    # 控制台
    print('OK 机检完成：%d 章，通过 %d，未过 %d，告警 %d，跨章重复 %d 段' %
          (len(results), len(passed), len(failed), len(warned), len(dups)))
    print('待深度全维审校：%d 章；本次新增：%d 章' % (deep_backlog, len(new_files)))
    if failed:
        for fn, hc, iss, _, _ in failed[:20]:
            print('  [未过] %s (%d字): %s' % (fn, hc, '；'.join(iss)))
    if warned:
        for fn, _, _, ws, _ in warned[:20]:
            print('  [告警] %s: %s' % (fn, '；'.join(ws)))
    if args.strict and failed:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
