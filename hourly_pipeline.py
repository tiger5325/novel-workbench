# -*- coding: utf-8 -*-
"""
每小时流水线：重建web数据包 + 机检 + 生成进度汇报
由 Windows 计划任务每小时调用。
退出码：0=正常；1=有硬闸未过章（不阻断，只标记）。
"""
import os, sys, subprocess, datetime, json, re

ROOT = r'F:\F05_Projects_Hub\智能网文小说创作工作台'
PY = r'F:\F03_Deps_Hub\Python_Local\bin\python.exe'
PROJ = r'F:\F05_Projects_Hub\穿越之我是杨广'
CORPUS = os.path.join(PROJ, '正文_精修版')   # 扫全部卷目录
TARGET_CHAPTERS = 1012
LOG_DIR = os.path.join(PROJ, '_工单与报告', 'hourly_log')
os.makedirs(LOG_DIR, exist_ok=True)

now = datetime.datetime.now()
stamp = now.strftime('%Y%m%d_%H%M')
log_path = os.path.join(LOG_DIR, 'pipeline_%s.log' % stamp)
report_path = os.path.join(LOG_DIR, 'latest_report.md')

lines = []
def log(msg):
    lines.append(msg)
    print(msg)

log('# 每小时流水线 %s' % now.strftime('%Y-%m-%d %H:%M:%S'))
log('')

# ① 统计当前章节数与字数（跨全部卷目录）
HAN = re.compile(r'[\u4e00-\u9fff]')
ch_re = re.compile(r'^(\d{3})_(.+)\.md$')
ch_files = []   # (章号int, 文件名, 卷目录)
for vol in sorted(os.listdir(CORPUS)):
    vd = os.path.join(CORPUS, vol)
    if not os.path.isdir(vd) or ('备份' in vol) or vol.startswith('_'):
        continue
    for fn in os.listdir(vd):
        m = ch_re.match(fn)
        if m:
            ch_files.append((int(m.group(1)), fn, vol))
ch_files.sort()
total_han = 0
for num, fn, vol in ch_files:
    with open(os.path.join(CORPUS, vol, fn), encoding='utf-8') as f:
        total_han += len(HAN.findall(f.read()))
max_ch = ch_files[-1][0] if ch_files else 0
next_ch = max_ch + 1
log('## 一、正文进度')
log('- 章节数：%d / 目标 %d（%.1f%%）' % (len(ch_files), TARGET_CHAPTERS, 100.0*len(ch_files)/TARGET_CHAPTERS))
log('- 章号区间：%03d ~ %03d；下一章应写：%03d' % (ch_files[0][0] if ch_files else 0, max_ch, next_ch))
log('- 总汉字数：%d（约 %.1f 万字）' % (total_han, total_han/10000.0))
# 各卷分布
from collections import Counter
vc = Counter(v for _, _, v in ch_files)
log('- 各卷：' + '；'.join('%s=%d章' % (v, c) for v, c in sorted(vc.items())))
log('')

# ② 重建 web/data.js
log('## 二、重建 web/data.js')
build_py = os.path.join(ROOT, 'web', 'build.py')
r = subprocess.run([PY, build_py], capture_output=True, text=True, encoding='utf-8')
log('```')
log(r.stdout.strip() if r.stdout else '(无stdout)')
if r.stderr:
    log('[stderr] ' + r.stderr.strip()[:500])
log('```')
log('')

# ③ 跑机检
log('## 三、机检')
qc_py = os.path.join(ROOT, 'qc_audit.py')
r2 = subprocess.run([PY, qc_py, '--baseline', '110'], capture_output=True, text=True, encoding='utf-8')
log('```')
log(r2.stdout.strip() if r2.stdout else '(无stdout)')
log('```')
log('')

# ④ 写汇报文件
with open(log_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

# ⑤ 写状态json供主agent读取
state = {
    'last_run': now.strftime('%Y-%m-%d %H:%M:%S'),
    'chapter_count': len(ch_files),
    'target': TARGET_CHAPTERS,
    'max_chapter': max_ch,
    'next_chapter_to_write': next_ch,
    'total_han': total_han,
    'log_file': log_path,
    'qc_exit': r2.returncode,
}
with open(os.path.join(LOG_DIR, 'latest_state.json'), 'w', encoding='utf-8') as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print('')
print('流水线完成，日志：' + log_path)
sys.exit(0)
