# -*- coding: utf-8 -*-
"""验收：/api/write 流式（可指向 18760 代理或 8770 直连）

用法:
    python scripts/verify_stream.py --base http://127.0.0.1:18760 --book <书名> --chapter 004
    python scripts/verify_stream.py --base http://127.0.0.1:8770  --book _t --chapter 001 --mode append
"""
import argparse
import json
import sys
import time
import urllib.request


def run(base, book, chapter, prompt, mode, timeout=300):
    body = json.dumps({'book': book, 'chapter': chapter, 'prompt': prompt, 'mode': mode}).encode()
    req = urllib.request.Request(base.rstrip('/') + '/api/write', data=body,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    t0 = time.time()
    first_content = None
    first_any = None
    events = {'delta': 0, 'content': 0, 'reasoning': 0}
    usage = done = err = start = None
    buf = b''
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            buf += raw
            while b'\n\n' in buf:
                chunk, buf = buf.split(b'\n\n', 1)
                line = chunk.decode('utf-8', 'replace').strip()
                if not line.startswith('data:'):
                    continue
                ev = json.loads(line[5:].strip())
                t = ev.get('type')
                if t == 'start':
                    start = ev
                elif t == 'delta':
                    events['delta'] += 1
                    if first_any is None:
                        first_any = int((time.time() - t0) * 1000)
                    if ev.get('kind') == 'content':
                        events['content'] += 1
                        if first_content is None:
                            first_content = int((time.time() - t0) * 1000)
                    elif ev.get('kind') == 'reasoning':
                        events['reasoning'] += 1
                elif t == 'usage':
                    usage = ev
                elif t == 'done':
                    done = ev
                elif t == 'error':
                    err = ev
    return {'ms': int((time.time() - t0) * 1000), 'first_any_ms': first_any,
            'first_content_ms': first_content, 'events': events,
            'usage': usage, 'done': done, 'error': err, 'start': start}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:18760')
    ap.add_argument('--book', required=True)
    ap.add_argument('--chapter', required=True)
    ap.add_argument('--prompt', default=None)
    ap.add_argument('--mode', default='replace', choices=['replace', 'append'])
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    prompt = args.prompt or ('写第 %s 章开头。只写正文。' % args.chapter.lstrip('0'))
    r = run(args.base, args.book, args.chapter, prompt, args.mode)
    checks = [
        ('SSE 起始事件', bool(r['start'])),
        ('首字 < 4000 ms（思考或正文）', r['first_any_ms'] is not None and r['first_any_ms'] < 4000),
        ('正文块 > 0', r['events']['content'] > 0),
        ('字数 > 500', bool(r['done']) and (r['done'].get('chars') or 0) > 500),
        ('total_cny > 0', bool(r['usage']) and float(r['usage'].get('total_cny') or 0) > 0),
        ('无 error 事件', r['error'] is None),
        ('commit ok', bool(r['done']) and (r['done'].get('commit') or {}).get('ok') is True),
    ]
    ok = all(v for _, v in checks)
    if args.json:
        print(json.dumps({'ok': ok, 'result': r, 'checks': checks}, ensure_ascii=False))
    else:
        print('base=%s  book=%s  chapter=%s  mode=%s' % (args.base, args.book, args.chapter, args.mode))
        print('首字 %s ms｜首个正文 %s ms｜总 %s ms｜delta %d（正文 %d / 思考 %d）' % (
            r['first_any_ms'], r['first_content_ms'], r['ms'],
            r['events']['delta'], r['events']['content'], r['events']['reasoning']))
        u = r['usage'] or {}
        d = r['done'] or {}
        print('usage: prompt=%s completion=%s cny=%s' % (
            u.get('prompt_tokens'), u.get('completion_tokens'), u.get('total_cny')))
        print('done : chars=%s mode=%s path=%s commit.ok=%s' % (
            d.get('chars'), d.get('mode'), d.get('path'), (d.get('commit') or {}).get('ok')))
        print('-' * 60)
        for name, v in checks:
            print(('  PASS  ' if v else '  FAIL  ') + name)
        print('结果:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
