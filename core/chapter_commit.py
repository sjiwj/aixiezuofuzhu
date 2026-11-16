# -*- coding: utf-8 -*-
"""章节提交（commit）：把「事实入账」做成有校验、有 ID、可重放的事务

流程：写章 → 提取 artifact → 校验 → 写 commit → 投影到账本/索引/摘要

产物：
    <书>/.story/commits/chapter_004.commit.json   一次性提交（校验通过才写）
    <书>/.story/events.jsonl                      事件（按确定性 ID 幂等追加）
    <书>/.story/projection_log.jsonl              五路投影状态（每行一条）

用法:
    python core/chapter_commit.py --book <书名> --chapter 003 --build
    python core/chapter_commit.py --book <书名> --validate some.json
    python core/chapter_commit.py --book <书名> --status
    python core/chapter_commit.py --book <书名> --retry 003
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

STORY = '.story'
COMMITS = 'commits'
EVENTS_FILE = 'events.jsonl'
PROJECTION_LOG = 'projection_log.jsonl'
ROUTES = ('state', 'index', 'summary', 'memory', 'vector')
REQUIRED_EXTRACTION = ('accepted_events', 'state_deltas', 'entity_deltas')
REQUIRED_TOP = ('chapter', 'book', 'extraction_result')


class CommitError(ValueError):
    pass


# ---------------- 路径 ----------------

def book_dir(book, root=None):
    return os.path.join(root or CO.projects_root(), book)


def story_dir(book, root=None):
    return os.path.join(book_dir(book, root), STORY)


def commit_path(book, chapter, root=None):
    ch = str(chapter).zfill(3)
    return os.path.join(story_dir(book, root), COMMITS, 'chapter_%s.commit.json' % ch)


# ---------------- 校验 ----------------

def validate_commit(commit):
    """严格校验。任何一条不过就抛 CommitError，绝不写账本。"""
    if not isinstance(commit, dict):
        raise CommitError('commit 必须是对象，收到 %s' % type(commit).__name__)
    if 'data' in commit and isinstance(commit.get('data'), dict) \
            and 'extraction_result' not in commit:
        raise CommitError('禁止嵌套：检测到 {"data": {...}} 包装，请把字段平铺到顶层')
    for k in REQUIRED_TOP:
        if k not in commit:
            raise CommitError('缺少必填字段：%s' % k)

    er = commit['extraction_result']
    if not isinstance(er, dict):
        raise CommitError('extraction_result 必须是对象')
    if 'data' in er and isinstance(er.get('data'), dict):
        raise CommitError('禁止嵌套：extraction_result 里又包了一层 {"data": {...}}')
    for k in REQUIRED_EXTRACTION:
        if k not in er:
            raise CommitError('extraction_result 缺少必填字段：%s' % k)
        if not isinstance(er[k], list):
            raise CommitError('extraction_result.%s 必须是数组' % k)

    rr = commit.get('review_result')
    if rr is not None:
        if not isinstance(rr, dict):
            raise CommitError('review_result 必须是对象')
        if 'blocking_count' in rr and not isinstance(rr['blocking_count'], int):
            raise CommitError('review_result.blocking_count 必须是 int，收到 %r（%s）'
                              % (rr['blocking_count'], type(rr['blocking_count']).__name__))
        if isinstance(rr.get('blocking_count'), bool):
            raise CommitError('review_result.blocking_count 不能是 bool')

    fr = commit.get('fulfillment_result')
    if fr is not None:
        if not isinstance(fr, dict):
            raise CommitError('fulfillment_result 必须是对象')
        for k in ('planned', 'covered', 'missed', 'extra'):
            if k in fr and not isinstance(fr[k], list):
                raise CommitError('fulfillment_result.%s 必须是数组' % k)

    dr = commit.get('disambiguation_result')
    if dr is not None and not isinstance(dr, dict):
        raise CommitError('disambiguation_result 必须是对象')
    return True


# ---------------- 事件 ID ----------------

def event_id(chapter, seq, payload):
    """同内容重跑 -> 同一 ID（投影幂等的基础）。"""
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]
    return 'evt-ch%03d-%03d-%s' % (int(chapter), int(seq), h)


def normalize_events(commit):
    """给每条事件补 id；没有 type/content 的按空值保留（由校验层决定是否拒绝）。"""
    ch = str(commit['chapter']).zfill(3)
    out = []
    for i, ev in enumerate(commit['extraction_result'].get('accepted_events') or [], 1):
        if not isinstance(ev, dict):
            raise CommitError('accepted_events[%d] 必须是对象' % i)
        payload = {k: v for k, v in ev.items() if k != 'id'}
        rec = dict(ev)
        rec['id'] = ev.get('id') or event_id(ch, i, payload)
        out.append(rec)
    return out


# ---------------- 写 commit ----------------

def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


def write_commit(book, commit, root=None):
    validate_commit(commit)
    ch = str(commit['chapter']).zfill(3)
    commit = dict(commit)
    commit['chapter'] = ch
    commit.setdefault('created_at', time.strftime('%Y-%m-%dT%H:%M:%S'))
    commit['events'] = normalize_events(commit)
    p = commit_path(book, ch, root)
    _atomic_write(p, json.dumps(commit, ensure_ascii=False, indent=1))
    return p, commit


def load_commit(book, chapter, root=None):
    p = commit_path(book, chapter, root)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)


# ---------------- 投影（五路） ----------------

def _log_projection(book, chapter, route, status, root=None):
    rec = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'chapter': str(chapter).zfill(3),
           'route': route, 'status': status}
    p = os.path.join(story_dir(book, root), PROJECTION_LOG)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return rec


def _append_events(book, chapter, events, root=None):
    """按 id 幂等追加（同 id 不重复写）。"""
    p = os.path.join(story_dir(book, root), EVENTS_FILE)
    seen = set()
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            for line in f:
                try:
                    seen.add(json.loads(line).get('id'))
                except ValueError:
                    continue
    with open(p, 'a', encoding='utf-8') as f:
        for ev in events:
            if ev['id'] in seen:
                continue
            f.write(json.dumps(dict(ev, chapter=str(chapter).zfill(3)), ensure_ascii=False) + '\n')
            seen.add(ev['id'])
    return len(seen)


def project_state(book, chapter, commit, root=None):
    d = os.path.join(story_dir(book, root), 'state')
    os.makedirs(d, exist_ok=True)
    payload = {'chapter': str(chapter).zfill(3),
               'state_deltas': commit['extraction_result'].get('state_deltas') or [],
               'entity_deltas': commit['extraction_result'].get('entity_deltas') or []}
    _atomic_write(os.path.join(d, 'chapter_%s.json' % str(chapter).zfill(3)),
                  json.dumps(payload, ensure_ascii=False, indent=1))
    return 'done'


def project_index(book, chapter, commit, root=None):
    try:
        import text_index as T
        T.build(book, root)
        return 'done'
    except Exception as e:
        return 'failed:%s' % type(e).__name__


def project_summary(book, chapter, commit, root=None):
    body = (commit.get('summary') or '').strip()
    if not body:
        return 'skipped:no-summary'
    d = os.path.join(story_dir(book, root), 'summary')
    os.makedirs(d, exist_ok=True)
    _atomic_write(os.path.join(d, 'chapter_%s.md' % str(chapter).zfill(3)),
                  '# 第 %s 章摘要\n\n%s\n' % (str(chapter).zfill(3), body))
    return 'done'


def project_memory(book, chapter, commit, root=None):
    try:
        import memory_index as MI
        MI.drop_cache(book)
        idx = MI.open_index(book, refresh=True)
        return 'done:rev%s' % idx.revision
    except Exception as e:
        return 'failed:%s' % type(e).__name__


def project_vector(book, chapter, commit, root=None):
    return 'skipped:no-embedding-key'


PROJECTORS = {
    'state': project_state,
    'index': project_index,
    'summary': project_summary,
    'memory': project_memory,
    'vector': project_vector,
}


def project(book, chapter, commit, root=None, only=None):
    status = {}
    for route in ROUTES:
        if only and route not in only:
            continue
        fn = PROJECTORS[route]
        try:
            st = fn(book, chapter, commit, root)
        except Exception as e:
            st = 'failed:%s: %s' % (type(e).__name__, e)
        status[route] = st
        _log_projection(book, chapter, route, st, root)
    _append_events(book, chapter, commit.get('events') or [], root)
    return status


# ---------------- 流水线入口：正文 -> 提取 -> 校验 -> commit -> 投影 ----------------

LAST_COMMIT = {}


def commit_chapter(book, chapter, text, review=None, outline=None, root=None,
                   model='deepseek-flash', precheck=None):
    """写章完成后调用。失败只影响账本（状态置 blocked），绝不动正文。"""
    ch = str(chapter).zfill(3)
    try:
        import artifact_extract as AE
        arts = AE.extract_artifacts(book, ch, text, model=model)
    except Exception as e:
        reason = '事实提取失败：%s' % (str(e)[:40] or type(e).__name__)
        LAST_COMMIT.clear()
        LAST_COMMIT.update({'ok': False, 'chapter': ch, 'reason': reason})
        return {'ok': False, 'chapter': ch, 'stage': 'blocked', 'error': reason}

    commit = {
        'chapter': ch, 'book': book,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'review_result': {
            'blocking_count': int((review or {}).get('blocking_count') or 0)
            + len((precheck or {}).get('blocking') or []),
            'issues': ((review or {}).get('issues') or [])
            + ((precheck or {}).get('blocking') or [])
            + ((precheck or {}).get('warnings') or []),
            'precheck_score': (precheck or {}).get('score'),
        },
        'fulfillment_result': (outline or {'planned': [], 'covered': [], 'missed': [], 'extra': []}),
        'disambiguation_result': {'pending': [d.get('name') for d in arts.get('entity_deltas') or []
                                             if d.get('name')]},
        'extraction_result': arts,
    }
    try:
        path, saved = write_commit(book, commit, root)
    except CommitError as e:
        reason = '事实入账被拒：%s' % str(e)[:60]
        LAST_COMMIT.clear()
        LAST_COMMIT.update({'ok': False, 'chapter': ch, 'reason': reason})
        return {'ok': False, 'chapter': ch, 'stage': 'blocked', 'error': reason}

    status = project(book, saved['chapter'], saved, root)
    LAST_COMMIT.clear()
    LAST_COMMIT.update({'ok': True, 'chapter': ch, 'path': path, 'status': status,
                        'events': len(saved.get('events') or [])})
    return {'ok': True, 'chapter': ch, 'path': path, 'status': status,
            'events': len(saved.get('events') or [])}


# ---------------- 状态 / 重试 ----------------

def latest_status(book, root=None):
    """每章每路最后一条状态。"""
    p = os.path.join(story_dir(book, root), PROJECTION_LOG)
    out = {}
    if not os.path.exists(p):
        return out
    with open(p, encoding='utf-8') as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            out.setdefault(r['chapter'], {})[r['route']] = r['status']
    return out


def retry(book, chapter, root=None):
    commit = load_commit(book, chapter, root)
    if not commit:
        return {'ok': False, 'error': '没有 commit：%s' % commit_path(book, chapter, root)}
    st = latest_status(book, root).get(str(chapter).zfill(3)) or {}
    def needs_retry(route):
        s = str(st.get(route, ''))
        return (s == '' or s.startswith('failed') or s.startswith('pending'))
    failed = [r for r in ROUTES if needs_retry(r)]
    if not failed:
        return {'ok': True, 'chapter': str(chapter).zfill(3), 'retried': [],
                'note': '没有失败的路（skipped 视为终态）'}
    res = project(book, chapter, commit, root, only=set(failed))
    return {'ok': True, 'chapter': str(chapter).zfill(3), 'retried': failed, 'status': res}


# ---------------- 从现有数据生成 commit（演示/回填） ----------------

def build_from_chapter(book, chapter, root=None):
    """把一章的可确定事实抽成 commit：事件来自 事件索引/时间线，状态来自 角色状态。"""
    base = book_dir(book, root)
    ch = str(chapter).zfill(3)
    def rd(name):
        p = os.path.join(base, '设定库', name)
        try:
            with open(p, encoding='utf-8-sig') as f:
                return f.read()
        except OSError:
            return ''

    events = []
    # 事件索引行 -> 事件
    for line in rd('事件索引.md').split('\n'):
        if not line.strip().startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) >= 3 and re.fullmatch(r'\d{1,3}', cells[0] or '') and cells[0].zfill(3) == ch:
            events.append({'type': 'chapter_event', 'subject': 'chapter:' + ch,
                           'content': cells[2]})

    state_deltas, entity_deltas = [], []
    cur = None
    for line in rd('角色状态.md').split('\n'):
        if line.startswith('## '):
            cur = re.sub(r'[（(].*?[)）]', '', line[3:]).strip()
            continue
        m = re.match(r'^\s*[-*]\s*\*\*(.+?)\*\*\s*[:：]\s*(.+?)\s*$', line)
        if m and cur:
            state_deltas.append({'entity': cur, 'field': m.group(1), 'value': m.group(2)})
            if m.group(1) == '当前位置':
                entity_deltas.append({'entity': cur, 'place': m.group(2)})

    summary = ''
    m = re.search(r'^###\s*' + ch + r'[^\n]*\n(.*?)(?=^###\s|^##\s|\Z)', rd('章节摘要.md'), re.S | re.M)
    if m:
        summary = m.group(1).strip()

    return {
        'chapter': ch,
        'book': book,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'review_result': {'blocking_count': 0, 'issues': []},
        'fulfillment_result': {'planned': [], 'covered': [], 'missed': [], 'extra': []},
        'disambiguation_result': {'pending': []},
        'extraction_result': {'accepted_events': events, 'state_deltas': state_deltas,
                              'entity_deltas': entity_deltas},
        'summary': summary,
    }


# ---------------- CLI ----------------

def main():
    ap = argparse.ArgumentParser(description='章节提交（校验 + 事件 ID + 投影状态）')
    ap.add_argument('--book', required=True)
    ap.add_argument('--chapter', default=None)
    ap.add_argument('--build', action='store_true', help='从现有账本生成并提交')
    ap.add_argument('--validate', default=None, help='只校验一个 commit json')
    ap.add_argument('--status', action='store_true', help='看每章每路投影状态')
    ap.add_argument('--retry', default=None, help='只重跑失败的投影')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    if args.validate:
        with open(args.validate, encoding='utf-8') as f:
            commit = json.load(f)
        try:
            write_commit(args.book, commit)
            print('校验通过')
            return 0
        except CommitError as e:
            print('校验失败：%s' % e)
            return 2

    if args.status:
        st = latest_status(args.book)
        if args.json:
            print(json.dumps(st, ensure_ascii=False, indent=1))
            return 0
        if not st:
            print('还没有投影记录')
            return 0
        for ch in sorted(st):
            print('第 %s 章' % ch)
            for route in ROUTES:
                print('  %-8s %s' % (route, st[ch].get(route, '（未跑）')))
        return 0

    if args.retry:
        r = retry(args.book, args.retry)
        print(json.dumps(r, ensure_ascii=False) if args.json else
              ('重跑 %s：%s' % (r.get('retried'), r.get('status') or r.get('note'))))
        return 0 if r.get('ok') else 2

    if args.build:
        if not args.chapter:
            print('--build 需要 --chapter', file=sys.stderr)
            return 2
        commit = build_from_chapter(args.book, args.chapter)
        try:
            p, c = write_commit(args.book, commit)
        except CommitError as e:
            print('校验失败，未写 commit：%s' % e)
            return 2
        st = project(args.book, args.chapter, c)
        print('commit: %s' % p)
        print('事件：%d 条（ID 幂等）' % len(c['events']))
        for route in ROUTES:
            print('  %-8s %s' % (route, st.get(route)))
        return 0

    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
