# -*- coding: utf-8 -*-
"""本章体检：一条命令看完所有机械检查。

用法:
    python scripts/gate_report.py "<章节.md>" [--book 书名] [--json]

串起来的东西：
    闸 1  开书前设定自洽（core/check_setup.py）
    闸 3  物品 / 能力 / 伏笔（scripts/l3_l4_check.py 的 gate3）
    L1/L2 格式与重复 + 套话（scripts/l1_l2_check.py）
    L3/L4 空间与时间（scripts/l3_l4_check.py）

判定：任一 error -> fail；有 warn 但无 error -> warn；全 skipped -> inconclusive
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'core'))

PY = sys.executable


def _run(args, timeout=180):
    try:
        p = subprocess.run([PY] + args, cwd=ROOT, capture_output=True,
                           timeout=timeout, encoding='utf-8', errors='replace')
        return p.returncode, p.stdout or '', p.stderr or ''
    except Exception as e:
        return 1, '', '%s: %s' % (type(e).__name__, e)


def book_of(chapter_path, explicit=None):
    if explicit:
        return explicit
    d = os.path.dirname(os.path.abspath(chapter_path))
    return os.path.basename(os.path.dirname(d)) if os.path.basename(d) == '章节' else os.path.basename(d)


def _msg(i):
    for k in ('message', 'item', 'detail', 'text', 'msg', 'reason'):
        if i.get(k):
            return str(i[k])
    return ''


def load_json_file(path):
    try:
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    ap = argparse.ArgumentParser(description='本章体检：闸1 + 闸3 + L1/L2 + L3/L4')
    ap.add_argument('chapter')
    ap.add_argument('--book', default=None)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    chapter = os.path.abspath(a.chapter)
    if not os.path.isfile(chapter):
        print('找不到章节文件：%s' % chapter)
        return 2
    book = book_of(chapter, a.book)

    tmp = os.path.join(HERE, '..', '_tmp')
    os.makedirs(tmp, exist_ok=True)
    l12_json = os.path.join(tmp, 'gate_l12.json')
    l34_json = os.path.join(tmp, 'gate_l34.json')

    code1, out1, err1 = _run([os.path.join('scripts', 'l1_l2_check.py'), chapter,
                              '--no-cache', '--json', l12_json])
    code3, out3, err3 = _run([os.path.join('scripts', 'l3_l4_check.py'), chapter,
                              '--no-cache', '--json', l34_json])
    code2, out2, err2 = _run([os.path.join('core', 'check_setup.py'), '--book', book, '--json'])

    l12 = load_json_file(l12_json)
    l34 = load_json_file(l34_json)
    try:
        setup = json.loads(out2) if out2.strip().startswith('{') else {}
    except ValueError:
        setup = {}

    def bucket(doc):
        iss = doc.get('issues') or []
        return {
            'error': [i for i in iss if str(i.get('severity')) == 'error'],
            'warn': [i for i in iss if str(i.get('severity')) == 'warn'],
            'info': [i for i in iss if str(i.get('severity')) == 'info'],
        }

    b12, b34 = bucket(l12), bucket(l34)
    g3 = (l34.get('stats') or {}).get('gate3') or {}
    errors = b12['error'] + b34['error']
    warns = b12['warn'] + b34['warn']
    infos = b12['info'] + b34['info']

    verdict = 'fail' if errors else ('warn' if warns else ('pass' if (b12 or b34) else 'inconclusive'))

    report = {
        'chapter': chapter,
        'book': book,
        'verdict': verdict,
        'counts': {'error': len(errors), 'warn': len(warns), 'info': len(infos)},
        'l1l2': {'issues': l12.get('issues') or [], 'coverage': l12.get('coverage') or {}},
        'l3l4': {'issues': l34.get('issues') or [], 'gate3': g3, 'coverage': l34.get('coverage') or {}},
        'setup': {'verdict': setup.get('verdict'), 'gaps': setup.get('gaps'),
                  'contradictions': setup.get('contradictions'),
                  'current_chapter': setup.get('current_chapter'),
                  'issues': setup.get('issues') or []},
        'runs': {'l1_l2_exit': code1, 'l3_l4_exit': code3, 'setup_exit': code2,
                 'stderr': [s for s in (err1, err3, err2) if s.strip()]},
    }

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if verdict != 'fail' else 1

    print('=' * 66)
    print('本章体检  %s' % os.path.basename(chapter))
    print('=' * 66)
    print('判定: %s   错误 %d / 警告 %d / 提示 %d' % (
        verdict, len(errors), len(warns), len(infos)))

    cov12 = report['l1l2']['coverage'] or {}
    cov34 = report['l3l4']['coverage'] or {}
    print('L1/L2 覆盖 %s/%s   L3/L4 覆盖 %s/%s' % (
        cov12.get('checked', '-'), cov12.get('total', '-'),
        cov34.get('checked', '-'), cov34.get('total', '-')))
    if g3:
        _ab = g3.get('foreshadow_abandoned', 0)
        print('闸3: 物品 %s 项 · 境界 %s 条 · 伏笔 %s 条（本章触及 %s，陈旧 %s%s）' % (
            g3.get('items_checked', 0), g3.get('realms', 0), g3.get('foreshadow', 0),
            g3.get('foreshadow_touched', 0), g3.get('foreshadow_stale', 0),
            ('，已作废 %d' % _ab) if _ab else ''))
    sv = report['setup']
    if sv.get('verdict'):
        print('闸1: %s   矛盾 %s / 待补 %s（截至第 %s 章）' % (
            sv.get('verdict'), sv.get('contradictions', 0), sv.get('gaps', 0),
            sv.get('current_chapter', '?')))
    print('-' * 66)

    for tag, group, icon in (('ERROR', errors, '❌'), ('WARN', warns, '⚠️ '), ('INFO', infos, 'ℹ️ ')):
        for i in group:
            loc = (' [行 %s]' % i['line']) if i.get('line') else ''
            print('%s %-5s %-24s%s  %s' % (icon, tag, i.get('rule'), loc, i.get('message')))
    if not (errors or warns or infos):
        print('✅ 机械检查全过')
    print('-' * 66)

    for i in (sv.get('issues') or []):
        lvl = '[矛盾]' if i.get('level') == 'contradiction' else '[待补]'
        print('%-6s %-8s %s' % (lvl, i.get('ledger'), _msg(i)))
    return 0 if verdict != 'fail' else 1


if __name__ == '__main__':
    sys.exit(main())
