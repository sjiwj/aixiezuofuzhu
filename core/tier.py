# -*- coding: utf-8 -*-
"""Step 2 重点章判定：不同的章用不同的强度。

分级（配置在 config/writing_tiers.json）：
  normal   常规章 —— 便宜快
  key      黄金三章（默认 1-3）—— 强模型 + 思考
  arc_end  卷末章 —— 最强，收束全卷

判定只做事后解释，改动只影响「这一章用哪个模型」，不动正文流程。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CFG_REL = os.path.join('config', 'writing_tiers.json')

DEFAULT = {
    'enabled': True,
    'key_chapters': [1, 2, 3],
    'tiers': {
        'normal': {'model': ''},
        'key': {'model': 'deepseek-v4-pro', 'thinking': True, 'max_tokens': 20000},
        'arc_end': {'model': 'deepseek-v4-pro', 'thinking': True, 'max_tokens': 24000},
    },
}

_VOL_PAT = re.compile(r'###\s*卷([一二三四五六七八九十]+)[^（(]*[（(](\d{1,4})\s*[–\-~]\s*(\d{1,4})[）)]')


def _root():
    return os.environ.get('NOVELAPP_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_cfg():
    p = os.path.join(_root(), CFG_REL)
    try:
        with open(p, encoding='utf-8-sig') as f:
            data = json.load(f)
        if isinstance(data, dict):
            out = dict(DEFAULT)
            out.update({k: v for k, v in data.items() if k in ('enabled', 'key_chapters', 'tiers')})
            tiers = dict(DEFAULT['tiers'])
            tiers.update(data.get('tiers') or {})
            out['tiers'] = tiers
            return out
    except (OSError, ValueError):
        pass
    return dict(DEFAULT)


def volume_range(book, ch):
    """本章所在卷的 (卷名, 起始章, 结束章)；解析不到返回 ('', 0, 0)。"""
    try:
        import write_context as WC
        d = os.path.join(WC._book_dir(book), '大纲')
    except Exception:
        return ('', 0, 0)
    if not os.path.isdir(d):
        return ('', 0, 0)
    try:
        ch_int = int(ch)
    except (TypeError, ValueError):
        return ('', 0, 0)
    for f in sorted(x for x in os.listdir(d) if x.endswith('.md')):
        try:
            with open(os.path.join(d, f), encoding='utf-8-sig') as fh:
                text = fh.read()
        except OSError:
            continue
        for m in _VOL_PAT.finditer(text):
            lo, hi = int(m.group(2)), int(m.group(3))
            if lo <= ch_int <= hi:
                return ('卷' + m.group(1), lo, hi)
    return ('', 0, 0)


def resolve_tier(book, ch, cfg=None):
    """返回 (tier, reason, conf)。tier ∈ normal / key / arc_end。"""
    c = cfg if isinstance(cfg, dict) else load_cfg()
    tiers = c.get('tiers') or {}
    if not c.get('enabled', True):
        return 'normal', '分级已关闭', tiers.get('normal') or {}
    try:
        ch_int = int(ch)
    except (TypeError, ValueError):
        return 'normal', '', tiers.get('normal') or {}

    vol, lo, hi = volume_range(book, ch)
    if hi and ch_int == hi and 'arc_end' in tiers:
        return 'arc_end', '%s 最后一章（第 %d 章）' % (vol, hi), tiers['arc_end']

    keys = c.get('key_chapters') or []
    try:
        keys = [int(x) for x in keys]
    except (TypeError, ValueError):
        keys = []
    if ch_int in keys and 'key' in tiers:
        return 'key', '黄金三章（第 %d 章）' % ch_int, tiers['key']

    return 'normal', '', tiers.get('normal') or {}
