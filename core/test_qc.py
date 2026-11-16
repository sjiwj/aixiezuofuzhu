# -*- coding: utf-8 -*-
"""质检接口的失败路径自测：超时 / 脚本缺失 / 脚本崩溃 / 文本兜底解析。"""
import json, os, sys, time, tempfile
sys.path.insert(0, 'core')
import server as S

fails = []


def check(label, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + label + ('' if cond else ' | ' + str(detail)[:300]))
    if not cond:
        fails.append(label)


# ---------- 1. 文本兜底解析 ----------
sample = """质检报告  x.md
----------------------------------------
字数 3277   段落 130   破折号 0   阿拉伯数字 0   主角名 12 次
--------------------------------------------------------------------------
❌ ERROR dash_count          [行 12]  破折号 3 个，上限 0
        → ——
⚠️  WARN  paragraph_length    [行 40]  2 段超过 100 字
        → 最长 180 字
ℹ️  INFO  dialogue_tag                   「他说/他道」连续 3 次
--------------------------------------------------------------------------
合计: 1 错误 / 1 警告 / 1 提示
"""
issues = S._parse_l1l2_text(sample)
check('T1 解析出 3 条', len(issues) == 3, issues)
check('T2 行号与 snippet', issues[0]['line'] == 12 and issues[0]['snippet'] == '——', issues[0])
check('T3 无行号条目不瞎填', issues[2]['line'] is None and issues[2]['severity'] == 'info', issues[2])
check('T4 rule 名正确', [i['rule'] for i in issues] == ['dash_count', 'paragraph_length', 'dialogue_tag'],
      [i['rule'] for i in issues])

# ---------- 2. issue 归一 ----------
n = S._norm_issue({'rule': 'X', 'severity': 'ERROR', 'line': '0', 'message': 'm'}, 'l1l2')
check('N1 severity 归一 + line 0 -> None', n['severity'] == 'error' and n['line'] is None, n)
n = S._norm_issue({'severity': 'fatal', 'line': '7'}, 'l3l4')
check('N2 未知 severity 落 info + line 转 int', n['severity'] == 'info' and n['line'] == 7, n)
n = S._norm_issue({}, 'l3l4')
check('N3 空 issue 不炸', n['rule'] == 'unknown' and n['message'] == '', n)

# ---------- 3. 超时 ----------
slow = os.path.join(S.ROOT, 'core', '_slow_probe.py')
with open(slow, 'w', encoding='utf-8') as f:
    f.write('import time\ntime.sleep(10)\n')
try:
    t0 = time.time()
    ok, out, err, info = S._run_script('core/_slow_probe.py', [], timeout=1)
    dt = time.time() - t0
    check('R1 超时被捕获', ok is False and info.get('error') == 'timeout', info)
    check('R2 1 秒左右返回不挂死', dt < 5, round(dt, 2))
finally:
    os.remove(slow)

# ---------- 4. 脚本缺失 ----------
ok, out, err, info = S._run_script('scripts/_not_exist.py', [])
check('R3 脚本缺失有明确 error', ok is False and info.get('error') == 'script_missing', info)

# ---------- 5. 脚本崩溃 + 两边都挂 -> ok:false 且不抛异常 ----------
crash = os.path.join(S.ROOT, 'core', '_crash_probe.py')
with open(crash, 'w', encoding='utf-8') as f:
    f.write('import sys\nprint("boom", file=sys.stderr)\nsys.exit(3)\n')
chap = os.path.join(S.ROOT, 'projects', '<书名>', '章节', '001-第一章-柴没砍完.md')
old = dict(S.QC_SCRIPTS)
try:
    S.QC_SCRIPTS['l1l2'] = 'core/_crash_probe.py'
    S.QC_SCRIPTS['l3l4'] = 'scripts/_not_exist.py'
    res = S.run_qc_file(chap, 'projects/<书名>/章节/001-第一章-柴没砍完.md')
    check('C1 两边都挂 -> ok:false', res['ok'] is False, res.get('errors'))
    check('C2 errors 有两条且带脚本名', len(res.get('errors', [])) == 2 and
          {e['tool'] for e in res['errors']} == {'l1l2', 'l3l4'}, res.get('errors'))
    check('C3 仍然返回合法结构', all(k in res for k in ('issues', 'stats', 'summary')), res.keys())
finally:
    S.QC_SCRIPTS.update(old)
    os.remove(crash)

# ---------- 6. 正常跑一次（真脚本），确认清理临时目录 ----------
import tempfile as _tf
tmp_before = set(os.listdir(tempfile.gettempdir()))
res = S.run_qc_file(chap, 'projects/<书名>/章节/001-第一章-柴没砍完.md')
tmp_after = set(os.listdir(tempfile.gettempdir()))
check('G1 真脚本 ok:true', res['ok'] is True and res['stats'].get('l1l2', {}).get('_from') == 'json', res.get('errors'))
check('G2 统计有 file/l3l4', 'file' in res['stats'] and 'l3l4' in res['stats'], list(res['stats']))
check('G3 summary.level 合法', res['summary']['level'] in ('pass', 'warn', 'error'), res['summary'])
check('G4 临时目录已清理', not any(x.startswith('novelapp_qc_') for x in (tmp_after - tmp_before)),
      [x for x in (tmp_after - tmp_before) if x.startswith('novelapp_qc_')])

print('----')
print('FAILED: %d' % len(fails))
for f in fails:
    print('  ' + f)
sys.exit(1 if fails else 0)
