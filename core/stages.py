# -*- coding: utf-8 -*-
"""章节状态（照 dsh-superagent 的 Ticket 阶段）

五态：draft / working / awaiting / blocked / done
存储：<书>/章节/.stages.json（缺省 = draft；可重建，已进 .gitignore）

自动流转（代码强制）：
  写章开始            -> working
  四层跑完            -> awaiting
  审稿团 inconclusive -> blocked
  客户点「可以」       -> done
  客户说「重写」       -> working

用法:
    python core/stages.py --book <书名>                 # 列出全部
    python core/stages.py --book <书名> --ch 003 --set awaiting
    python core/stages.py --book <书名> --ch 003 --get
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

STAGES = ('draft', 'working', 'awaiting', 'blocked', 'done')
SOURCES = ('reviewers', 'writing', 'manual', 'import')
ACTIONS = ('choose', 'review', 'confirm', 'retry', 'cancel')
REASON_MAX = 40
FILE = '.stages.json'
CHAPTERS = '章节'


# 允许的状态流转（None = 首次写入任意状态）
# 目的：拦住「没写完就定稿」「定稿后悄悄回到等待」这类越权跳转。
TRANSITIONS = {
    'draft': ('working', 'blocked', 'awaiting'),
    'working': ('awaiting', 'blocked', 'draft'),
    'awaiting': ('done', 'working', 'blocked', 'awaiting'),
    'blocked': ('working', 'draft', 'done', 'blocked', 'awaiting'),
    'done': ('working', 'awaiting', 'done'),
}

def book_dir(book, root=None):
    return os.path.join(root or CO.projects_root(), book)


def stages_path(book, root=None):
    return os.path.join(book_dir(book, root), CHAPTERS, FILE)


def chapter_no(chapter):
    m = re.search(r'(\d{1,4})', str(chapter or ''))
    return m.group(1).zfill(3) if m else None


def book_of_path(path, root=None):
    """从章节/设定文件路径反推书名；不在 projects/<书>/ 下返回 None。"""
    p = os.path.abspath(path or '')
    root = os.path.abspath(os.path.join(root or CO.ROOT, 'projects'))
    if not p.startswith(root + os.sep):
        return None
    rel = p[len(root) + 1:].split(os.sep)
    return rel[0] if rel and rel[0] else None


def _load(book, root=None):
    try:
        with open(stages_path(book, root), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(book, root=None, data=None):
    p = stages_path(book, root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data or {}, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, p)
    return p


def get_stages(book, root=None):
    """{"001": "done", ...}（只含已记录过的章；缺省 draft 由调用方补）"""
    return {k: (v.get('stage') if isinstance(v, dict) else 'draft')
            for k, v in _load(book, root).items()}


def get_stage(book, chapter, root=None):
    ch = chapter_no(chapter)
    rec = _load(book, root).get(ch) or {}
    return rec.get('stage') or 'draft'


def get_detail(book, chapter, root=None):
    """{stage, reason, source, action, updated}"""
    ch = chapter_no(chapter)
    rec = dict(_load(book, root).get(ch) or {})
    rec.setdefault('stage', 'draft')
    return rec


def _clip(reason):
    if not reason:
        return ''
    r = re.sub(r'\s+', ' ', str(reason)).strip()
    return r if len(r) <= REASON_MAX else r[:REASON_MAX - 1] + '…'


def can_transition(prev, nxt):
    """prev -> nxt 是否合法。prev 缺失视为首次写入。"""
    if not prev:
        return True
    allowed = TRANSITIONS.get(prev)
    if allowed is None:
        return False
    return nxt in allowed


def set_stage(book, chapter, stage, reason=None, source=None, action=None, root=None,
              force=False):
    """写状态。reason 直接给客户看（强制 <=40 字），source/action 给前端决定按钮。"""
    ch = chapter_no(chapter)
    if not ch:
        raise ValueError('章节号无法识别：%r' % (chapter,))
    stage = str(stage or '').lower()
    if stage not in STAGES:
        raise ValueError('非法状态 %r（可选：%s）' % (stage, '/'.join(STAGES)))
    if source is not None and source not in SOURCES:
        raise ValueError('非法 source %r（可选：%s）' % (source, '/'.join(SOURCES)))
    if action is not None and action not in ACTIONS:
        raise ValueError('非法 action %r（可选：%s）' % (action, '/'.join(ACTIONS)))
    data = _load(book, root)
    old = data.get(ch) or {}
    prev = old.get('stage') or 'draft'
    if not force and prev != stage and not can_transition(prev, stage):
        raise ValueError('状态不能从 %s 直接跳到 %s（允许：%s）'
                         % (prev, stage, '/'.join(TRANSITIONS.get(prev, ())) or '无'))
    rec = {'stage': stage, 'updated': time.strftime('%Y-%m-%d %H:%M:%S')}
    reason_txt = _clip(reason) if reason is not None else _clip(old.get('reason'))
    if reason_txt:
        rec['reason'] = reason_txt
    if source:
        rec['source'] = source
    elif old.get('source'):
        rec['source'] = old['source']
    if action:
        rec['action'] = action
    elif old.get('action'):
        rec['action'] = old['action']
    data[ch] = rec
    _save(book, root, data)
    return {'book': book, 'chapter': ch, 'stage': stage, 'previous': prev,
            'changed': prev != stage, 'reason': rec.get('reason', ''),
            'source': rec.get('source', ''), 'action': rec.get('action', ''),
            'path': stages_path(book, root)}


def missing_map(book, root=None):
    """{章: True} 表示 .stages.json 里有记录、但磁盘上没有对应正文文件（幽灵章节）。"""
    bd = book_dir(book, root)
    d = os.path.join(bd, '章节')
    out = {}
    try:
        files = [f for f in os.listdir(d) if f.endswith('.md') and '.bak' not in f]
    except OSError:
        files = []
    for ch in (get_stages(book, root) or {}):
        out[ch] = not any(f.startswith(ch + '-') for f in files)
    return out


def details_map(book, root=None):
    """{章: {reason, source, action}}（只含有原因/来源/动作的章）"""
    out = {}
    for ch, rec in _load(book, root).items():
        if not isinstance(rec, dict):
            continue
        d = {k: rec[k] for k in ('reason', 'source', 'action') if rec.get(k)}
        if d:
            out[ch] = d
    return dict(sorted(out.items()))


def full_map(book, chapters=None, root=None):
    """合并所有章节文件（缺省 draft），给前端画状态点。"""
    m = {k: (v.get('stage') if isinstance(v, dict) else 'draft')
         for k, v in _load(book, root).items()}
    d = os.path.join(book_dir(book, root), CHAPTERS)
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith('.md'):
                ch = chapter_no(f)
                if ch and ch not in m:
                    m[ch] = 'draft'
    return dict(sorted(m.items()))


def main():
    ap = argparse.ArgumentParser(description='章节状态')
    ap.add_argument('--book', required=True)
    ap.add_argument('--ch', default=None)
    ap.add_argument('--set', dest='new_stage', default=None)
    ap.add_argument('--get', action='store_true')
    ap.add_argument('--reason', default=None)
    ap.add_argument('--source', default=None)
    ap.add_argument('--action', default=None)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    if args.ch and args.new_stage:
        r = set_stage(args.book, args.ch, args.new_stage,
                      reason=args.reason, source=args.source, action=args.action)
        print(json.dumps(r, ensure_ascii=False) if args.json else
              '%s 第 %s 章：%s → %s%s' % (r['book'], r['chapter'], r['previous'], r['stage'],
                                        '（%s）' % r['reason'] if r.get('reason') else ''))
        return 0
    if args.ch and args.get:
        st = get_stage(args.book, args.ch)
        print(json.dumps({'chapter': chapter_no(args.ch), 'stage': st}) if args.json else st)
        return 0
    m = full_map(args.book)
    if args.json:
        print(json.dumps(m, ensure_ascii=False, indent=1))
    else:
        for ch, st in m.items():
            print('  %s  %s' % (ch, st))
    return 0


if __name__ == '__main__':
    sys.exit(main())
