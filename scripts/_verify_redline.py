#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写盘红线（redline）验收。

R1 隐藏路径（.stages.json）篡改 → 403 且磁盘不变
R2 覆盖已定稿章节 → 403；带 force → 200
R3 删除已定稿章节 → 403；带 force → 200 且进 .trash
R4 非定稿章节照常写 → 200
R5 大纲照常写 → 200
C  命令级 check_command：git push 默认拦、publish_flow 上下文放行

用法：python scripts/_verify_redline.py
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

import redline as R      # noqa: E402


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    bad = 0

    def chk(label, cond, detail=''):
        nonlocal bad
        if not cond:
            bad += 1
        print('  %s  %-34s %s' % ('PASS' if cond else 'FAIL', label, detail))

    # C 命令级
    r = R.check_command(['git', 'push', 'origin', 'main'])
    chk('C git push 默认拦', not r['ok'], str([x['code'] for x in r['blocked']]))
    r = R.check_command(['git', 'push', 'origin', 'main'], {'publish_flow': True})
    chk('C publish_flow 放行', r['ok'])
    r = R.check_command(['rm', '-rf', '/data'])
    chk('C rm -rf 拦', not r['ok'], str([x['code'] for x in r['blocked']]))
    r = R.check_command(['python', 'core/server.py', '8770'])
    chk('C 普通命令放行', r['ok'])

    d = tempfile.mkdtemp(prefix='rl-')
    book = os.path.join(d, 'projects', '示例书')
    os.makedirs(os.path.join(book, '章节'))
    os.makedirs(os.path.join(book, '大纲'))
    open(os.path.join(book, '章节', '001-a.md'), 'w', encoding='utf-8').write('# 一\n\n正文\n')
    json.dump({'001': {'stage': 'done'}},
              open(os.path.join(book, '章节', '.stages.json'), 'w', encoding='utf-8'))

    port = free_port()
    env = dict(os.environ)
    env['NOVELAPP_DATA'] = d
    env.pop('NOVELAPP_BACKEND_TOKEN', None)
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'core', 'server.py'),
                             str(port), '--no-browser'],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def req(method, path, body=None):
        c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
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
        t = r.read().decode('utf-8', 'ignore')
        c.close()
        return r.status, t

    try:
        for _ in range(80):
            try:
                req('GET', '/api/health')
                break
            except Exception:
                time.sleep(0.25)

        st, _ = req('POST', '/api/save',
                    {'path': 'projects/示例书/章节/.stages.json',
                     'content': '{"001":{"stage":"draft"}}'})
        disk = open(os.path.join(book, '章节', '.stages.json'), encoding='utf-8').read()
        chk('R1 篡改 .stages.json 被拒', st == 403 and 'done' in disk, 'HTTP %d' % st)

        st, _ = req('POST', '/api/save',
                    {'path': 'projects/示例书/章节/001-a.md', 'content': '# 改坏\n'})
        disk2 = open(os.path.join(book, '章节', '001-a.md'), encoding='utf-8').read()
        chk('R2 覆盖定稿被拒', st == 403 and '改坏' not in disk2, 'HTTP %d' % st)

        st, _ = req('POST', '/api/save',
                    {'path': 'projects/示例书/章节/001-a.md', 'content': '# 定稿改了\n', 'force': True})
        chk('R2 force 放行', st == 200, 'HTTP %d' % st)

        st, _ = req('POST', '/api/file/delete', {'path': 'projects/示例书/章节/001-a.md'})
        chk('R3 删定稿被拒', st == 403 and os.path.isfile(os.path.join(book, '章节', '001-a.md')),
            'HTTP %d' % st)

        st, t = req('POST', '/api/file/delete', {'path': 'projects/示例书/章节/001-a.md', 'force': True})
        chk('R3 force 删（进 trash）', st == 200 and '.trash/' in t, 'HTTP %d' % st)

        open(os.path.join(book, '章节', '002-b.md'), 'w', encoding='utf-8').write('# 二\n\n草稿\n')
        st, _ = req('POST', '/api/save',
                    {'path': 'projects/示例书/章节/002-b.md', 'content': '# 二改\n\n草稿正文\n'})
        chk('R4 非定稿照常写', st == 200, 'HTTP %d' % st)

        st, _ = req('POST', '/api/save',
                    {'path': 'projects/示例书/大纲/全书大纲.md', 'content': '# 全书大纲\n\n| 003 | x |\n'})
        chk('R5 大纲照常写', st == 200, 'HTTP %d' % st)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(d, ignore_errors=True)

    print('\n结果: %s（失败 %d）' % ('PASS' if bad == 0 else 'FAIL', bad))
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
