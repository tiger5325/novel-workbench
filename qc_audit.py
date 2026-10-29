#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
质控机检脚本 · 智能网文小说创作工作台 v6
========================================
对现行正文逐章做【确定性】机检，不依赖任何 LLM / 远程技能，可无人值守运行。
规则全部外置到 qc_rules.json（缺失则用内置默认值）——换书复用只改规则、不改脚本。

硬闸（全章适用）：
  - 首行「# 章名」单标题行，标题汉字数 = rules.title_words（默认 7），标题与文件名一致
  - 纯汉字字数三段口径（默认 2600–3200 标准 / >3200 且 ≤3520 只告警 / >3520 判未过）
  - 禁 ASCII 直引号 / 直角引号「」；弯引号须成对
  - 禁阿拉伯数字（数字全汉字）
  - 违禁词（通用：当代科技术语 + 后世才有人物事物）与「用词应替换」（本项目方言映射）
  - 禁格式元素：小标题(#)/加粗(**)/分隔线(---)/列表(* -)
  - 跨章重复段落（≥25 汉字的段落全文比对）

内容闸（仅对 --baseline 之后的新章生效；冻结章不追溯）：
  - 岁数直报（「十六岁」等；「三岁一易」制度语豁免）
  - 章内重复段落（≥10 汉字且出现≥2次）
  - 公式化措辞超限（套话词表 + 合闸 + 二批动作代偿型套话；只计叙述段）
  - 章末套话、现代词、人名错写

只观测不判未过：
  - 文风密度（段均/句均/台词句均/叙述句均/短句占比/对话占比）：报告给分布与偏离 Top-N
  - 月份节气、数据罗列、章末碎段、整句重复、台词内公式句

产物：
  - <项目根>/_工单与报告/机检报告/机检审校报告.md
  - <项目根>/_工单与报告/机检报告/qc_audit_state.json

用法：
  python qc_audit.py [--root <项目根>] [--rules <规则文件>]
                     [--deep-seeded <已深度全维审校章数>] [--baseline 164] [--strict]
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

# ---- 规则默认值（＝本项目当前口径）----
# 换书复用只改 qc_rules.json，不必动脚本。缺失规则文件时用这里的默认值，零配置可跑。
DEFAULTS = {
    'words': {'min': 2600, 'standard_max': 3200, 'hard_max': 3520},
    'title_words': 7,
    'banned_words': ['GDP', 'KPI', '系统', '互联网', '蒸汽机', '供应链', '杠杆',
                     '鉴真', '郑和', '贾岛', '近代火炮'],
    'lexicon_map': {'太极宫': '大兴宫', '太极殿': '大兴殿'},
    'modern_hard': ['奶酪', '蛋糕', '起跑线', '钢印', '公司', '董事长',
                    '签字权', '付款权', '绩效', '第二选项', '管理层', '复盘', '闭环',
                    '政策红利', '全员通告', '新老板', '总裁', '业绩', '风险点'],
    'modern_warn': ['底线', '赋能', '赛道', '颗粒度',
                    '底层逻辑', '考核', '指标', '认知', '信息差', '用户', '产品'],
    'name_typo': ['杨谦', '杨先'],
    'formula': {
        '原以为': 1, '没想到': 1, '愣了一下': 1, '说不出话': 1,
        '他知道': 1, '他也知道': 1, '他明白': 1, '他清楚': 1,
        '叹了口气': 1, '深吸一口气': 1, '眉头一皱': 1, '心里一沉': 1,
        '因为他是杨广': 0, '大隋的皇帝': 1, '一件一件': 1,
        '不能马虎': 0, '不敢马虎': 0, '这是他的使命': 0, '也是他的宿命': 0,
        '越来越好': 1, '不急': 1, '但不停': 0, '一步一步': 1,
    },
    'formula_core': ['他知道', '他也知道', '原以为', '没想到', '愣了一下', '说不出话'],
    'formula_core_cap': 3,
    # 二批公式句：动作代偿型套话（用固定小动作替代具体观察）。组名 -> [变体, 单章上限]
    'formula2': {
        '静场': [['静了一息', '静了一静', '沉默了一息', '沉默片刻'], 1],
        '停顿': [['顿了顿', '停了一停'], 1],
        '半晌': [['半晌'], 1],
        '看一眼': [['看了他一眼', '看了她一眼', '看了他们一眼', '看了一眼'], 1],
        '轻笑': [['笑了一下', '笑了一声', '笑了笑'], 2],
        '指节指尖': [['指节', '指尖'], 2],
        '喉头': [['喉头', '喉咙'], 1],
        '没说话': [['没说话', '没接话', '没有接话', '没有出声', '没出声'], 1],
    },
    # 「不是…是…」对举：单句内出现「不是」与「，是」/「。是」的对照结构
    'not_a_b': {'pattern': '不是[^。！？；]{1,20}[，。]是', 'cap': 3},
    # 文风密度参考带（对标范文实测·10 章干净口径；仅供观测与排行，不判未过）
    'style_band': {
        'sent_avg': [18.5, 25.0],
        'dialogue_avg': [16.5, 30.0],
        'narr_avg': [18.0, 26.0],
        'short_sent': [0.15, 0.34],
        'para_avg': [18.0, 25.0],
        'dialogue': [0.05, 0.48],
    },
    'style_top_n': 10,
    'end_marks': ['因为他是杨广', '大隋的皇帝', '这是他的使命', '也是他的宿命',
                  '不能马虎', '不敢马虎', '一件一件', '一步一步', '但不停',
                  '他要让这个天下', '这就是他要做的事'],
    'exclude_pattern': '(README|说明|样章)',
}

RULES = {}


def load_rules(path=None):
    """读取规则文件；缺失或损坏则用内置 DEFAULTS（不阻断机检）。"""
    rules = json.loads(json.dumps(DEFAULTS))
    p = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qc_rules.json')
    if os.path.isfile(p):
        try:
            with open(p, encoding='utf-8') as f:
                user = json.load(f)
            for k, v in user.items():
                if k.startswith('_'):
                    continue
                if k == 'words' and isinstance(v, dict):
                    rules['words'].update(v)
                else:
                    rules[k] = v
            rules['_source'] = p
        except Exception as e:
            sys.stderr.write('[WARN] 规则文件解析失败，改用内置默认：%s\n' % e)
            rules['_source'] = 'builtin'
    else:
        rules['_source'] = 'builtin'
    return rules


def apply_rules(rules):
    """把规则摊成模块级常量，check() 直接引用。"""
    g = globals()
    g['RULES'] = rules
    g['BANNED'] = list(rules['banned_words'])
    g['LEXICON'] = dict(rules.get('lexicon_map') or {})
    g['MODERN_HARD'] = list(rules['modern_hard'])
    g['MODERN_WARN'] = list(rules['modern_warn'])
    g['NAME_TYPO'] = list(rules['name_typo'])
    g['FORMULA'] = {k: int(v) for k, v in rules['formula'].items()}
    g['FORMULA_CORE'] = list(rules['formula_core'])
    g['FORMULA_CORE_CAP'] = int(rules['formula_core_cap'])
    g['FORMULA2'] = {k: (list(v[0]), int(v[1])) for k, v in rules['formula2'].items()}
    g['NOT_A_B'] = re.compile(rules['not_a_b']['pattern'])
    g['NOT_A_B_CAP'] = int(rules['not_a_b']['cap'])
    g['STYLE_BAND'] = {k: tuple(v) for k, v in rules['style_band'].items()}
    g['STYLE_TOP_N'] = int(rules.get('style_top_n', 10))
    g['END_MARKS'] = list(rules['end_marks'])
    g['EXCLUDE'] = re.compile(rules['exclude_pattern'])
    g['WORDS'] = rules['words']
    g['TITLE_WORDS'] = int(rules['title_words'])


# ---- 路径解析（不写死任何本机绝对路径）----
def resolve_project_root(root):
    """项目根：NOVEL_PROJECT_ROOT → root 自身 → root 同级中带「正文_精修版」的目录 → root。
    「工作台 + 同级正稿目录」这种布局下，作者本机与克隆者都能自动找对位置。"""
    env = os.environ.get('NOVEL_PROJECT_ROOT')
    if env and os.path.isdir(env):
        return env
    if os.path.isdir(os.path.join(root, '正文_精修版')):
        return root
    parent = os.path.dirname(os.path.abspath(root))
    try:
        for name in sorted(os.listdir(parent)):
            cand = os.path.join(parent, name)
            if os.path.isdir(os.path.join(cand, '正文_精修版')):
                return cand
    except OSError:
        pass
    return root


def chapter_files(root, prefer_root=False):
    """扫描正文目录。
    prefer_root=True（显式 --root）时只看该目录下的「正文_精修版」/「novel-source」，
    不向上探测，保证临时目录自测不串到作者正稿。"""
    if prefer_root:
        cands = [os.path.join(root, '正文_精修版'), os.path.join(root, 'novel-source')]
    else:
        proj = resolve_project_root(root)
        cands = [os.path.join(proj, '正文_精修版'), os.path.join(root, 'novel-source')]
    corpus = None
    for cand in cands:
        if os.path.isdir(cand):
            corpus = cand
            break
    if corpus is None:
        return [], None
    files = []
    for vol in sorted(os.listdir(corpus)):
        vd = os.path.join(corpus, vol)
        if not os.path.isdir(vd) or ('备份' in vol) or vol.startswith('_'):
            continue
        for fn in sorted(os.listdir(vd)):
            if fn.endswith('.md') and not EXCLUDE.search(fn):
                files.append(os.path.join(vd, fn))
    return files, corpus


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
        if tc != TITLE_WORDS:
            if num is not None and num > baseline:
                issues.append('标题非%d字(%d)' % (TITLE_WORDS, tc))
            else:
                warns.append('标题非%d字(%d)，冻结章不追溯' % (TITLE_WORDS, tc))
        if m and title != m.group(2):
            issues.append('标题与文件名不一致')

    # 字数（三段口径，对齐写作规范：标准区间 / 上浮缓冲 / 硬上限）
    hancount = len(HAN.findall(text))
    w_lo, w_std, w_hard = WORDS['min'], WORDS['standard_max'], WORDS['hard_max']
    if hancount < w_lo:
        issues.append('字数不足(%d<%d)' % (hancount, w_lo))
    elif hancount > w_hard:
        issues.append('字数超硬上限(%d>%d)' % (hancount, w_hard))
    elif hancount > w_std:
        warns.append('字数超出标准区间(%d>%d，未超硬上限%d)' % (hancount, w_std, w_hard))

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

    # 违禁词（跨题材通用：当代科技术语 + 后世才有人物与事物）
    hit = [w for w in BANNED if w in text]
    if hit:
        issues.append('违禁词:' + ','.join(hit))
    # 本项目方言限定用词（左=禁用写法，右=应替换为；属史实/设定考据，不是通用禁词）
    lex = ['%s→%s' % (w, LEXICON[w]) for w in LEXICON if w in text]
    if lex:
        issues.append('用词应替换:' + ','.join(lex))

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
               'dialogue_avg': 0.0, 'narr_avg': 0.0, 'flags': []}
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
        c = sum(narr.count(v) for v in variants)
        if c > cap:
            over.append('%s×%d(上限%d)' % (name, c, cap))
    nab = len(NOT_A_B.findall(narr))
    if nab > NOT_A_B_CAP:
        over.append('不是…是…×%d(上限%d)' % (nab, NOT_A_B_CAP))
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
    # v4 文风密度观测（对标 benchmark §5.1 范文区间）
    # v6（2026-10-30）：不再逐章写进告警——全员命中的告警等于没有告警。
    # 改为 metrics['flags'] 汇总，报告按「偏离幅度 Top-N」列明细。
    flags = []
    for key, label in (('sent_avg', '句均'), ('dialogue_avg', '台词句均'),
                       ('narr_avg', '叙述句均'), ('short_sent', '短句≤10占比'),
                       ('para_avg', '段均')):
        v = metrics.get(key) or 0
        if not v:
            continue
        lo, hi = STYLE_BAND[key]
        if lo <= v <= hi:
            continue
        span = max(1e-9, hi - lo)
        dev = (v - hi) / span if v > hi else (lo - v) / span
        pct = (key == 'short_sent')
        flags.append({
            'metric': label,
            'value': ('%.0f%%' % (v * 100)) if pct else ('%.1f' % v),
            'band': ('%.0f%%–%.0f%%' % (lo * 100, hi * 100)) if pct
                    else ('%.1f–%.1f' % (lo, hi)),
            'dev': round(dev, 3),
        })
    metrics['flags'] = flags
    # 月份/节气与数据罗列：只告警，不扣闸（2026-10-29 作者口径：
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
    ap.add_argument('--root', default=None,
                    help='项目根目录（默认=脚本所在目录；显式传入时只用该目录下的正文源）')
    ap.add_argument('--rules', default=None,
                    help='规则文件路径（默认=脚本同级 qc_rules.json；缺失则用内置默认）')
    ap.add_argument('--deep-seeded', type=int, default=None,
                    help='已做过深度全维审校的章数')
    ap.add_argument('--baseline', type=int, default=0,
                    help='该章号及以前为冻结章，不套用 v2 内容闸')
    ap.add_argument('--strict', action='store_true',
                    help='有未过章时返回 1')
    args = ap.parse_args()
    root = args.root or os.path.dirname(os.path.abspath(__file__))

    rules = load_rules(args.rules)
    apply_rules(rules)

    files, corpus = chapter_files(root, prefer_root=args.root is not None)
    if not files:
        print('未找到章节文件，检查路径：%s 或 %s' %
              (os.path.join(root, '正文_精修版'), os.path.join(root, 'novel-source')))
        return 1
    print('正文源：%s（%d 章）' % (corpus, len(files)))
    print('规则文件：%s' % rules['_source'])

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
    # 显式 --root 时报告落在该根目录下；默认落到项目根的 _工单与报告/机检报告
    if args.root is not None:
        prod = os.path.join(root, '_工单与报告', '机检报告')
    else:
        prod = os.path.join(resolve_project_root(root), '_工单与报告', '机检报告')
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
    md.append('# 机检审校报告（确定性 v6）\n')
    md.append('> 生成时间：%s　｜　范围：现行稿全 %d 章　｜　口径：写作规范.md 硬闸\n'
              % (now, len(results)))
    md.append('> 正文源：`%s`　｜　规则：`%s`\n' % (corpus, rules['_source']))
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
    md.append('| 内容闸基线 | 第 %d 章及以前豁免 |' % args.baseline)
    md.append('| 字数口径 | %d–%d 标准，≤%d 只告警，>%d 判未过 |'
              % (WORDS['min'], WORDS['standard_max'], WORDS['hard_max'], WORDS['hard_max']))
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
    md.append('\n## 七、文风密度观测（对标范文带·只观测不判未过）\n')
    style_rows = [r for r in results if FILENAME.match(r[0])]
    md.append('### 7.1 分布（共 %d 章）\n' % len(style_rows))
    md.append('| 指标 | 范文带 | P10 | 中位数 | P90 | 达标率 |')
    md.append('|---|---|---:|---:|---:|---:|')
    for key, label, pct in (('para_avg', '段均', False), ('sent_avg', '句均', False),
                            ('dialogue_avg', '台词句均', False), ('narr_avg', '叙述句均', False),
                            ('short_sent', '短句≤10占比', True), ('dialogue', '对话占比', True)):
        vals = sorted(r[4].get(key, 0) for r in style_rows if r[4].get(key))
        if not vals:
            continue
        lo, hi = STYLE_BAND[key]
        ok = sum(1 for v in vals if lo <= v <= hi)

        def _p(q):
            i = min(len(vals) - 1, max(0, int(round(q * (len(vals) - 1)))))
            return vals[i]

        fmt = (lambda x: '%.0f%%' % (x * 100)) if pct else (lambda x: '%.1f' % x)
        band = ('%.0f%%–%.0f%%' % (lo * 100, hi * 100)) if pct else ('%.1f–%.1f' % (lo, hi))
        md.append('| %s | %s | %s | %s | %s | %.0f%% |' % (
            label, band, fmt(_p(0.1)), fmt(_p(0.5)), fmt(_p(0.9)),
            ok * 100.0 / len(vals)))

    md.append('')
    md.append('> 读法：达标率反映「全书系统性偏离」而非个别章问题——'
              '中位数整体落在带外时，说明是文风基底要调，不是挑章返工。'
              '本节只观测，不参与未过判定。')

    scored = []
    for fn, _hc, _iss, _ws, mt in style_rows:
        fl = mt.get('flags') or []
        if fl:
            top = max(fl, key=lambda d: d['dev'])
            scored.append((top['dev'], fn, fl))
    scored.sort(key=lambda x: -x[0])
    top_n = scored[:STYLE_TOP_N]
    md.append('')
    md.append('### 7.2 偏离最大 %d 章（按超出参考带宽的倍数排序）\n' % len(top_n))
    if top_n:
        md.append('| 章文件 | 指标 | 实测 | 范文带 | 偏离带宽 |')
        md.append('|---|---|---|---|---:|')
        for dev, fn, fl in top_n:
            first = max(fl, key=lambda d: d['dev'])
            rest = len(fl) - 1
            name = first['metric'] + (' 等%d项' % (rest + 1) if rest else '')
            md.append('| %s | %s | %s | %s | %.1f× |' % (
                fn, name, first['value'], first['band'], dev))
        if len(scored) > len(top_n):
            md.append('')
            md.append('另有 %d 章存在偏离，未列出（合计 %d 章偏离参考带）。'
                      % (len(scored) - len(top_n), len(scored)))
    else:
        md.append('全部章节均落在参考带内。')
    md.append('')
    with open(os.path.join(prod, '机检审校报告.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))

    json.dump({
        'gate_version': 6,
        'rules_source': rules['_source'],
        'corpus': corpus,
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
