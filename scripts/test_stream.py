# -*- coding: utf-8 -*-
"""流式输出验证脚本（独立于 app，直接打网关）

用法:
    python scripts/test_stream.py                       # 流式（默认）
    python scripts/test_stream.py --no-stream           # 同步对照
    python scripts/test_stream.py --model deepseek-v4-pro --prompt "数到五"
    python scripts/test_stream.py --key sk-xxx          # 不传则读 config / user_token
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def gateway_base():
    try:
        with open(os.path.join(ROOT, 'config', 'coordinator.json'), encoding='utf-8') as f:
            cfg = json.load(f)
        base = (cfg.get('gateway') or {}).get('base')
        if base:
            return base.rstrip('/')
    except Exception:
        pass
    return 'http://127.0.0.1:3000/v1'


def read_key(explicit=None):
    if explicit:
        return explicit
    env = os.environ.get('NOVELAPP_DOWNSTREAM_KEY')
    if env and os.environ.get('NOVELAPP_ALLOW_DEV_KEY') == '1':
        return env
    paths = [
        os.path.join(os.environ.get('APPDATA', ''), 'novelapp-desktop', 'data', 'config', 'user_token.json'),
        os.path.join(ROOT, 'config', 'user_token.json'),
    ]
    for p in paths:
        try:
            with open(p, encoding='utf-8') as f:
                d = json.load(f)
            k = d.get('token') or d.get('key')
            if k:
                return k
        except Exception:
            continue
    return ''


def run(stream, model, prompt, key, base, max_tokens):
    body = {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': max_tokens, 'temperature': 0.3}
    if stream:
        body['stream'] = True
        body['stream_options'] = {'include_usage': True}
    req = urllib.request.Request(
        base + '/chat/completions', data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key},
        method='POST')

    t0 = time.time()
    first = None
    chunks = 0
    text = ''
    reasoning = ''
    usage = None
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            if not stream:
                data = json.loads(r.read().decode('utf-8', 'replace'))
                text = (data['choices'][0]['message'].get('content') or '')
                usage = data.get('usage') or {}
                return {'ok': True, 'text': text, 'usage': usage, 'first_ms': None,
                        'total_ms': int((time.time() - t0) * 1000), 'chunks': 0}
            for raw in r:
                line = raw.decode('utf-8', 'replace').strip()
                if not line.startswith('data:'):
                    continue
                payload = line[5:].strip()
                if payload == '[DONE]':
                    break
                try:
                    obj = json.loads(payload)
                except ValueError:
                    continue
                if obj.get('usage'):
                    usage = obj['usage']
                for ch in obj.get('choices') or []:
                    d = ch.get('delta') or {}
                    piece = d.get('content') or ''
                    reasoning += d.get('reasoning_content') or ''
                    if piece:
                        if first is None:
                            first = int((time.time() - t0) * 1000)
                        text += piece
                        chunks += 1
                if obj.get('error'):
                    return {'ok': False, 'error': str(obj['error'])[:200], 'text': text,
                            'first_ms': first, 'total_ms': int((time.time() - t0) * 1000),
                            'chunks': chunks, 'usage': usage}
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = e.read().decode('utf-8', 'replace')[:200]
        except Exception:
            pass
        return {'ok': False, 'error': 'HTTP %s %s' % (e.code, detail), 'text': text,
                'first_ms': first, 'total_ms': int((time.time() - t0) * 1000), 'chunks': chunks}
    except Exception as e:
        return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e), 'text': text,
                'first_ms': first, 'total_ms': int((time.time() - t0) * 1000), 'chunks': chunks}
    return {'ok': True, 'text': text, 'usage': usage or {}, 'first_ms': first,
            'total_ms': int((time.time() - t0) * 1000), 'chunks': chunks,
            'reasoning_chars': len(reasoning)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stream', dest='stream', action='store_true', default=True)
    ap.add_argument('--no-stream', dest='stream', action='store_false')
    ap.add_argument('--model', default='deepseek-flash')
    ap.add_argument('--prompt', default='用三句话描写一场雾。')
    ap.add_argument('--key', default=None)
    ap.add_argument('--max-tokens', type=int, default=200)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    key = read_key(args.key)
    if not key:
        print('找不到令牌（config/user_token.json 或 --key）', file=sys.stderr)
        return 2
    res = run(args.stream, args.model, args.prompt, key, gateway_base(), args.max_tokens)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res.get('ok') else 1
    print('模式: %s  模型: %s' % ('流式' if args.stream else '同步', args.model))
    print('首字延迟: %s ms   总时长: %s ms   块数: %s' % (
        res.get('first_ms'), res.get('total_ms'), res.get('chunks')))
    u = res.get('usage') or {}
    print('usage: prompt=%s completion=%s total=%s' % (
        u.get('prompt_tokens'), u.get('completion_tokens'), u.get('total_tokens')))
    print('正文 %d 字 / 思考 %s 字' % (len(res.get('text') or ''),
                                     res.get('reasoning_chars', '-')))
    print('文本：%s' % (res.get('text') or '')[:120])
    if not res.get('ok'):
        print('错误:', res.get('error'))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
