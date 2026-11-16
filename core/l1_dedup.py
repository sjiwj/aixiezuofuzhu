# -*- coding: utf-8 -*-
"""L1 冲突检测（照抄 TencentDB-Agent-Memory 的 l1-dedup 三阶段）

问题：账本更新时，「甲剩下 40 文」和「甲剩下 0 文」会同时存在，
      写着写着模型就不知道该信哪个。

做法（三个阶段，任何时候都不 merge 不相干的东西）：
  1. 逐条新记忆召回候选（按 token 重叠打分，topK=5，不调 LLM）
  2. 新记忆 + 候选池拼成一次 LLM 调用，批量判定
  3. 按判定落地：store / update / merge / skip
     merge 时 merged_timestamps 取并集（不是覆盖）
  没有候选（检索不可用）就全部 store —— 不瞎合并。

用法:
    python core/l1_dedup.py --book <书名> --ch 003            # 只看结果
    python core/l1_dedup.py --book <书名> --ch 003 --apply     # 写 sidecar
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

STATE_FILE = '角色状态.md'
SIDECAR = '.l1-records.json'
TOP_K = 5

ACTIONS = ('store', 'update', 'merge', 'skip')


# ---------------- 抽取 ----------------

def chapter_of(name):
    m = re.search(r'(\d{3})', name or '')
    return m.group(1) if m else None


def extract_records(state_text, chapter):
    """角色状态.md -> [{id, key, field, value, chapters}]"""
    out = []
    cur = None
    for line in (state_text or '').split('\n'):
        if line.startswith('## '):
            title = line[3:].strip()
            cur = re.sub(r'（.*?）|\(.*?\)', '', title).strip()
            continue
        m = re.match(r'^\s*[-*]\s*\*\*(.+?)\*\*\s*[:：]\s*(.+?)\s*$', line)
        if not m or not cur:
            continue
        field, value = m.group(1).strip(), m.group(2).strip()
        if field in ('最后更新',):
            continue
        out.append({
            'id': '%s/%s/%s' % (cur, field, chapter or '000'),
            'key': cur, 'field': field, 'value': value,
            'chapters': [chapter] if chapter else [],
        })
    return out


def tokens(text):
    """无 jieba 时的轻量替代：中文按 2-gram，英文/数字按词。"""
    s = str(text or '').lower()
    grams = set(re.findall(r'[a-z0-9]{2,}', s))
    zh = re.findall(r'[\u4e00-\u9fa5]+', s)
    for w in zh:
        for i in range(len(w) - 1):
            grams.add(w[i:i + 2])
    return grams


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def candidates(record, pool, topk=TOP_K):
    scored = []
    for other in pool:
        if other['id'] == record['id']:
            continue
        # 同角色同字段优先，其次文本相似
        same = (other['key'] == record['key']) + (other['field'] == record['field'])
        score = similarity(record['value'], other['value']) + 0.5 * same
        if score > 0:
            scored.append((score, other))
    scored.sort(key=lambda x: -x[0])
    return [o for _, o in scored[:topk]]


# ---------------- LLM 批量判定 ----------------

JUDGE_PROMPT = """你是小说账本的去重员。下面给你「新记录」和「已有记录」。
逐条判断每条新记录该怎么处理，输出严格 JSON（不要解释、不要代码块围栏）：

{"decisions":[{"id":"<新记录id>","action":"store|update|merge|skip","target":"<已有记录id或空>","reason":"<20字内>"}]}

判定规则：
- skip   ：新记录与某条已有记录表达同一事实（数值/内容相同或只是措辞不同）
- update ：同一事实被改写（如「四十文」→「零文」），以新记录为准，target 指向旧记录
- merge  ：两条各有信息、应合成一条，target 指向旧记录
- store  ：确实是一条新事实，与已有记录不冲突
每条新记录必须给出一条 decision。

方向约定（必须遵守）：
- 【旧】= 已有记录（可能过时，是 target 的唯一合法来源）
- 【新】= 本次新记录（刚写进账本，是当前事实）
- update/merge 的 target 必须指向某条【旧】记录的 id，绝不能指向新记录自己。
- reason 必须写成「旧 → 新」的方向，例如「四十文 → 零文」。

【新】记录：
%s

【旧】记录：
%s
"""


def _parse_json(text):
    s = (text or '').strip()
    if not s:
        return None
    i, j = s.find('{'), s.rfind('}')
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(s[i:j + 1])
    except ValueError:
        return None


def judge(new_records, cand_map, model='deepseek-flash'):
    """一次调用判定所有新记录。返回 {id: decision}；失败返回 None（调用方跳过检测）。"""
    if not new_records:
        return {}
    payload = [{'tag': '新', 'id': r['id'], 'key': r['key'], 'field': r['field'],
                'value': r['value']} for r in new_records]
    pool, seen = [], set()
    for rid, lst in cand_map.items():
        for c in lst:
            if c['id'] in seen:
                continue
            seen.add(c['id'])
            pool.append({'tag': '旧', 'id': c['id'], 'key': c['key'], 'field': c['field'],
                         'value': c['value']})
    if not pool:
        return {r['id']: {'id': r['id'], 'action': 'store', 'target': '', 'reason': '无候选'} for r in new_records}
    prompt = JUDGE_PROMPT % (json.dumps(payload, ensure_ascii=False, indent=1),
                             json.dumps(pool, ensure_ascii=False, indent=1))
    try:
        resp = CO.chat({'model': model, 'temperature': 0.0, 'max_tokens': 1500,
                        'extra_body': {'thinking': {'type': 'disabled'}}},
                       [{'role': 'user', 'content': prompt}])
    except Exception:
        return None
    data = _parse_json(CO._extract_content(resp))
    if not isinstance(data, dict) or not isinstance(data.get('decisions'), list):
        return None
    out = {}
    for d in data['decisions']:
        if not isinstance(d, dict):
            continue
        rid = str(d.get('id') or '')
        act = str(d.get('action') or '').lower()
        if rid and act in ACTIONS:
            out[rid] = {'id': rid, 'action': act, 'target': str(d.get('target') or ''),
                        'reason': str(d.get('reason') or '')[:40]}
    return out or None


# ---------------- 落地 ----------------

def apply_decisions(existing, new_records, decisions, chapter):
    """返回 (records, report)。已有记录被 update/merge/skip 时标 superseded，时间戳取并集。"""
    by_id = {r['id']: r for r in existing}
    added, report = [], {'store': [], 'update': [], 'merge': [], 'skip': [], 'unjudged': []}

    for rec in new_records:
        d = decisions.get(rec['id'])
        if not d:
            by_id[rec['id']] = rec
            added.append(rec['id'])
            report['unjudged'].append(rec['id'])
            continue
        act = d['action']
        if d.get('target') == rec['id']:
            # 模型把目标指回自己：同值就 skip，不同就当新事实存
            if any(r['id'] == rec['id'] and r.get('value') == rec['value'] for r in existing):
                report['skip'].append({'id': rec['id'], 'target': rec['id'], 'reason': '同值'})
                continue
            by_id[rec['id']] = rec
            added.append(rec['id'])
            report['store'].append({'id': rec['id'], 'reason': '自指'})
            continue
        target = by_id.get(d['target'])
        if act == 'store' or target is None:
            by_id[rec['id']] = rec
            added.append(rec['id'])
            report['store' if act == 'store' else 'unjudged'].append(
                {'id': rec['id'], 'reason': d.get('reason') if act != 'store' else ''})
            continue
        if act == 'skip':
            target['chapters'] = sorted(set(target.get('chapters') or []) |
                                        set(rec.get('chapters') or []))
            report['skip'].append({'id': rec['id'], 'target': target['id'], 'reason': d['reason']})
            continue
        # update / merge：旧记录留档标 superseded（保留旧值与旧时间戳），新记录生效，时间戳取并集
        merged_chapters = sorted(set(target.get('chapters') or []) | set(rec.get('chapters') or []))
        if act == 'merge':
            value = target['value'] if target['value'] == rec['value'] else '%s；%s' % (
                target['value'], rec['value'])
        else:
            value = rec['value']
        target['status'] = 'superseded'
        target['superseded_by'] = rec['id']
        new_rec = {'id': rec['id'], 'key': rec['key'], 'field': rec['field'],
                   'value': value, 'chapters': merged_chapters,
                   'merged_timestamps': merged_chapters, 'supersedes': target['id']}
        by_id[rec['id']] = new_rec
        added.append(rec['id'])
        report[act].append({'id': rec['id'], 'target': target['id'],
                            'old': target.get('value'), 'new': value,
                            'merged_timestamps': merged_chapters, 'reason': d['reason']})
    records = list(by_id.values())
    return records, report


def run(book, chapter, model='deepseek-flash', apply=False, root=None):
    base = os.path.join(root or CO.ROOT, 'projects', book)
    sdir = os.path.join(base, '设定库')
    state_path = os.path.join(sdir, STATE_FILE)
    if not os.path.exists(state_path):
        return {'ok': False, 'error': '缺少 %s' % STATE_FILE}
    with open(state_path, encoding='utf-8-sig') as f:
        text = f.read()
    chapter = str(chapter).zfill(3) if str(chapter).isdigit() else chapter
    new_records = extract_records(text, chapter)
    if not new_records:
        return {'ok': True, 'decisions': {}, 'report': {}, 'note': '没有可检测的记录'}

    sidecar = os.path.join(sdir, SIDECAR)
    existing = []
    if os.path.exists(sidecar):
        try:
            with open(sidecar, encoding='utf-8') as f:
                existing = (json.load(f) or {}).get('records') or []
        except ValueError:
            existing = []

    # 同一个 key/field 的旧记录就是候选池（不依赖外部检索）
    pool = [r for r in existing if r.get('status') != 'superseded']
    cand_map = {r['id']: candidates(r, pool) for r in new_records}
    has_cands = any(cand_map.values())
    decisions = judge(new_records, cand_map, model) if has_cands else None
    if decisions is None:
        # 检索/判定不可用：全部按新记录存，不合并
        decisions = {r['id']: {'id': r['id'], 'action': 'store', 'target': '', 'reason': '跳过检测'}
                     for r in new_records}
        skipped = True
    else:
        skipped = False

    # target 指回自己时，改指同 key+field 的最近一条旧记录（不让模型的方向错误带偏落库）
    by_key = {}
    for r in existing:
        if r.get('status') == 'superseded':
            continue
        by_key.setdefault((r['key'], r['field']), r)
    for rid, d in list(decisions.items()):
        if d.get('target') == rid and d.get('action') in ('update', 'merge'):
            rec = next((r for r in new_records if r['id'] == rid), None)
            old = by_key.get((rec['key'], rec['field'])) if rec else None
            if old and old['id'] != rid:
                d['target'] = old['id']
                d['reason'] = (d.get('reason') or '') + '（target 修正为旧记录）'
            else:
                d['action'] = 'store'
                d['target'] = ''
                d['reason'] = (d.get('reason') or '') + '（无可覆盖旧记录）'

    records, report = apply_decisions(existing, new_records, decisions, chapter)
    result = {'ok': True, 'chapter': chapter, 'model': model, 'skipped_detection': skipped,
              'decisions': decisions, 'report': report, 'total': len(records)}
    if apply:
        tmp = sidecar + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'updated': time.strftime('%Y-%m-%d %H:%M'),
                       'chapter': chapter, 'records': records}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, sidecar)
        result['sidecar'] = sidecar
    return result


def main():
    ap = argparse.ArgumentParser(description='L1 冲突检测（账本去重）')
    ap.add_argument('--book', required=True)
    ap.add_argument('--ch', required=True)
    ap.add_argument('--model', default='deepseek-flash')
    ap.add_argument('--apply', action='store_true', help='把结果写进 设定库/.l1-records.json')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    res = run(args.book, args.ch, model=args.model, apply=args.apply)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get('ok') else 2
    if not res.get('ok'):
        print('[错误]', res.get('error'))
        return 2
    rep = res.get('report') or {}
    print('第 %s 章：新记录 %d 条 → store %d / update %d / merge %d / skip %d / 未判定 %d' % (
        res['chapter'], len(res['decisions']),
        len(rep.get('store', [])), len(rep.get('update', [])),
        len(rep.get('merge', [])), len(rep.get('skip', [])), len(rep.get('unjudged', []))))
    for act in ('update', 'merge'):
        for item in rep.get(act) or []:
            print('  [%s] %s → %s：%r → %r（时间戳 %s）' % (
                act, item['id'], item['target'], item.get('old'), item.get('new'),
                item.get('merged_timestamps')))
    for item in rep.get('skip') or []:
        print('  [skip] %s（同 %s）' % (item['id'], item['target']))
    if res.get('sidecar'):
        print('已写 sidecar：%s' % res['sidecar'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
