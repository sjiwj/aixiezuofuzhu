#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 tag 建 GitHub Release（幂等：已存在就报现有 URL，不重复创建）。

用法：python scripts/_create_release.py v1.0.1 release/1.0.1.md [--draft]

token 从 git credential（Windows 凭据管理器）取，不打印、不落盘。
仓库地址从 git remote origin 解析。
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args, **kw):
    return subprocess.run(['git', '-C', ROOT] + list(args), capture_output=True, text=True, **kw)


def owner_repo():
    url = git('remote', 'get-url', 'origin').stdout.strip()
    m = re.search(r'github\.com[:/]([^/]+)/(.+?)(?:\.git)?$', url)
    if not m:
        raise SystemExit('无法从 remote 解析 owner/repo：%s' % url)
    return m.group(1), m.group(2)


def token():
    cred = subprocess.run(['git', '-C', ROOT, 'credential', 'fill'],
                          input='protocol=https\nhost=github.com\n\n',
                          capture_output=True, text=True)
    for line in cred.stdout.splitlines():
        if line.startswith('password='):
            return line[len('password='):]
    raise SystemExit('凭据管理器里没有 github.com 的口令，先跑 _auth_device_flow.py')


def api(method, path, tok, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request('https://api.github.com' + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + tok,
                                          'Accept': 'application/vnd.github+json',
                                          'X-GitHub-Api-Version': '2022-11-28',
                                          'Content-Type': 'application/json',
                                          'User-Agent': 'novelapp-release'})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        return e.code, {'raw': body[:400]}


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    tag, notes_path = sys.argv[1], sys.argv[2]
    draft = '--draft' in sys.argv
    if not os.path.isfile(os.path.join(ROOT, notes_path)):
        raise SystemExit('找不到说明文件：%s' % notes_path)
    with open(os.path.join(ROOT, notes_path), encoding='utf-8') as f:
        body = f.read()
    if len(body) > 120000:
        raise SystemExit('说明过长（%d 字符），GitHub 上限 125000' % len(body))

    tok = token()
    owner, repo = owner_repo()

    st, cur = api('GET', '/repos/%s/%s/releases/tags/%s' % (owner, repo, tag), tok)
    if st == 200:
        print('ALREADY_EXISTS=%s' % cur.get('html_url'))
        return 0

    st, res = api('POST', '/repos/%s/%s/releases' % (owner, repo), tok, {
        'tag_name': tag,
        'name': tag,
        'body': body,
        'draft': draft,
        'prerelease': False,
    })
    if st not in (200, 201):
        print('FAIL status=%s %s' % (st, json.dumps(res, ensure_ascii=False)[:400]))
        return 1
    print('CREATED=%s' % res.get('html_url'))
    print('release_id=%s draft=%s tag=%s' % (res.get('id'), res.get('draft'), res.get('tag_name')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
