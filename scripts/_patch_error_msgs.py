#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错误普通话化补丁（幂等）：把 `'%s: %s' % (type(e).__name__, e)` 换成中文。

只改「直接把异常字符串回给界面」的出口；不动日志行、不动含多参数的复杂格式。
每处替换同时写 errors.log（report() 负责），界面只拿中文。

用法：
  python scripts/_patch_error_msgs.py --dry-run
  python scripts/_patch_error_msgs.py
重复跑第二遍必须是 no-op。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, 'core', 'server.py')

# '...%s: %s' % (type(e).__name__, e)
# 允许 % 两侧换行（原文件有跨行写法），变量名必须前后一致
PAT = re.compile(
    r"'([^'\n]*)%s: %s'\s*%\s*\(type\((\w+)\)\.__name__,\s*\2\)",
    re.S,
)

IMPORT_BLOCK = """import coordinator as CO
from errors import human, report          # v1.0.1 错误普通话化：界面只显示中文，原文进日志
"""
IMPORT_OLD = "import coordinator as CO\n"


def repl(m):
    prefix, var = m.group(1), m.group(2)
    if '%' in prefix:                     # 多参数格式，交给人看，不自动改
        return m.group(0)
    if prefix.strip() == '':
        return 'report(%s)' % var
    return "'%s' + report(%s)" % (prefix, var)


def _in_log_line(src, m):
    """匹配点所在行是不是 _log(...)：日志要留英文原文，不能改成中文。"""
    start = src.rfind('\n', 0, m.start()) + 1
    end = src.find('\n', m.end())
    line = src[start:end if end >= 0 else len(src)]
    return '_log(' in line


def main():
    dry = '--dry-run' in sys.argv
    src = open(SERVER, encoding='utf-8', newline='').read()
    if '\r\n' in src:
        raise SystemExit('server.py 含 CRLF，按 LF 处理，停止')

    hits = list(PAT.finditer(src))
    pieces = []
    last = 0
    changed = skipped = 0
    print('server.py 命中 %d 处候选\n' % len(hits))
    for m in hits:
        old = m.group(0).replace('\n', ' ')
        new = repl(m).replace('\n', ' ')
        if old == new or _in_log_line(src, m):
            print('  SKIP  %s' % old[:110])
            skipped += 1
            continue
        print('  - %s' % old[:110])
        print('  + %s' % new[:110])
        pieces.append(src[last:m.start()])
        pieces.append(new)
        last = m.end()
        changed += 1

    if pieces:
        pieces.append(src[last:])
        out = ''.join(pieces)
    else:
        out = src

    if 'from errors import human, report' in out:
        print('\nimport: 已存在，跳过')
    elif IMPORT_OLD in out:
        out = out.replace(IMPORT_OLD, IMPORT_BLOCK, 1)
        print('\nimport: 已加入 from errors import human, report')
    else:
        raise SystemExit('找不到 import 锚点，停止')

    print('\n计划替换 %d 处，跳过 %d 处' % (changed, skipped))
    if dry:
        print('dry-run，未写盘')
        return 0
    if out == src:
        print('内容无变化（幂等）')
        return 0
    tmp = SERVER + '.tmp-patch'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(out)
    os.replace(tmp, SERVER)
    print('已写入 core/server.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())
