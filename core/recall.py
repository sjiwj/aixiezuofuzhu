# -*- coding: utf-8 -*-
"""记忆检索器：写第 N 章前，从八个账本里捞相关记忆，拼成 2000-4000 字参考资料。

原则：AI 可以忘，软件不能忘。
    L0 瞬时  当前章节正文
    L1 工作  相关角色/地点/伏笔（本文件负责）
    L2 短期  最近 3 章摘要（本文件负责）
    L3 长期  全书设定 + 事件索引（本文件负责）
    L4 归档  章节原文全文检索（暂不做）

用法:
    python core/recall.py --book <书名> --ch 003
    python core/recall.py --book <书名> --ch 003 --json
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

SETTINGS = '设定库'
RECENT_N = 3
MAX_FORESHADOW = 10
INDEX_MIN_CHAPTERS = int(os.environ.get('NOVELAPP_INDEX_MIN_CHAPTERS') or 60)


def read(p):
    try:
        with open(p, encoding='utf-8-sig') as f:
            return f.read()
    except OSError:
        return ''


def sdir(book):
    return os.path.join(CO.projects_root(), book, SETTINGS)


def sections(text, skip=()):
    """## 标题 -> 段落。"""
    out, cur, buf = {}, None, []
    for ln in text.split('\n'):
        if ln.startswith('## '):
            if cur:
                out[cur] = '\n'.join(buf).strip()
            cur = ln[3:].strip()
            buf = [ln]
        elif cur:
            buf.append(ln)
    if cur:
        out[cur] = '\n'.join(buf).strip()
    for k in list(out):
        if any(s in k for s in skip):
            out.pop(k)
    return out


def rows(text, header_keys, limit=None):
    """md 表格 -> list[dict]；遇到新表头重新开始（只取第一张匹配表）。"""
    out, header = [], None
    for ln in text.split('\n'):
        s = ln.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if header is None:
            if all(any(k in c for c in cells) for k in header_keys):
                header = cells
            continue
        if set(''.join(cells)) <= set('-: '):
            continue
        out.append(dict(zip(header, cells)))
        if limit and len(out) >= limit:
            break
    return out


def bare(name):
    """去掉「一、」「（一）」序号和（主角）这类后缀。"""
    name = re.sub(r'^[一二三四五六七八九十百]+、', '', name).strip()
    name = re.sub(r'^（[一二三四五六七八九十百]+）', '', name).strip()
    for a, b in (('（', '）'), ('(', ')')):
        while a in name and b in name:
            i1, i2 = name.find(a), name.find(b, name.find(a))
            if i1 < 0 or i2 < 0:
                break
            name = (name[:i1] + name[i2 + 1:]).strip()
    return name


def chapter_no(s):
    m = re.search(r'(\d+)', s or '')
    return int(m.group(1)) if m else None


def collect_entities(base, context, idx=None):
    """取出所有角色/地名，再按 context 命中筛。

    有索引时直接用索引的 key（不再读文件）；无索引退回全扫。
    照抄 Dataview 的思路：索引是权威，文件只是数据源。
    """
    if idx is not None:
        chars = list(idx.by_character.keys())
        places = list(idx.by_place.keys())
        # 按出现章数排序（出现越多的越重要）
        chars.sort(key=lambda c: -len(idx.by_character.get(c, [])))
        places.sort(key=lambda p: -len(idx.by_place.get(p, [])))
    else:
        chars = []
        for name in sections(read(os.path.join(base, '角色状态.md')), skip=('更新规则', '审稿团')):
            chars.append(bare(name))
        places = [r.get('地点') for r in rows(read(os.path.join(base, '世界地图.md')), ['地点', '距离'])]
        places = [p for p in places if p]

    hit_chars = [c for c in chars if c and c in context] or chars[:2]
    hit_places = [p for p in places if p and p in context] or places[:2]
    return hit_chars, hit_places, chars, places


def recent_summaries(base, upto_no, n=RECENT_N, idx=None):
    text = read(os.path.join(base, '章节摘要.md'))
    blocks = re.findall(r'^###\s*(\d{3})[^\n]*\n(.*?)(?=^###\s|\Z)', text, re.S | re.M)
    picked = []
    for num, body in blocks:
        no = int(num)
        if upto_no is None or no < upto_no:
            picked.append((no, body.strip()))
    picked.sort()
    return picked[-n:]


def foreshadows(base, limit=MAX_FORESHADOW):
    text = read(os.path.join(base, '伏笔.md'))
    seg = text.split('## 已埋未收', 1)
    if len(seg) != 2:
        return []
    body = seg[1].split('\n## ', 1)[0]
    out = []
    for r in rows(body, ['编号', '埋在哪章']):
        status = r.get('状态') or ''
        # 2026-11-08：加「待收」——它是「即将回收」，比「悬着」更该进写章上下文，
        # 之前漏了导致待收伏笔永远不被想起。
        if '悬着' in status or '未收' in status or '待收' in status:
            out.append(r)
    return out[:limit]


def hard_rules(base):
    text = read(os.path.join(base, '力量体系.md'))
    m = re.search(r'##\s*三、硬约束(.*?)(?=\n##\s|\Z)', text, re.S)
    if not m:
        return ''
    return re.sub(chr(96) * 3, '', m.group(1)).strip()


def _chapter_count(book):
    d = os.path.join(CO.projects_root(), book, '章节')
    return len([f for f in os.listdir(d) if f.endswith('.md')]) if os.path.isdir(d) else 0


def _load_chapter(book, no):
    d = os.path.join(CO.projects_root(), book, '章节')
    if not os.path.isdir(d) or no is None:
        return ''
    for f in os.listdir(d):
        if f.startswith('%03d' % no) and f.endswith('.md'):
            return read(os.path.join(d, f))
    return ''


def _from_index(idx, body, no, max_chars):
    """只读索引：不碰任何 md 文件。"""
    bag = idx.by_setting or {}
    chars = [c for c in (idx.by_character or {}) if c and c in body][:3] or list(idx.by_character)[:2]
    places = [p for p in (idx.by_place or {}) if p and p in body][:4] or list(idx.by_place)[:2]

    parts = ['【本章参考资料】']

    st = bag.get('角色状态') or {}
    cards = bag.get('角色卡') or {}
    blocks = []
    for name in chars:
        if st.get(name):
            blocks.append(st[name])
        sec7 = (cards.get(name) or {}).get('sec7')
        if sec7:
            blocks.append(sec7)
    if blocks:
        parts.append('\n## 相关角色\n' + '\n\n'.join(blocks))

    maps = bag.get('世界地图') or {}
    rows_ = [r for r in (maps.get('places') or []) if r.get('地点') in places][:6]
    lines = []
    if rows_:
        lines.append('| ' + ' | '.join(rows_[0].keys()) + ' |')
        lines += ['| ' + ' | '.join(r.values()) + ' |' for r in rows_]
    for r in (maps.get('routes') or []):
        if any(p in ' '.join(r.values()) for p in places):
            lines.append('| ' + ' | '.join(r.values()) + ' |')
    if lines:
        parts.append('\n## 相关地点\n' + '\n'.join(lines))

    cand = [int(c) for c in idx.chapters_for(chars + places) if str(c).isdigit()]
    cand = sorted(c for c in cand if no is None or c < no)
    ev = []
    for c in cand[-6:]:
        rec = idx.summary('%03d' % c)
        if rec.get('event'):
            ev.append('%03d：%s' % (c, rec['event']))
    if ev:
        parts.append('\n## 相关事件（索引）\n' + '\n'.join(ev))

    tl, recs = [], []
    for key in sorted(idx.by_chapter):
        if not str(key).isdigit():
            continue
        c = int(key)
        if no is not None and c >= no:
            continue
        rec = idx.by_chapter[key]
        if rec.get('timeline'):
            tl.append('%03d（%s）：%s' % (c, rec['timeline'], rec.get('place') or '—'))
        if rec.get('summary'):
            recs.append((c, rec['summary']))
    if tl:
        parts.append('\n## 时间线（最近）\n' + '\n'.join(tl[-3:]))

    if bag.get('卷摘要'):
        parts.append('\n## 本卷概要\n' + bag['卷摘要'][:600])
    if bag.get('全书摘要'):
        parts.append('\n## 全书主线\n' + bag['全书摘要'][:300])
    if recs:
        parts.append('\n## 最近发生了什么\n' + '\n\n'.join(
            '%d 章：%s' % (c, s) for c, s in recs[-RECENT_N:]))

    fs = bag.get('伏笔') or {}
    open_fs = [(k, v) for k, v in fs.items() if '已收' not in (v.get('状态') or '')]
    if open_fs:
        parts.append('\n## 未收伏笔\n' + '\n'.join(
            '%s（埋于 %s）：%s' % (k, v.get('埋章') or '?', v.get('内容') or '') for k, v in open_fs[:MAX_FORESHADOW]))

    rules = (bag.get('力量体系') or {}).get('硬约束')
    if rules:
        parts.append('\n## 不能破的规矩\n' + rules)

    out = '\n'.join(parts).strip()
    return out if len(out) <= max_chars else out[:max_chars].rstrip() + '\n…（已按预算截断）'


def _from_files(base, body, no, max_chars):
    chars, places, all_chars, all_places = collect_entities(base, body)
    parts = ['【本章参考资料】']
    st = sections(read(os.path.join(base, '角色状态.md')), skip=('更新规则', '审稿团'))
    card = sections(read(os.path.join(base, '角色卡.md')), skip=('用法', '审稿团'))
    blocks = []
    for name in chars[:3]:
        key = next((k for k in st if bare(k) == name), None)
        if key:
            blocks.append(st[key])
        hit = [card[k] for k in card if bare(k) == name]
        if hit:
            m = re.search(r'###\s*7\.[\s\S]*?(?=\n###\s*9\.|\Z)', hit[0])
            if m:
                blocks.append(m.group(0).strip())
    if blocks:
        parts.append('\n## 相关角色\n' + '\n\n'.join(blocks))

    map_text = read(os.path.join(base, '世界地图.md'))
    place_rows = rows(map_text, ['地点', '距离'])
    route_rows = rows(map_text, ['路线', '步行'])
    if places:
        hit = [r for r in place_rows if r.get('地点') in places][:6]
        lines = ['| ' + ' | '.join(hit[0].keys()) + ' |'] if hit else []
        lines += ['| ' + ' | '.join(r.values()) + ' |' for r in hit]
        lines += ['| ' + ' | '.join(r.values()) + ' |' for r in route_rows
                  if any(p in ' '.join(r.values()) for p in places)][:4]
        if lines:
            parts.append('\n## 相关地点\n' + '\n'.join(lines))

    ev_rows = rows(read(os.path.join(base, '事件索引.md')), ['章', '故事内时间', '一句话事件'])
    hits = [r for r in ev_rows
            if any(c in ((r.get('关键角色') or '') + (r.get('关键地点') or '')) for c in chars)
            or any(p in ((r.get('关键角色') or '') + (r.get('关键地点') or '')) for p in places)]
    if hits:
        parts.append('\n## 相关事件（事件索引）\n' + '\n'.join(
            '%s（%s）：%s' % (r.get('章'), r.get('故事内时间'), r.get('一句话事件')) for r in hits[-6:]))

    tl_rows = rows(read(os.path.join(base, '时间线.md')), ['章', '故事内时间'])
    tl_prev = [r for r in tl_rows if chapter_no(r.get('章')) is not None
               and (no is None or chapter_no(r.get('章')) < no)]
    if tl_prev:
        parts.append('\n## 时间线（最近）\n' + '\n'.join(
            '%s（%s，%s）：%s' % (r.get('章'), r.get('故事内时间'), r.get('地点'), r.get('关键事件'))
            for r in tl_prev[-3:]))

    sm_text = read(os.path.join(base, '章节摘要.md'))
    if '## 卷摘要' in sm_text:
        vol = sm_text.split('## 卷摘要', 1)[1].split('## 全书摘要', 1)[0].strip()
        if vol:
            parts.append('\n## 本卷概要\n' + vol[:600])
    if '## 全书摘要' in sm_text:
        whole = sm_text.split('## 全书摘要', 1)[1].split('## 更新规则', 1)[0].strip()
        if whole:
            parts.append('\n## 全书主线\n' + whole[:300])

    recent = recent_summaries(base, no)
    if recent:
        parts.append('\n## 最近发生了什么\n' + '\n\n'.join('%d 章：%s' % (n, b) for n, b in recent))

    fs = foreshadows(base)
    if fs:
        parts.append('\n## 未收伏笔\n' + '\n'.join(
            '%s（埋于 %s）：%s' % (r.get('编号'), r.get('埋在哪章'), r.get('内容')) for r in fs))

    rules = hard_rules(base)
    if rules:
        parts.append('\n## 不能破的规矩\n' + rules)

    out = '\n'.join(parts).strip()
    return out if len(out) <= max_chars else out[:max_chars].rstrip() + '\n…（已按预算截断）'


_RENDER_CACHE = {}


def recall(book, chapter_hint=None, text=None, max_chars=4000, use_index=True):
    """写第 N 章前的参考资料。有索引且书够大 -> 只读 .index.json；否则读 md。"""
    base = sdir(book)
    if not os.path.isdir(base):
        return ''
    no = chapter_no(chapter_hint)
    body = text or _load_chapter(book, no)
    idx = None
    if use_index and _chapter_count(book) >= INDEX_MIN_CHAPTERS:
        try:
            import memory_index as MI
            idx = MI.open_index(book)
        except Exception:
            idx = None
    if idx is not None:
        key = (book, no, idx.revision, len(body))
        hit = _RENDER_CACHE.get(key)
        if hit is not None:
            return hit
        out = _from_index(idx, body, no, max_chars)
        if len(_RENDER_CACHE) > 32:
            _RENDER_CACHE.clear()
        _RENDER_CACHE[key] = out
        return out
    return _from_files(base, body, no, max_chars)


def main():
    ap = argparse.ArgumentParser(description='写前记忆检索')
    ap.add_argument('--book', required=True)
    ap.add_argument('--ch', default=None)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    out = recall(args.book, args.ch)
    if args.json:
        print(json.dumps({'book': args.book, 'chapter': args.ch, 'chars': len(out),
                          'text': out}, ensure_ascii=False, indent=2))
    else:
        print('《%s》%s 参考资料：%d 字' % (args.book, args.ch or '', len(out)))
        print('-' * 66)
        print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())