# -*- coding: utf-8 -*-
"""路径审计：客户数据必须走 projects_root()，不许直接拼程序目录。

为什么要这个脚本：
    2026-11-07 一天里同一个 bug 犯了四次（promises / update_state / check_setup /
    infogap + coordinator 三处）。表现都是「客户机上读不到数据」，
    因为代码拿 ROOT（程序安装目录）去拼 projects/，而客户数据在 %APPDATA%。

用法:
    python scripts/audit_paths.py            # 人看
    python scripts/audit_paths.py --json     # 机读
退出码：发现违规 -> 1
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 允许的写法：fallback 的最后一行（有 return，且是 projects_root 定义体内）
ALLOW_MARK = 'projects_root'

PATTERNS = [
    (re.compile(r"os\.path\.join\(\s*(?:CO\.)?ROOT\s*,\s*['\"]projects['\"]"), '拼程序目录'),
    (re.compile(r"os\.path\.join\(\s*(?:CO\.)?ROOT\s*,\s*['\"]projects['\"]\s*,"), '拼程序目录'),
]


def scan_file(path):
    out = []
    try:
        with open(path, encoding='utf-8-sig', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return out
    cur_func = ''
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip('\n')
        stripped = line.strip()
        mdef = re.match(r'def\s+(\w+)', stripped)
        if mdef:
            cur_func = mdef.group(1)
        if stripped.startswith('#'):
            continue
        # projects_root / _projects_root 定义体内的 fallback 是合法的
        if cur_func in ('projects_root', '_projects_root'):
            continue
        for pat, why in PATTERNS:
            if pat.search(line):
                out.append({'file': os.path.relpath(path, ROOT), 'line': i,
                            'why': why, 'text': stripped[:120]})
                break
    return out


def audit():
    hits = []
    for sub, exts in (('core', ('.py',)), ('scripts', ('.py',)), ('plugin/lib', ('.js',))):
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if '.bak' in name or not name.endswith(exts):
                continue
            hits.extend(scan_file(os.path.join(d, name)))
    return hits


def main():
    ap = argparse.ArgumentParser(description='路径审计：客户数据不许拼程序目录')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    hits = audit()
    if a.json:
        print(json.dumps({'ok': not hits, 'violations': hits}, ensure_ascii=False, indent=2))
        return 0 if not hits else 1
    if not hits:
        print('路径审计通过：没有直接拼 ROOT/projects 的地方')
        return 0
    print('路径审计：发现 %d 处直接拼程序目录（客户机上会读不到数据）' % len(hits))
    print('-' * 66)
    for h in hits:
        print('%-28s :%-4d %s' % (h['file'], h['line'], h['text']))
        print('     -> 应改为 projects_root() / CO.projects_root()')
    print('-' * 66)
    print('例外：projects_root() 定义体内的 fallback 返回行可以保留。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
