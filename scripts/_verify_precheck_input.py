#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写前粗筛（precheck_input）验收。

A 单元：7 种输入，断言 block/warn 与预期一致
B 集成：起后端打 /api/write，缺大纲 / 章号非法必须 400 且带 screen；不触发模型调用
C 不回归：precheck.py（写后机检）未被改动，两模块互不覆盖

用法：python scripts/_verify_precheck_input.py
"""
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'core'))

import precheck_input as PI      # noqa: E402

GOOD = """<details>
<summary>003 分场章纲</summary>

**场次**

| 场 | 地点·时辰 | 发生什么 | 约字数 |
|---|---|---|---|
| 场1 | 门口·晨 | 他停住 | 400 |
| 场2 | 柜台·晨 | 他要赎当 | 1200 |

**必须做到的事**

1. 先摸白线
2. 推木牌
3. 只说一句

**不许做**

- 不许出现配角甲
</details>
"""


def unit(d):
    cases = [
        ('正常', dict(book='示例书', chapter='003'), True, []),
        ('缺大纲', dict(book='示例书', chapter='009'), False, ['precheck.no_outline']),
        ('一句话章纲', dict(book='示例书', chapter='004'), True, []),
        ('占位残留', dict(book='示例书', chapter='005'), False, ['precheck.placeholder']),
        ('章号非法', dict(book='示例书', chapter='第三章'), False, ['precheck.chapter_no']),
        ('覆盖定稿', dict(book='示例书', chapter='003', stage='done'), True, []),
        ('force 放行', dict(book='示例书', chapter='009', force=True), True, []),
    ]
    bad = 0
    for label, kw, expect_ok, expect_codes in cases:
        r = PI.screen_write(root=os.path.join(d, 'projects'), **kw)
        codes = [x['code'] for x in r['blocked']]
        ok = (r['ok'] is expect_ok) and all(c in codes for c in expect_codes)
        bad += 0 if ok else 1
        print('  %s  %-10s ok=%-5s block=%s' % ('PASS' if ok else 'FAIL', label, r['ok'], codes or '-'))
    # warn 断言
    one = PI.screen_write(root=os.path.join(d, 'projects'), book='示例书', chapter='004')
    ok = 'precheck.outline_one_line' in [x['code'] for x in one['warn']]
    bad += 0 if ok else 1
    print('  %s  warn:一句话章纲 → outline_one_line' % ('PASS' if ok else 'FAIL'))
    done = PI.screen_write(root=os.path.join(d, 'projects'), book='示例书', chapter='003', stage='done')
    ok = 'precheck.overwrite_done' in [x['code'] for x in done['warn']]
    bad += 0 if ok else 1
    print('  %s  warn:覆盖定稿 → overwrite_done' % ('PASS' if ok else 'FAIL'))
    return bad


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(port, method, path, body=None):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    h = {'Host': '127.0.0.1:%d' % port, 'Content-Type': 'application/json'}
    data = json.dumps(body).encode() if body is not None else None
    c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    for k, v in h.items():
        c.putheader(k, v)
    if data is not None:
        c.putheader('Content-Length', str(len(data)))
    c.endheaders()
    if data is not None:
        c.send(data)
    r = c.getresponse()
    txt = r.read().decode('utf-8', 'ignore')
    c.close()
    return r.status, txt


def integration(d):
    port = free_port()
    env = dict(os.environ)
    env['NOVELAPP_DATA'] = d
    env.pop('NOVELAPP_BACKEND_TOKEN', None)
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'core', 'server.py'),
                             str(port), '--no-browser'],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    bad = 0
    try:
        for _ in range(80):
            try:
                req(port, 'GET', '/api/health')
                break
            except Exception:
                time.sleep(0.25)

        st, txt = req(port, 'POST', '/api/write',
                      {'book': '示例书', 'chapter': '009', 'prompt': '写第九章'})
        ok = st == 400 and '前置检查未通过' in txt and 'precheck.no_outline' in txt
        bad += 0 if ok else 1
        print('  %s  缺大纲 → 400 且带 screen' % ('PASS' if ok else 'FAIL'), '|', txt[:90])

        st, txt = req(port, 'POST', '/api/write',
                      {'book': '示例书', 'chapter': '第三章', 'prompt': '写'})
        ok = st == 400 and 'precheck.chapter_no' in txt
        bad += 0 if ok else 1
        print('  %s  章号非法 → 400' % ('PASS' if ok else 'FAIL'), '|', txt[:90])

        st, txt = req(port, 'POST', '/api/write',
                      {'book': '示例书', 'chapter': '005', 'prompt': '写'})
        ok = st == 400 and 'precheck.placeholder' in txt
        bad += 0 if ok else 1
        print('  %s  占位残留 → 400' % ('PASS' if ok else 'FAIL'), '|', txt[:90])
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    return bad


def main():
    d = tempfile.mkdtemp(prefix='pi-')
    book = os.path.join(d, 'projects', '示例书')
    os.makedirs(os.path.join(book, '大纲'))
    os.makedirs(os.path.join(book, '章节'))
    open(os.path.join(book, '大纲', '003-赎当.md'), 'w', encoding='utf-8').write(GOOD)
    open(os.path.join(book, '大纲', '004-一句话.md'), 'w', encoding='utf-8').write(
        '| 004 | 他想赎当 | [推测] | 规则二 |\n')
    open(os.path.join(book, '大纲', '005-占位.md'), 'w', encoding='utf-8').write(
        '<details>\n**场次**\nTODO 待补\n</details>\n')

    print('=== A 单元 ===')
    bad = unit(d)
    print('=== B 集成 ===')
    bad += integration(d)

    print('=== C 两模块不互相覆盖 ===')
    ok = os.path.isfile(os.path.join(ROOT, 'core', 'precheck.py')) and \
        'def precheck(' in open(os.path.join(ROOT, 'core', 'precheck.py'), encoding='utf-8').read()
    bad += 0 if ok else 1
    print('  %s  precheck.py 仍是写后机检（def precheck 在）' % ('PASS' if ok else 'FAIL'))

    shutil.rmtree(d, ignore_errors=True)
    print('\n结果: %s（失败 %d）' % ('PASS' if bad == 0 else 'FAIL', bad))
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
