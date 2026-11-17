#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N1/N2 红队 PoC（先红后绿）。

覆盖五项：
  N1  Host 头伪造（DNS rebinding）           -> 期望 403
  N2  跨站 Origin + text/plain 写文件（CSRF） -> 期望 403 且不落地
  N3  /api/chat 无令牌                       -> 期望 401
  N4  /api/tree?path=.. 目录穿越              -> 期望 400
  N5  Content-Type 不是 application/json 的写 -> 期望 403/415

同时跑四条回归，确认修复不伤正常调用。

用法：
  python scripts/_poc_n1n2.py            # 退出码 0 全绿，非 0 有红
"""
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOK = '_pocbook'
REL = 'projects/%s/章节/001-poc.md' % BOOK


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(port, method, path, body=None, headers=None, raw=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    h = {'Content-Type': 'application/json'}
    if headers:
        h.update(headers)
    if raw is not None:
        data = raw
    elif body is not None:
        data = json.dumps(body).encode('utf-8')
    else:
        data = None
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    for k, v in h.items():
        conn.putheader(k, v)
    if data is not None:
        conn.putheader('Content-Length', str(len(data)))
    conn.endheaders()
    if data is not None:
        conn.send(data)
    r = conn.getresponse()
    txt = r.read().decode('utf-8', 'ignore')
    st = r.status
    conn.close()
    return st, txt


def main():
    data_dir = tempfile.mkdtemp(prefix='nvl-poc-')
    proj = os.path.join(data_dir, 'projects', BOOK)
    os.makedirs(os.path.join(proj, '章节'))
    os.makedirs(os.path.join(proj, '设定库'))
    target = os.path.join(proj, '章节', '001-poc.md')
    with open(target, 'w', encoding='utf-8') as f:
        f.write('# PoC\n\n原始内容\n')

    port = free_port()
    env = dict(os.environ)
    env['NOVELAPP_DATA'] = data_dir
    env.pop('NOVELAPP_BACKEND_TOKEN', None)

    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, 'core', 'server.py'), str(port), '--no-browser'],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    results = []

    def check(name, cond, detail=''):
        results.append((name, bool(cond), detail))
        print(('PASS  ' if cond else 'FAIL  ') + name + ('  ' + detail if detail else ''))

    try:
        up = False
        for _ in range(80):
            try:
                st, _ = req(port, 'GET', '/api/health',
                            headers={'Host': '127.0.0.1:%d' % port})
                up = True
                break
            except Exception:
                time.sleep(0.25)
        check('0 后端启动', up, 'port=%d' % port)
        if not up:
            return 1

        good = {'Host': '127.0.0.1:%d' % port}

        # ---- N1 Host 伪造 ----
        st, _ = req(port, 'GET', '/api/config', headers={'Host': 'evil.example'})
        check('N1 Host: evil.example GET /api/config -> 403', st == 403, 'status=%d' % st)

        # ---- N2 CSRF：跨站 Origin + text/plain 写文件 ----
        payload = {'path': REL, 'content': '# 被改\n\nCSRF 写入\n'}
        st, _ = req(port, 'POST', '/api/save', body=payload,
                    headers={'Host': '127.0.0.1:%d' % port,
                             'Origin': 'https://evil.example',
                             'Content-Type': 'text/plain'})
        on_disk = open(target, encoding='utf-8').read()
        touched = 'CSRF' in on_disk
        check('N2 跨站 Origin + text/plain -> 403', st == 403, 'status=%d' % st)
        check('N2 文件未被改写', not touched, 'touched=%s' % touched)

        # ---- N2b 同源 Origin 仍应放行（回归） ----
        ok_body = {'path': REL, 'content': '# 正常\n\n同源写入\n'}
        st, _ = req(port, 'POST', '/api/save', body=ok_body,
                    headers={'Host': '127.0.0.1:%d' % port,
                             'Origin': 'http://127.0.0.1:%d' % port})
        disk = open(target, encoding='utf-8').read()
        check('R1 同源 Origin POST /api/save -> 200 且落盘',
              st == 200 and '同源写入' in disk, 'status=%d disk_ok=%s' % (st, '同源写入' in disk))

        # ---- N2c 无 Origin（curl / 本机脚本）仍应放行 ----
        st, _ = req(port, 'POST', '/api/save', body={'path': REL, 'content': '# 无 Origin\n'},
                    headers={'Host': '127.0.0.1:%d' % port})
        check('R2 无 Origin POST /api/save -> 200', st == 200, 'status=%d' % st)

        # ---- N3 /api/chat 无令牌 ----
        st, _ = req(port, 'POST', '/api/chat', body={'messages': [{'role': 'user', 'content': 'hi'}]},
                    headers={'Host': '127.0.0.1:%d' % port})
        check('N3 POST /api/chat 无令牌 -> 401', st == 401, 'status=%d' % st)

        # ---- N4 /api/tree?path=.. ----
        st, _ = req(port, 'GET', '/api/tree?path=..',
                    headers={'Host': '127.0.0.1:%d' % port})
        check('N4 GET /api/tree?path=.. -> 400', st == 400, 'status=%d' % st)
        st, _ = req(port, 'GET', '/api/tree?path=projects/%s' % BOOK,
                    headers={'Host': '127.0.0.1:%d' % port})
        check('R3 GET /api/tree?path=projects/<book> -> 200', st == 200, 'status=%d' % st)

        # ---- N5 非 JSON Content-Type 写 ----
        st, _ = req(port, 'POST', '/api/save', raw=b'{"path":"%s","content":"x"}' % REL.encode(),
                    headers={'Host': '127.0.0.1:%d' % port,
                             'Content-Type': 'application/x-www-form-urlencoded'})
        check('N5 POST /api/save 表单 Content-Type -> 403/415', st in (403, 415), 'status=%d' % st)

        # ---- 回归：正常读 ----
        st, txt = req(port, 'GET', '/api/config', headers=good)
        check('R4 GET /api/config 正常 Host -> 200', st == 200, 'status=%d' % st)
        st, txt = req(port, 'GET', '/api/tree', headers=good)
        try:
            j = json.loads(txt)
        except Exception:
            j = {}
        check('R5 GET /api/tree 正常 -> 200 且有树',
              st == 200 and bool(j.get('tree')), 'status=%d tree=%s' % (st, bool(j.get('tree'))))

        # ---- N6 页面令牌注入不自伤（变量名不能被占位符替换误伤） ----
        st, page = req(port, 'GET', '/', headers=good)
        mt = re.search(r"var TK = '([^']*)'", page)
        tok = mt.group(1) if mt else ''
        check('N6 页面注入令牌 -> nvls- 前缀',
              st == 200 and tok.startswith('nvls-'), 'status=%d tk=%s' % (st, tok[:10]))
        check('N6 变量名未被替换（无 window.nvls- 残骸）',
              'window.nvls-' not in page and 'window.__NVL_TOKEN__ = TK' in page,
              'clean=%s' % ('window.nvls-' not in page))
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(data_dir, ignore_errors=True)

    passed = sum(1 for _, okk, _ in results if okk)
    total = len(results)
    print()
    print('结果: %d/%d PASS' % (passed, total))
    red = [n for n, okk, _ in results if not okk]
    if red:
        print('未修: ' + ' | '.join(red))
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
