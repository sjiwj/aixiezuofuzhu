#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务循环（task_queue）验收。

Q1 建表：章号来自 状态机 ∪ 章节文件 ∪ 大纲；三者都没痕迹的章不会凭空出现
Q2 排序：错题本待办 > 有章纲无正文 > 有正文草稿 > 已定稿（且每条带理由）
Q3 next：跳过定稿，返回分数最高的一条
Q4 HTTP：GET /api/queue 200；POST /api/queue/next 200 且 next.chapter 正确
Q5 边界：无 book → 400；书不存在 → 404；空书（无章节无大纲）→ count=0 而不是 500

用法：python scripts/_verify_queue.py
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
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'core'))

import task_queue as Q     # noqa: E402
import loop_log as LL      # noqa: E402


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
        print('  %s  %-38s %s' % ('PASS' if cond else 'FAIL', label, detail))

    d = tempfile.mkdtemp(prefix='q-')
    proj = os.path.join(d, 'projects')
    book = os.path.join(proj, '示例书')
    os.makedirs(os.path.join(book, '章节'))
    os.makedirs(os.path.join(book, '大纲'))
    open(os.path.join(book, '章节', '001-a.md'), 'w', encoding='utf-8').write('# 一\n\n正文\n')
    open(os.path.join(book, '章节', '002-b.md'), 'w', encoding='utf-8').write('# 二\n\n正文\n')
    open(os.path.join(book, '大纲', '001-a.md'), 'w', encoding='utf-8').write('<details>\n**场次**\n</details>\n')
    open(os.path.join(book, '大纲', '003-c.md'), 'w', encoding='utf-8').write('<details>\n**场次**\n</details>\n')
    json.dump({'002': {'stage': 'done'}},
              open(os.path.join(book, '章节', '.stages.json'), 'w', encoding='utf-8'))
    os.makedirs(os.path.join(proj, '空书', '章节'))

    LL.record('第001章', 'gate_depth', '篇幅不足', cycle='review')

    # Q1/Q2
    r = Q.build_queue('示例书', proj)
    chs = [it['chapter'] for it in r['items']]
    chk('Q1 章号集合 = 001/002/003', chs == ['001', '003', '002'], str(chs))
    chk('Q1 三者无痕迹的章不出现', '004' not in chs)
    chk('Q2 每条都有理由', all(it['reasons'] for it in r['items']))
    chk('Q2 错题本那章排第一', r['items'][0]['chapter'] == '001',
        '%s score=%d' % (r['items'][0]['chapter'], r['items'][0]['score']))
    chk('Q2 定稿排最后', r['items'][-1]['chapter'] == '002',
        '%s score=%d' % (r['items'][-1]['chapter'], r['items'][-1]['score']))
    chk('Q2 counts 分类正确',
        r['counts'].get('done') == 1 and r['counts'].get('missing') == 1, str(r['counts']))

    # Q3
    n = Q.next_item('示例书', proj)
    chk('Q3 next 跳过定稿', bool(n) and n['chapter'] == '001', str((n or {}).get('chapter')))
    chk('Q3 空书 next 为 None', Q.next_item('空书', proj) is None)

    # Q5 只读不炸
    chk('Q5 空书建表 count=0', Q.build_queue('空书', proj)['count'] == 0)

    # Q4 HTTP
    port = free_port()
    env = dict(os.environ)
    env['NOVELAPP_DATA'] = d
    env.pop('NOVELAPP_BACKEND_TOKEN', None)
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'core', 'server.py'),
                             str(port), '--no-browser'],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def req(method, path, body=None):
        path = quote(path, safe='/?=&%')
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

        st, t = req('GET', '/api/queue?book=示例书')
        j = json.loads(t) if t.startswith('{') else {}
        chk('Q4 GET /api/queue 200', st == 200 and j.get('count') == 3,
            'HTTP %d count=%s' % (st, j.get('count')))

        st, t = req('POST', '/api/queue/next', {'book': '示例书'})
        j = json.loads(t) if t.startswith('{') else {}
        chk('Q4 POST /api/queue/next 返回 001',
            st == 200 and (j.get('next') or {}).get('chapter') == '001',
            'HTTP %d next=%s' % (st, (j.get('next') or {}).get('chapter')))

        st, _ = req('GET', '/api/queue')
        chk('Q5 无 book → 400', st == 400, 'HTTP %d' % st)

        st, _ = req('GET', '/api/queue?book=不存在的书')
        chk('Q5 书不存在 → 404', st == 404, 'HTTP %d' % st)
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
