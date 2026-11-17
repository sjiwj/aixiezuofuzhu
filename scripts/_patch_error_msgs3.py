#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错误普通话化补丁（第三批，幂等）：把「模块内已经成型、直接回给界面」的错误串改中文。

处理：ai_detect / history / reviewers / planning / charge_guard / breakdown_ui / update_ledgers。
不动：日志行（_log / _f.write / sys.stderr / print）、多参数复杂格式（这几条走 SPECIAL 手工锚定）。

用法：python scripts/_patch_error_msgs3.py [--dry-run]
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, 'core')

TARGETS = ['ai_detect.py', 'history.py', 'reviewers.py', 'planning.py',
           'charge_guard.py', 'breakdown_ui.py', 'update_ledgers.py']

IMP = 'from errors import human, report          # v1.0.1 错误普通话化：界面只显示中文，原文进日志\n'

# 三种形态：var / str(var)[:n]；单引号或双引号前缀
PAT_SQ = re.compile(
    r"'([^'\n]*)%s: %s'\s*%\s*\(type\((\w+)\)\.__name__,\s*(?:str\(\2\)\[:\d+\]|\2)\)", re.S)
PAT_DQ = re.compile(
    r'"([^"\n]*)%s: %s"\s*%\s*\(type\((\w+)\)\.__name__,\s*(?:str\(\2\)\[:\d+\]|\2)\)', re.S)

LOG_MARKS = ('_log(', '_f.write', 'sys.stderr.write', 'print(')

# 第四批无法正则化的（多参数 / 特殊前缀），逐条锚定：(文件, old, new)
SPECIAL = [
    ('breakdown_ui.py',
     "        return '', '「%s」拆解失败：%s: %s' % (dim, type(e).__name__, str(e)[:80])\n",
     "        return '', '「%s」拆解失败：%s' % (dim, report(e))\n"),
    ('breakdown_ui.py',
     "                'warning': '拆解已写好，但原文路径没记住（%s: %s）' % (type(e).__name__, e)}\n",
     "                'warning': '拆解已写好，但原文路径没记住（%s）' % report(e)}\n"),
]


def make_repl(quote):
    def repl(m):
        prefix, var = m.group(1), m.group(2)
        if '%' in prefix:
            return m.group(0)
        if prefix.strip() == '':
            return 'report(%s)' % var
        return '%s%s%s + report(%s)' % (quote, prefix, quote, var)
    return repl


def in_log_line(src, m):
    start = src.rfind('\n', 0, m.start()) + 1
    end = src.find('\n', m.end())
    line = src[start:end if end >= 0 else len(src)]
    return any(k in line for k in LOG_MARKS)


def ensure_import(out, name=''):
    if 'from errors import human, report' in out:
        return out, True
    # 只认行首（顶层）import；函数体内的 import 缩进过，不能当锚点
    for anchor in ('import coordinator as CO\n', 'import sys\n', 'import os\n'):
        m = re.search(r'^' + re.escape(anchor), out, re.M)
        if m:
            return out[:m.end()] + IMP + out[m.end():], True
    return out, False


def patch_file(path, dry, specials):
    raw = open(path, encoding='utf-8', newline='').read()
    crlf = raw.count('\r\n')
    lf = raw.count('\n')
    mixed = crlf and crlf != lf
    if mixed:
        print('  FAIL  CRLF/LF 混杂，跳过（%s）' % os.path.basename(path))
        return 0, 0, 1
    src = raw.replace('\r\n', '\n')

    pieces, changed, skipped = [], 0, 0
    for pat, quote in ((PAT_SQ, "'"), (PAT_DQ, '"')):
        for m in pat.finditer(src):
            if in_log_line(src, m):
                skipped += 1
                continue
            new = make_repl(quote)(m)
            if new == m.group(0):
                skipped += 1
                continue
            pieces.append((m.start(), m.end(), new))
            changed += 1

    out = src
    if pieces:
        pieces.sort()
        parts, last = [], 0
        for s, e, new in pieces:
            if s < last:
                continue
            parts.append(out[last:s])
            parts.append(new)
            last = e
        parts.append(out[last:])
        out = ''.join(parts)

    for old, new in specials:
        if new in out and old not in out:
            continue
        if old in out:
            out = out.replace(old, new)
            changed += 1

    failed = 0
    if changed:
        out, ok = ensure_import(out, os.path.basename(path))
        if not ok:
            print('  FAIL  找不到 import 锚点：%s' % os.path.basename(path))
            failed = 1

    if changed and not dry and not failed and out != src:
        if crlf:
            out = out.replace('\n', '\r\n')
        tmp = path + '.tmp-patch'
        with open(tmp, 'w', encoding='utf-8', newline='') as f:
            f.write(out)
        os.replace(tmp, path)

    return changed, skipped, failed


def main():
    dry = '--dry-run' in sys.argv
    tot = [0, 0, 0]
    for name in TARGETS:
        path = os.path.join(CORE, name)
        sp = [(o, n) for (f, o, n) in SPECIAL if f == name]
        c, s, f = patch_file(path, dry, sp)
        tot[0] += c
        tot[1] += s
        tot[2] += f
        print('%-20s replaced=%d skipped=%d failed=%d' % (name, c, s, f))
    print('\n合计: replaced=%d skipped=%d failed=%d%s'
          % (tot[0], tot[1], tot[2], '（dry-run）' if dry else ''))
    return 1 if tot[2] else 0


if __name__ == '__main__':
    sys.exit(main())
