#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""鉴权回归：验证 NOVELAPP_BACKEND_TOKEN 生效且不伤既有逻辑

背景：regression_p0.py 起后端时没设 token，只跑了"无鉴权"分支。
      本脚本专门验证"配了 token 之后"的行为。

断言 7 项，任一失败退出码非 0。
"""
import http.client, json, os, socket, subprocess, sys, tempfile, time, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = 'nvl-regress-' + str(int(time.time()))


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(port, method, path, body=None, token=None, timeout=8):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
    headers = {'Content-Type': 'application/json'}
    if token is not None:
        headers['X-Novelapp-Token'] = token
    data = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=data, headers=headers)
    r = conn.getresponse()
    text = r.read().decode('utf-8', 'ignore')
    conn.close()
    return r.status, text


def main():
    data_dir = tempfile.mkdtemp(prefix='nvl-auth-')
    proj = os.path.join(data_dir, 'projects', '_authtest')
    os.makedirs(os.path.join(proj, '章节'))
    os.makedirs(os.path.join(proj, '设定库'))
    with open(os.path.join(proj, '章节', '001-t.md'), 'w', encoding='utf-8') as f:
        f.write('# 测试\n\n正文一百字左右。\n')

    port = free_port()
    env = dict(os.environ)
    env['NOVELAPP_DATA'] = data_dir
    env['NOVELAPP_BACKEND_TOKEN'] = TOKEN

    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, 'core', 'server.py'), str(port), '--no-browser'],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    results = []
    def check(name, cond, detail=''):
        results.append((name, bool(cond), detail))
        print(('PASS  ' if cond else 'FAIL  ') + name + ('  ' + detail if detail else ''))

    try:
        # 等端口就绪（但不能用带鉴权的探测，所以先无 token 探测到有响应即可）
        ok = False
        for _ in range(60):
            try:
                st, _ = req(port, 'GET', '/api/health')
                ok = True
                break
            except Exception:
                time.sleep(0.25)
        check('1 后端启动', ok, 'port=%d' % port)
        if not ok:
            return 1

        # 2 无 token → 401
        st, _ = req(port, 'GET', '/api/tree')
        check('2 无 token GET /api/tree → 401', st == 401, 'status=%d' % st)

        # 3 正确 token → 200 且 tree 非空
        st, txt = req(port, 'GET', '/api/tree', token=TOKEN)
        try:
            j = json.loads(txt)
        except Exception:
            j = {}
        has_tree = bool(j.get('tree'))
        check('3 正确 token GET /api/tree → 200 且 tree 非空',
              st == 200 and has_tree, 'status=%d tree=%s' % (st, has_tree))

        # 4 错误 token → 401
        st, _ = req(port, 'GET', '/api/tree', token='wrong')
        check('4 错误 token → 401', st == 401, 'status=%d' % st)

        # 5 无 token POST → 401
        st, _ = req(port, 'POST', '/api/save',
                    body={'path': 'projects/_authtest/章节/002.md', 'content': 'x'})
        check('5 无 token POST /api/save → 401', st == 401, 'status=%d' % st)

        # 6 正确 token POST → 200 且落盘一致
        content = '鉴权测试正文\n第二行\n'
        st, txt = req(port, 'POST', '/api/save',
                      body={'path': 'projects/_authtest/章节/002.md', 'content': content},
                      token=TOKEN)
        fp = os.path.join(proj, '章节', '002.md')
        on_disk = open(fp, encoding='utf-8').read() if os.path.exists(fp) else None
        check('6 正确 token POST /api/save → 200 且落盘一致',
              st == 200 and on_disk == content, 'status=%d disk_ok=%s' % (st, on_disk == content))

        # 7 越界路径：带 token 也应 400（不是 401，证明顺序正确）
        st, _ = req(port, 'GET', '/api/file?path=../../evil.md', token=TOKEN)
        check('7 越界路径带 token → 400（鉴权先过、路径校验生效）',
              st == 400, 'status=%d' % st)

        # 8 健康接口也要 token（一致性检查）
        st, _ = req(port, 'GET', '/api/health')
        check('8 无 token GET /api/health → 401', st == 401, 'status=%d' % st)

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
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
