# -*- coding: utf-8 -*-
"""错题本 + 归因（模板「四保险」里我们真正缺的两件）。

设计约束（与本项目数据契约一致）：
- **文件为真源**：只追加 jsonl，不引入 sqlite 三表，避免与章节/账本形成双源。
- 去重键 = (category, message 归一化)，`subject` 只记来源，不参与去重计数。
- 达到阈值只生成**提案**，不自动改门禁；确认由人调用 confirm()。
"""
import json, os, re, time

THRESHOLD = 3
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, 'data', 'loop')
EVENTS = os.path.join(DIR, 'events.jsonl')
WRONG = os.path.join(DIR, 'wrongbook.jsonl')


def _ensure():
    os.makedirs(DIR, exist_ok=True)


def _append(path, row):
    _ensure()
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def _norm(msg):
    return re.sub(r'\s+', ' ', str(msg or '')).strip()[:300]


def event(stage, status, subject='', metric=None, message=''):
    _append(EVENTS, {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'stage': stage,
                     'status': status, 'subject': subject,
                     'metric': metric or {}, 'message': _norm(message)})


def record(subject, category, message, cycle='generate'):
    """回写一条错题；返回 {count, strengthened}。count 按 (category,msg) 累计。"""
    key_msg = _norm(message)
    rows = []
    if os.path.exists(WRONG):
        with open(WRONG, encoding='utf-8') as f:
            rows = [json.loads(l) for l in f if l.strip()]
    same = [r for r in rows if r.get('category') == category and r.get('message') == key_msg]
    count = len(same) + 1
    strengthened = count >= THRESHOLD
    _append(WRONG, {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'subject': subject,
                    'cycle': cycle, 'category': category, 'message': key_msg,
                    'count_after': count, 'strengthened': strengthened})
    return {'count': count, 'strengthened': strengthened}


def summarize():
    """按 (category, message) 聚合：出现次数、涉及章节、是否达阈值。"""
    agg = {}
    if os.path.exists(WRONG):
        with open(WRONG, encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                k = (r.get('category'), r.get('message'))
                e = agg.setdefault(k, {'category': k[0], 'message': k[1],
                                       'hits': 0, 'subjects': set()})
                e['hits'] += 1
                e['subjects'].add(r.get('subject') or '(unknown)')
    out = []
    for e in agg.values():
        e['subjects'] = sorted(e['subjects'])
        e['strengthened'] = e['hits'] >= THRESHOLD
        out.append(e)
    return sorted(out, key=lambda x: -x['hits'])


def proposals():
    """达阈值且未确认的条目 → 提案文本（不自动落门禁）。"""
    return [{'category': e['category'], 'message': e['message'], 'hits': e['hits'],
             'subjects': e['subjects'],
             'proposal': '同类错误出现 %d 次：%s；建议升级为硬门禁' % (e['hits'], e['message'])}
            for e in summarize() if e['strengthened']]


def rework_queue():
    """返工队列：按章节汇总未处置错题，命中多者优先。"""
    by = {}
    for e in summarize():
        for s in e['subjects']:
            it = by.setdefault(s, {'subject': s, 'hits': 0, 'issues': []})
            it['hits'] += e['hits']
            it['issues'].append({'category': e['category'], 'message': e['message'],
                                 'hits': e['hits'], 'strengthened': e['strengthened']})
    return sorted(by.values(), key=lambda x: -x['hits'])
