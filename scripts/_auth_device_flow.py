#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub OAuth 设备授权（device flow）——拿到能 push 的凭据。

背景：本机缓存的 fine-grained PAT 只有读权限，git push 403；GitHub 不允许用 PAT 改 PAT，
网页改权限又需要点一堆复选框。设备流只需用户在已登录的浏览器里确认一次。

用法：
  python scripts/_auth_device_flow.py --start    # 申请 user_code 并打印（5 分钟有效）
  python scripts/_auth_device_flow.py --poll     # 轮询换 token -> 验证身份 -> 验证 push -> 存凭据

说明：
  - 用 GitHub CLI 的公开 client_id（授权页显示的是 GitHub CLI，不是本项目）。
  - scope 只要 repo（读写仓库）。
  - token 不打印、不写明文文件；成功后用 git credential approve 存进 Windows 凭据管理器。
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

CLIENT_ID = '178c6fc778ccc68e1d6a'          # GitHub CLI 的公开 client_id
SCOPE = 'repo'
STATE = os.path.join(tempfile.gettempdir(), 'gh_device_flow.json')


def post(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={'Accept': 'application/json',
                                          'User-Agent': 'novelapp-token-fix'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        raise SystemExit('HTTP %s: %s' % (e.code, body[:200]))


def start():
    r = post('https://github.com/login/device/code',
             {'client_id': CLIENT_ID, 'scope': SCOPE})
    if 'device_code' not in r:
        raise SystemExit('申请失败: %s' % json.dumps(r, ensure_ascii=False)[:300])
    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump({'device_code': r['device_code'],
                   'interval': r.get('interval', 5),
                   'expires_at': time.time() + r.get('expires_in', 900)}, f)
    print('VERIFY_URL=%s' % r['verification_uri'])
    print('USER_CODE=%s' % r['user_code'])
    print('EXPIRES_IN=%s' % r.get('expires_in', 900))
    print('STATE=%s' % STATE)


def poll():
    if not os.path.isfile(STATE):
        raise SystemExit('没有待办授权，先跑 --start')
    with open(STATE, encoding='utf-8') as f:
        st = json.load(f)
    interval = int(st.get('interval', 5))
    deadline = st.get('expires_at', time.time() + 900)
    token = ''
    while time.time() < deadline:
        time.sleep(interval)
        r = post('https://github.com/login/oauth/access_token',
                 {'client_id': CLIENT_ID,
                  'device_code': st['device_code'],
                  'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'})
        if r.get('access_token'):
            token = r['access_token']
            break
        err = r.get('error')
        if err == 'authorization_pending':
            print('.', end='', flush=True)
            continue
        if err == 'slow_down':
            interval += 5
            continue
        raise SystemExit('\n授权失败: %s %s' % (err, r.get('error_description', '')))
    if not token:
        raise SystemExit('\n超时：设备码过期，重新跑 --start')
    os.remove(STATE)
    print('\n拿到 token: 长度=%d 前缀=%s' % (len(token), token[:4]))

    # 1) 验证身份
    req = urllib.request.Request('https://api.github.com/user',
                                 headers={'Authorization': 'Bearer ' + token,
                                          'Accept': 'application/vnd.github+json',
                                          'User-Agent': 'novelapp-token-fix'})
    with urllib.request.urlopen(req, timeout=25) as r:
        me = json.loads(r.read().decode())
    print('身份: %s' % me.get('login'))

    # 2) 验证 push 权限（dry-run，不改远端）
    user = me.get('login') or 'x-access-token'
    basic = base64.b64encode(('%s:%s' % (user, token)).encode()).decode()
    p = subprocess.run(
        ['git', '-C', os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
         '-c', 'credential.helper=',
         '-c', 'http.https://github.com/.extraheader=AUTHORIZATION: basic ' + basic,
         'push', '--dry-run', 'origin', 'main'],
        capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip().splitlines()
    tail = out[-2:] if out else []
    print('push 验证: exit=%d %s' % (p.returncode, ' | '.join(tail)))
    if p.returncode != 0:
        raise SystemExit('push 仍然失败，token 权限不足')

    # 3) 存进凭据管理器（加密存储；口令经 stdin 传，不进命令行）
    cred = 'protocol=https\nhost=github.com\nusername=%s\npassword=%s\n\n' % (user, token)
    q = subprocess.run(['git', 'credential', 'approve'], input=cred,
                       capture_output=True, text=True)
    print('凭据已保存: %s' % ('ok' if q.returncode == 0 else '失败 ' + q.stderr[:120]))
    print('READY=1')


if __name__ == '__main__':
    if '--start' in sys.argv:
        start()
    elif '--poll' in sys.argv:
        poll()
    else:
        print(__doc__)
