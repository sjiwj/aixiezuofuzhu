#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错误普通话化验收（v1.0.1 第 2 项）。

三道断言：
  A  映射表：12 种常见异常翻成中文，且不含英文异常类名
  B  源码：server.py 里 type(e).__name__ 只允许出现在日志行（_log / _f.write）
  C  线上：起后端打一圈接口，任何响应体都不许出现英文异常类名

用法：python scripts/_verify_err_msgs.py
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
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'core'))

import errors as E                                    # noqa: E402

EN_ERR = re.compile(r'\b(KeyError|TypeError|ValueError|JSONDecodeError|AttributeError|'
                    r'IndexError|OSError|FileNotFoundError|PermissionError|URLError|'
                    r'HTTPError|TimeoutError|ConnectionError|UnicodeDecodeError|'
                    r'ZeroDivisionError|StopIteration|RuntimeError)\b')
CJK = re.compile(r'[\u4e00-\u9fff]')

CASES = [
    (KeyError('title'), '数据里缺字段', '标题缺字段类'),
    (IndexError('list index out of range'), '数据条数对不上', '越界'),
    (FileNotFoundError(2, 'No such file', 'D:/x/001.md'), 'file', '文件不存在'),
    (PermissionError(13, 'Permission denied'), '没有权限', '权限'),
    (IsADirectoryError(21, 'Is a directory'), '目录', '是目录'),
    (UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid'), 'UTF-8', '编码'),
    (TimeoutError('timed out'), '超时', '超时'),
    (ValueError('请求体不是合法 JSON'), '请求体不是合法 JSON', '中文 ValueError 直用'),
    (ValueError('invalid literal for int()'), '参数不合法', '英文 ValueError 泛化'),
    (TypeError("'NoneType' object is not subscriptable"), '数据类型对不上', '类型'),
    (AttributeError("'dict' object has no attribute 'x'"), '取错了对象', '属性'),
    (Exception('boom'), '未知错误', '兜底'),
]


def check_mapping():
    bad = 0
    for e, expect, label in CASES:
        got = E.human(e)
        ok = (expect in got) if expect != 'file' else ('文件不存在' in got)
        clean = not EN_ERR.search(got)
        if not (ok and clean):
            bad += 1
        print('%s  %-22s -> %s' % ('PASS' if ok and clean else 'FAIL', label, got))
    with_action = E.human(KeyError('x'), '保存')
    ok = with_action.startswith('保存失败') and not EN_ERR.search(with_action)
    print('%s  %-22s -> %s' % ('PASS' if ok else 'FAIL', '带动作前缀', with_action))
    return bad + (0 if ok else 1)


def check_source():
    src = open(os.path.join(ROOT, 'core', 'server.py'), encoding='utf-8').read()
    lines = src.splitlines()
    bad = []
    for i, line in enumerate(lines, 1):
        if 'type(' in line and '__name__' in line:
            # 续行也要看：向上 3 行内出现 _log( / _f.write 就算日志
            window = '\n'.join(lines[max(0, i - 4):i])
            if '_log(' in window or '_f.write' in window:
                continue
            bad.append((i, line.strip()[:110]))
    for i, line in bad:
        print('FAIL  界面出口仍有英文类名  server.py:%d  %s' % (i, line))
    if not bad:
        print('PASS  server.py 里 type(...).__name__ 只剩日志行')
    return len(bad)


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(port, method, path, body=None, headers=None):
    # 中文路径必须百分号编码，否则 http.client 用 ascii 编码请求行会抛
    path = quote(path, safe='/?=&%')
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    h = {'Host': '127.0.0.1:%d' % port, 'Content-Type': 'application/json'}
    h.update(headers or {})
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


def check_live():
    d = tempfile.mkdtemp(prefix='nvl-err-')
    book = os.path.join(d, 'projects', '_errtest')
    os.makedirs(os.path.join(book, '章节'))
    os.makedirs(os.path.join(book, '设定库'))
    open(os.path.join(book, '章节', '001-a.md'), 'w', encoding='utf-8').write('# t\n\n正文\n')
    open(os.path.join(book, '章节', '.stages.json'), 'w', encoding='utf-8').write('{坏掉')

    port = free_port()
    env = dict(os.environ)
    env['NOVELAPP_DATA'] = d
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'core', 'server.py'), str(port), '--no-browser'],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    hits = []
    try:
        for _ in range(80):
            try:
                req(port, 'GET', '/api/health')
                break
            except Exception:
                time.sleep(0.25)

        probes = [
            ('GET', '/api/tree'),
            ('GET', '/api/config'),
            ('GET', '/api/stats?path=projects/_errtest'),
            ('GET', '/api/file?path=projects/_errtest/章节/001-a.md'),
            ('GET', '/api/stages?book=_errtest'),
            ('GET', '/api/history?book=_errtest&chapter=001'),
            ('GET', '/api/history/diff?book=_errtest&chapter=001'),
            ('GET', '/api/qc?path=projects/_errtest/章节/001-a.md'),
            ('GET', '/api/debt?book=_errtest'),
            ('GET', '/api/completion?book=_errtest'),
            ('GET', '/api/shelf?book=_errtest'),
            ('GET', '/api/usage/summary?days=7'),
            ('GET', '/api/layers?book=_errtest&chapter=001'),
            ('GET', '/api/gate?book=_errtest&chapter=001'),
            ('POST', '/api/save', {'path': 'projects/_errtest/章节/002.md', 'content': '# n\n'}),
            ('POST', '/api/save', {'path': 'projects/_errtest/章节', 'content': 'x'}),      # 路径是目录
            ('POST', '/api/project', {'name': '_errtest2'}),
            ('POST', '/api/file/new', {'path': 'projects/_errtest/章节/003.md'}),
            ('POST', '/api/scene-tag', {'book': '_errtest', 'chapter': '001'}),
            ('POST', '/api/ai-detect', {'book': '_errtest', 'chapter': '001', 'text': ''}),
            ('POST', '/api/ai-detect/text', {'text': ''}),
            ('POST', '/api/breakdown/import', {'path': 'projects/_errtest/章节/001-a.md'}),
            ('GET', '/api/planning/status?book=_errtest'),
            ('POST', '/api/planning/step', {'book': '_errtest', 'sid': '99'}),
            ('POST', '/api/review/config', {'book': '_errtest', 'chapter': '001'}),
            ('GET', '/api/nonexistent'),
        ]
        for p in probes:
            method, path = p[0], p[1]
            body = p[2] if len(p) > 2 else None
            try:
                st, txt = req(port, method, path, body)
            except Exception as e:
                print('FAIL  请求本身炸了 %s %s -> %s' % (method, path, e))
                hits.append(path)
                continue
            m = EN_ERR.search(txt)
            if m:
                print('FAIL  %s %s -> HTTP %d 含英文异常名 %r: %s'
                      % (method, path, st, m.group(0), txt[:160]))
                hits.append(path)
            else:
                print('PASS  %s %-56s HTTP %-3d %s' % (method, path, st, txt[:50].replace('\n', ' ')))
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(d, ignore_errors=True)
    return len(hits)


def main():
    print('=== A 映射表 ===')
    a = check_mapping()
    print('\n=== B 源码 ===')
    b = check_source()
    print('\n=== C 线上响应 ===')
    c = check_live()
    total = a + b + c
    print('\n结果: %s（失败 %d）' % ('PASS' if total == 0 else 'FAIL', total))
    return 0 if total == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
