# -*- coding: utf-8 -*-
"""扫描项目内 JSON 的 key 类字段是否全为空。exit 0 = 全空（可发布）。"""
import io, json, os, sys

ROOT = r'D:\NovelApp'
DIRS = ['config', 'data', '发布', '发布桌面版', 'docs', 'web']
KEYNAMES = {'api_key', 'downstream_key', 'token', 'secret', 'access_token', 'password', 'jwt', 'key'}
bad = []
scanned = 0

for d in DIRS:
    base = os.path.join(ROOT, d)
    if not os.path.isdir(base):
        continue
    for cur, _, files in os.walk(base):
        for fn in files:
            if not fn.lower().endswith('.json'):
                continue
            p = os.path.join(cur, fn)
            try:
                if os.path.getsize(p) > 2 * 1024 * 1024:
                    continue
                data = json.load(io.open(p, encoding='utf-8'))
            except Exception:
                continue
            scanned += 1

            def walk(o, path=''):
                if isinstance(o, dict):
                    for k, v in o.items():
                        if k in KEYNAMES and isinstance(v, str) and v.strip():
                            bad.append('%s::%s.%s(len=%d)' % (os.path.relpath(p, ROOT), path, k, len(v)))
                        walk(v, path + '.' + str(k))
                elif isinstance(o, list):
                    for i, v in enumerate(o):
                        walk(v, '%s[%d]' % (path, i))
            walk(data)

print('scanned_json=%d non_empty=%d' % (scanned, len(bad)))
for b in bad[:20]:
    print('  ' + b)
sys.exit(0 if not bad else 1)
