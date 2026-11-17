#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大纲 / 设定库专用 API 验收（v1.0.1 第 3 项）。

覆盖：
  E1  GET  /api/entries          outline/settings 由 missing 变 wired，evidence_route 非空
  O1  GET  /api/outline?book     列目录（全书大纲 + 章纲），带标题与字数
  O2  GET  /api/outline?book&name=009-...  读单篇 + check（合规 -> ok=true）
  O3  GET  不合规章纲            check.ok=false，issues 里点名缺哪块
  O4  POST 不合规章纲            400，且文件没被改写
  O5  POST 不合规 + force=true   200（人工确认后能存）
  O6  POST 合规章纲              200，落盘内容一致
  S1  GET  /api/settings?book    列设定库
  S2  POST /api/settings         写角色卡成功
  X1  name 带 ..                 400
  X2  不存在的书                 400（书名校验）或 404
  X3  GET /api/outline 无 book   400 且不是 501

用法：python scripts/_verify_entries_api.py
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
BOOK = '_apitest'

GOOD_OUTLINE = """<details>
<summary>009 分场章纲</summary>

**场次**

| 场 | 地点·时辰 | 发生什么 | 约字数 |
|---|---|---|---|
| 场1 | 当铺门口·晨 | 他在门槛外停住，低头看——空的 | 400 |
| 场2 | 当铺柜台·晨 | 他要赎当，老头推来木牌 | 1200 |

**合计 1600 字**

**必须做到的事**

1. 甲必须先摸一次怀里那根白线，再开口说「赎」
2. 老头必须把木牌推过来，牌上出现三样刻字
3. 「有人买」必须是老头原话，且不许再解释一句

**本章推进**

- **P-006 门槛外的旧草鞋**（推进：他在门槛外找不到，问老头）

**不许做**

- 不许出现赵老四、乙、老汉（本章他们都不在场）

**文风锚点**

- 短句为主，一段不超过 100 字
</details>
"""

BAD_OUTLINE = """<details>
<summary>010 分场章纲</summary>

**场次**

| 场 | 地点·时辰 | 发生什么 | 约字数 |
|---|---|---|---|
| 场1 | 当铺柜台·晨 | 他要赎当 | 1200 |

**必须做到的事**

1. 要写得有张力

</details>
"""


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(port, method, path, body=None):
    path = quote(path, safe='/?=&%')
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    h = {'Host': '127.0.0.1:%d' % port, 'Content-Type': 'application/json'}
    data = json.dumps(body).encode('utf-8') if body is not None else None
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
    try:
        return r.status, json.loads(txt)
    except Exception:
        return r.status, {'_raw': txt[:300]}


def main():
    d = tempfile.mkdtemp(prefix='nvl-api-')
    proj = os.path.join(d, 'projects', BOOK)
    os.makedirs(os.path.join(proj, '章节'))
    os.makedirs(os.path.join(proj, '大纲'))
    os.makedirs(os.path.join(proj, '设定库'))
    open(os.path.join(proj, '章节', '001-a.md'), 'w', encoding='utf-8').write('# 一\n\n正文\n')
    open(os.path.join(proj, '大纲', '全书大纲.md'), 'w', encoding='utf-8').write(
        '# 全书大纲\n\n| 009 | 赎当 | [推测] | 规则第二条 |\n')
    open(os.path.join(proj, '大纲', '009-赎当.md'), 'w', encoding='utf-8').write(GOOD_OUTLINE)
    open(os.path.join(proj, '设定库', '角色.md'), 'w', encoding='utf-8').write('# 角色\n\n- 甲\n')

    port = free_port()
    env = dict(os.environ)
    env['NOVELAPP_DATA'] = d
    env.pop('NOVELAPP_BACKEND_TOKEN', None)
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'core', 'server.py'), str(port), '--no-browser'],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    fails = []

    def check(name, cond, detail=''):
        print(('PASS  ' if cond else 'FAIL  ') + name + ('  ' + detail if detail else ''))
        if not cond:
            fails.append(name)

    try:
        for _ in range(80):
            try:
                req(port, 'GET', '/api/health')
                break
            except Exception:
                time.sleep(0.25)

        # E1 入口状态
        st, j = req(port, 'GET', '/api/entries')
        rows = {e['key']: e for e in (j.get('entries') or [])}
        ok_o = rows.get('outline', {})
        ok_s = rows.get('settings', {})
        check('E1 outline 变 wired 且有 evidence',
              ok_o.get('state') == 'wired' and ok_o.get('evidence_route') == '/api/outline',
              'state=%s route=%s' % (ok_o.get('state'), ok_o.get('evidence_route')))
        check('E1 settings 变 wired 且有 evidence',
              ok_s.get('state') == 'wired' and ok_s.get('evidence_route') == '/api/settings',
              'state=%s route=%s' % (ok_s.get('state'), ok_s.get('evidence_route')))

        # O1 列目录
        st, j = req(port, 'GET', '/api/outline?book=' + BOOK)
        names = [f['name'] for f in (j.get('files') or [])]
        check('O1 列大纲 200 且含两篇',
              st == 200 and j.get('count') == 2 and '009-赎当.md' in names and '全书大纲.md' in names,
              'status=%d files=%s' % (st, names))

        # O2 读合规章纲
        st, j = req(port, 'GET', '/api/outline?book=%s&name=009-赎当.md' % BOOK)
        ck = j.get('check') or {}
        check('O2 读章纲 200 且 check.ok=true',
              st == 200 and ck.get('ok') is True and ck.get('scenes') == 2,
              'status=%d ok=%s scenes=%s' % (st, ck.get('ok'), ck.get('scenes')))

        # O3 不合规章纲的 check
        open(os.path.join(proj, '大纲', '010-坏.md'), 'w', encoding='utf-8').write(BAD_OUTLINE)
        st, j = req(port, 'GET', '/api/outline?book=%s&name=010-坏.md' % BOOK)
        ck = j.get('check') or {}
        codes = [i['code'] for i in (ck.get('issues') or [])]
        check('O3 不合规章纲 check.ok=false 且点名缺项',
              st == 200 and ck.get('ok') is False and 'outline.too-few-scenes' in codes
              and 'outline.must-too-few' in codes and 'outline.no-forbid' in codes,
              'codes=%s' % codes)

        # O4 写不合规章纲 -> 400 且不落盘
        before = open(os.path.join(proj, '大纲', '010-坏.md'), encoding='utf-8').read()
        st, j = req(port, 'POST', '/api/outline',
                    {'book': BOOK, 'name': '010-坏.md', 'content': BAD_OUTLINE + '\n又被改了一次\n'})
        after = open(os.path.join(proj, '大纲', '010-坏.md'), encoding='utf-8').read()
        check('O4 不合规章纲被挡 400', st == 400 and j.get('error') == '章纲不合格，没有写入',
              'status=%d error=%s' % (st, j.get('error')))
        check('O4 文件未被改写', before == after, 'unchanged=%s' % (before == after))

        # O5 force 绕过
        st, j = req(port, 'POST', '/api/outline',
                    {'book': BOOK, 'name': '010-坏.md', 'content': BAD_OUTLINE + '\n又被改了一次\n',
                     'force': True})
        check('O5 force=true 允许保存', st == 200 and j.get('ok') is True, 'status=%d' % st)

        # O6 保存合规章纲
        st, j = req(port, 'POST', '/api/outline',
                    {'book': BOOK, 'name': '011-新章.md', 'content': GOOD_OUTLINE})
        disk = open(os.path.join(proj, '大纲', '011-新章.md'), encoding='utf-8').read() \
            if os.path.exists(os.path.join(proj, '大纲', '011-新章.md')) else ''
        check('O6 合规章纲保存 200 且落盘一致',
              st == 200 and disk == GOOD_OUTLINE, 'status=%d disk_ok=%s' % (st, disk == GOOD_OUTLINE))

        # S1 列设定库
        st, j = req(port, 'GET', '/api/settings?book=' + BOOK)
        check('S1 列设定库 200 且含角色.md',
              st == 200 and any(f['name'] == '角色.md' for f in (j.get('files') or [])),
              'status=%d files=%s' % (st, [f['name'] for f in (j.get('files') or [])]))

        # S2 写设定
        st, j = req(port, 'POST', '/api/settings',
                    {'book': BOOK, 'name': '势力.md', 'content': '# 势力\n\n- 当铺\n'})
        check('S2 写设定库 200', st == 200 and j.get('ok') is True, 'status=%d' % st)

        # X1 越界 name
        st, j = req(port, 'GET', '/api/outline?book=%s&name=../../etc/passwd.md' % BOOK)
        check('X1 name 带 .. -> 400', st == 400, 'status=%d' % st)

        # X2 不存在的书
        st, j = req(port, 'GET', '/api/outline?book=__nobook__')
        check('X2 不存在的书 -> exists=false 而非 500',
              st == 200 and j.get('exists') is False, 'status=%d exists=%s' % (st, j.get('exists')))

        # X3 无参数
        st, j = req(port, 'GET', '/api/outline')
        check('X3 无 book -> 400 且不是 501', st == 400 and j.get('ok') is False,
              'status=%d' % st)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(d, ignore_errors=True)

    print('\n结果: %s（失败 %d）' % ('PASS' if not fails else 'FAIL', len(fails)))
    if fails:
        print('失败项: ' + ' | '.join(fails))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
