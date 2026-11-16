# -*- coding: utf-8 -*-
"""记忆索引 MemoryIndex（schema 3）—— 账本 → 结构化索引 + 文本缓存

schema 3 的关键变化：把「回忆时要用的文本」也存进索引（by_setting），
recall 只读 .index.json，不再碰任何 .md 文件。

设计来源：blacksmithgu/obsidian-dataview src/data-index/index.ts（MIT）
  1. revision 单调递增（任何索引变化 +1）
  2. 增量重载：mtime（纳秒）没变的文件跳过
  3. 反向链接：backlinks("甲") -> ['001','002','003']
  4. 双链：[[名字]] 自动建索引

用法：
    python core/memory_index.py --book <书名>
    python core/memory_index.py --book <书名> --backlinks 甲
    python core/memory_index.py --book <书名> --reindex
"""
import argparse
import json
import os
import re
import sys
import time

INDEX_FILE = '.index.json'
SCHEMA = 3
WIKI_RE = re.compile(r'\[\[([^\[\]|#]{1,24})(?:[|#][^\[\]]*)?\]\]')
SETTING_FILES = ('角色状态.md', '角色卡.md', '世界地图.md', '伏笔.md', '力量体系.md', '章节摘要.md')


def _mtime(path):
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return 0


def _read(path):
    try:
        with open(path, encoding='utf-8-sig') as f:
            return f.read()
    except OSError:
        return ''


def _ch3(value):
    m = re.search(r'(\d{1,3})', str(value or ''))
    return m.group(1).zfill(3) if m else None


def _bare(name):
    n = re.sub(r'^[一二三四五六七八九十百]+、', '', (name or '').strip()).strip()
    n = re.sub(r'^（[一二三四五六七八九十百]+）', '', n).strip()
    for a, b in (('（', '）'), ('(', ')')):
        while a in n and b in n:
            i1, i2 = n.find(a), n.find(b, n.find(a))
            if i1 < 0 or i2 < 0:
                break
            n = (n[:i1] + n[i2 + 1:]).strip()
    return n


def _table(text, header_keys, stop_at_blank=True):
    """只解析第一张表（遇到表格后的空行就收工），避免把后面同列名的表也吞进来。"""
    out, header = [], None
    for line in text.split('\n'):
        s = line.strip()
        if not s.startswith('|'):
            if header is not None and out and stop_at_blank:
                break
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if header is None:
            if all(any(k in c for c in cells) for k in header_keys):
                header = cells
            continue
        if set(''.join(cells)) <= set('-: '):
            continue
        out.append(dict(zip(header, cells)))
    return out


def _sections(text, skip=()):
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
            out.pop(k, None)
    return out


class MemoryIndex:
    def __init__(self, book_dir, index_path=None):
        self.book_dir = os.path.abspath(book_dir)
        self.setting_dir = os.path.join(self.book_dir, '设定库')
        self.chapter_dir = os.path.join(self.book_dir, '章节')
        self._index_path = index_path
        self.revision = 0
        self.by_character = {}
        self.by_place = {}
        self.by_foreshadow = {}
        self.by_time = {}
        self.by_tag = {}
        self.by_chapter = {}
        self.by_setting = {}
        self.wiki = {}
        self.mtime = {}
        self.last_scan = {}
        self._roles_cache = None
        self._places_cache = None
        self.load()

    # ---------------- 持久化 ----------------
    @property
    def index_path(self):
        return self._index_path or os.path.join(self.book_dir, INDEX_FILE)

    def load(self):
        try:
            with open(self.index_path, encoding='utf-8') as f:
                d = json.load(f)
        except (OSError, ValueError):
            return False
        if d.get('schema') != SCHEMA:
            return False
        self.revision = int(d.get('revision') or 0)
        self.by_character = d.get('by_character') or {}
        self.by_place = d.get('by_place') or {}
        self.by_foreshadow = {k: self._norm_fs(v) for k, v in (d.get('by_foreshadow') or {}).items()}
        self.by_time = d.get('by_time') or {}
        self.by_tag = d.get('by_tag') or {}
        self.by_chapter = d.get('by_chapter') or {}
        self.by_setting = d.get('by_setting') or {}
        self.wiki = d.get('wiki') or {}
        self.mtime = d.get('mtime') or {}
        return True

    def save(self):
        d = {
            'schema': SCHEMA, 'revision': self.revision, 'saved_at': int(time.time()),
            'by_character': self.by_character, 'by_place': self.by_place,
            'by_foreshadow': self.by_foreshadow, 'by_time': self.by_time,
            'by_tag': self.by_tag, 'by_chapter': self.by_chapter,
            'by_setting': self.by_setting, 'wiki': self.wiki, 'mtime': self.mtime,
        }
        tmp = self.index_path + '.tmp'
        try:
            os.makedirs(os.path.dirname(self.index_path) or '.', exist_ok=True)
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False, separators=(',', ':'))
            os.replace(tmp, self.index_path)
            return True
        except OSError:
            return False

    @staticmethod
    def _norm_fs(v):
        if not isinstance(v, dict):
            return {'埋': [], '收': []}
        return {'埋': list(v.get('埋') or v.get('planted') or []),
                '收': list(v.get('收') or v.get('resolved') or [])}

    # ---------------- 文件 ----------------
    def _files(self):
        out = []
        for d in (self.setting_dir, self.chapter_dir):
            if not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                if name.endswith('.md'):
                    out.append(os.path.join(d, name))
        return out

    def _dict_roles(self):
        names = set()
        for fname in ('角色卡.md', '角色状态.md'):
            t = _read(os.path.join(self.setting_dir, fname))
            for m in re.finditer(r'^##\s+(?:[一二三四五六七八九十]+、)?([^\n(（]{1,12})', t, re.M):
                nm = m.group(1).strip()
                if 1 <= len(nm) <= 8 and '规则' not in nm:
                    names.add(nm)
        return names

    def _dict_places(self):
        t = _read(os.path.join(self.setting_dir, '世界地图.md'))
        return {_bare(r.get('地点')) for r in _table(t, ['地点', '距离']) if r.get('地点')}

    # ---------------- 章节解析 ----------------
    def _parse_chapter(self, path):
        text = _read(path)
        name = os.path.basename(path)
        m = re.match(r'(\d{3})', name)
        ch = m.group(1) if m else os.path.splitext(name)[0]
        if self._roles_cache is None:
            self._roles_cache = self._dict_roles()
        if self._places_cache is None:
            self._places_cache = self._dict_places()
        return {
            'chapter': ch,
            'text': text,
            'roles': sorted([n for n in self._roles_cache if n in text], key=lambda n: -text.count(n)),
            'places': sorted([p for p in self._places_cache if p in text], key=lambda n: -text.count(n)),
            'times': sorted(set(sum([re.findall(p, text) for p in
                                     (r'第[一二三四五六七八九十百\d]+天', r'次日', r'翌日', r'上个月')], []))),
        }

    def _add(self, mapping, key, ch):
        lst = mapping.setdefault(key, [])
        if ch and ch not in lst:
            lst.append(ch)
            lst.sort()

    def _drop_chapter(self, ch):
        for mapping in (self.by_character, self.by_place, self.by_time, self.by_tag):
            for k in list(mapping):
                if ch in mapping[k]:
                    mapping[k] = [c for c in mapping[k] if c != ch]
                    if not mapping[k]:
                        mapping.pop(k, None)
        for k in list(self.by_foreshadow):
            e = self.by_foreshadow[k]
            for fld in ('埋', '收'):
                e[fld] = [c for c in e.get(fld, []) if c != ch]

    # ---------------- 账本文本（schema 3） ----------------
    def _index_setting_file(self, path):
        name = os.path.basename(path)
        text = _read(path)
        bag = self.by_setting

        if name == '角色状态.md':
            secs = _sections(text, skip=('更新规则', '审稿团'))
            bag['角色状态'] = {_bare(k): v for k, v in secs.items()}
        elif name == '角色卡.md':
            secs = _sections(text, skip=('用法', '审稿团'))
            out = {}
            for k, v in secs.items():
                m7 = re.search(r'###\s*7\.[\s\S]*?(?=\n###\s*9\.|\Z)', v)
                out[_bare(k)] = {'raw': v, 'sec7': m7.group(0).strip() if m7 else ''}
            bag['角色卡'] = out
        elif name == '世界地图.md':
            arc = re.search(r'##\s*二、[^\n]*\n(.*?)(?=\n##\s*三、|\Z)', text, re.S)
            bag['世界地图'] = {
                'places': _table(text, ['地点', '距离']),
                'routes': _table(text, ['路线', '步行']),
                'speeds': _table(arc.group(1) if arc else '', ['方式', '速度']),
            }
        elif name == '伏笔.md':
            out = {}
            for r in _table(text, ['编号', '埋在哪章']):
                fid = (r.get('编号') or '').strip()
                if not re.match(r'F\d{2}', fid):
                    continue
                out[fid] = {'埋章': _ch3(r.get('埋在哪章')), '内容': r.get('内容', ''),
                            '状态': r.get('状态', ''), '建议': r.get('建议', '')}
                self.by_foreshadow.setdefault(fid, {'埋': [], '收': []})
                ch = _ch3(r.get('埋在哪章'))
                if ch and ch not in self.by_foreshadow[fid]['埋']:
                    self.by_foreshadow[fid]['埋'].append(ch)
                    self.by_foreshadow[fid]['埋'].sort()
            bag['伏笔'] = out
        elif name == '力量体系.md':
            m = re.search(r'##\s*三、硬约束(.*?)(?=\n##\s|\Z)', text, re.S)
            bag['力量体系'] = {'硬约束': re.sub(chr(96) * 3, '', m.group(1)).strip() if m else ''}
        elif name == '章节摘要.md':
            if '## 卷摘要' in text:
                bag['卷摘要'] = text.split('## 卷摘要', 1)[1].split('## 全书摘要', 1)[0].strip()[:800]
            if '## 全书摘要' in text:
                bag['全书摘要'] = text.split('## 全书摘要', 1)[1].split('## 更新规则', 1)[0].strip()[:500]

    def _index_one(self, path):
        name = os.path.basename(path)
        is_chapter = path.startswith(self.chapter_dir + os.sep)
        if is_chapter:
            info = self._parse_chapter(path)
            ch = info['chapter']
            self._drop_chapter(ch)
            for r in info['roles']:
                self._add(self.by_character, r, ch)
            for p in info['places']:
                self._add(self.by_place, p, ch)
            for t in info['times']:
                self._add(self.by_time, t, ch)
            self.by_chapter.setdefault(ch, {})['title'] = os.path.splitext(name)[0]
            for m in WIKI_RE.finditer(info['text']):
                target = m.group(1).strip()
                if target:
                    self._add(self.wiki, target, ch)
            return

        self._index_setting_file(path)
        self._index_setting_rows(path)

    def _index_setting_rows(self, path):
        name = os.path.basename(path)
        text = _read(path)
        if name == '事件索引.md':
            for r in _table(text, ['章', '故事内时间', '一句话事件']):
                ch = _ch3(r.get('章'))
                if not ch:
                    continue
                rec = self.by_chapter.setdefault(ch, {})
                rec['event'] = r.get('一句话事件', '')
                t = (r.get('故事内时间') or '').strip()
                if t and '未说明' not in t:
                    rec['time'] = t
                    self._add(self.by_time, t, ch)
                for who in re.split(r'[、,，\s]+', r.get('关键角色') or ''):
                    if who.strip():
                        self._add(self.by_character, who.strip(), ch)
                for pl in re.split(r'[、,，\s]+', r.get('关键地点') or ''):
                    if pl.strip():
                        self._add(self.by_place, pl.strip(), ch)
        elif name == '时间线.md':
            for r in _table(text, ['章', '故事内时间']):
                ch = _ch3(r.get('章'))
                if not ch:
                    continue
                rec = self.by_chapter.setdefault(ch, {})
                t = (r.get('故事内时间') or '').strip()
                if t:
                    rec['timeline'] = t
                pl = (r.get('地点') or '').strip()
                if pl:
                    rec['place'] = pl
        elif name == '章节摘要.md':
            for m in re.finditer(r'^###\s*(\d{1,3})[^\n]*\n(.*?)(?=^###\s|^##\s|\Z)',
                                 text, re.S | re.M):
                ch = m.group(1).zfill(3)
                self.by_chapter.setdefault(ch, {})['summary'] = m.group(2).strip()[:400]

    # ---------------- 构建 ----------------
    def scan(self, force=False):
        self._roles_cache = None
        self._places_cache = None
        if force:
            self.by_character, self.by_place, self.by_time = {}, {}, {}
            self.by_tag, self.by_foreshadow = {}, {}
            self.by_chapter, self.wiki, self.by_setting, self.mtime = {}, {}, {}, {}
        parsed = skipped = 0
        for p in self._files():
            mt = _mtime(p)
            if not force and self.mtime.get(p) == mt:
                skipped += 1
                continue
            self._index_one(p)
            self.mtime[p] = mt
            parsed += 1
        if parsed:
            self.revision += 1
            self.save()
        self.last_scan = {'parsed': parsed, 'skipped': skipped}
        return parsed, skipped

    def reload(self, path):
        p = os.path.abspath(path)
        mt = _mtime(p)
        if self.mtime.get(p) == mt:
            return {'cached': True, 'skipped': True}
        self._roles_cache = None
        self._places_cache = None
        self._index_one(p)
        self.mtime[p] = mt
        self.revision += 1
        self.save()
        return {'cached': False, 'skipped': False, 'revision': self.revision}

    def build(self, force=False):
        parsed, skipped = self.scan(force=force)
        return {'rebuilt': bool(parsed), 'parsed': parsed, 'skipped': skipped,
                'revision': self.revision}

    # ---------------- 查询 ----------------
    def backlinks(self, name):
        out = []
        for mapping in (self.by_character, self.by_place, self.wiki):
            for ch in mapping.get(name, []):
                if ch not in out:
                    out.append(ch)
        return sorted(out)

    def chapters_with(self, field, value):
        mapping = {'角色': self.by_character, '地点': self.by_place, '时间': self.by_time}.get(field)
        return list(mapping.get(value, [])) if mapping else []

    def chapters_for(self, names):
        out = set()
        for n in names or []:
            out.update(self.backlinks(n))
        return sorted(out)

    def summary(self, ch):
        key = ch if isinstance(ch, str) else str(ch).zfill(3)
        return self.by_chapter.get(key, {})

    def open_foreshadows(self):
        return sorted([k for k, v in self.by_foreshadow.items() if not v.get('收')])

    def stats(self):
        return {
            'schema': SCHEMA, 'revision': self.revision,
            'chapters': len(self.by_chapter), 'characters': len(self.by_character),
            'places': len(self.by_place), 'foreshadows': len(self.by_foreshadow),
            'setting_blocks': len(self.by_setting), 'wiki_links': len(self.wiki),
            'files': len(self.mtime), 'last_scan': self.last_scan,
            'path': self.index_path,
        }


_CACHE = {}


_SETTING_NAMES = ('角色状态.md', '角色卡.md', '世界地图.md', '伏笔.md',
                  '力量体系.md', '章节摘要.md', '事件索引.md', '时间线.md')


def _fresh(idx):
    """只 stat 固定的 8 个账本文件；有变化就要重扫（不 listdir 章节）。"""
    for name in _SETTING_NAMES:
        f = os.path.join(idx.setting_dir, name)
        if idx.mtime.get(f) != _mtime(f):
            return False
    return True


def open_index(book, root=None, refresh='auto'):
    """进程内缓存索引：refresh=True 强制扫描；'auto' 只在账本变化时重扫。"""
    import coordinator as _CO
    bd = os.path.join(root or _CO.projects_root(), book)
    idx = _CACHE.get(bd)
    if idx is None:
        idx = MemoryIndex(bd)
        idx.scan()
        _CACHE[bd] = idx
    elif refresh is True:
        idx.scan()
    elif refresh == 'auto' and not _fresh(idx):
        idx.scan()
    return idx


def drop_cache(book=None, root=None):
    import coordinator as _CO
    if book is None:
        _CACHE.clear()
        return
    bd = os.path.join(root or _CO.projects_root(), book)
    _CACHE.pop(bd, None)


def main():
    ap = argparse.ArgumentParser(description='账本索引（schema 3：结构化 + 文本缓存）')
    ap.add_argument('--book', default='<书名>')
    ap.add_argument('--backlinks', default=None)
    ap.add_argument('--reindex', action='store_true')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    import coordinator as CO
    bd = os.path.join(CO.projects_root(), args.book)
    idx = MemoryIndex(bd)
    t0 = time.time()
    idx.scan(force=args.reindex)
    took = (time.time() - t0) * 1000

    if args.backlinks:
        bl = idx.backlinks(args.backlinks)
        print(json.dumps({'name': args.backlinks, 'chapters': bl, 'revision': idx.revision},
                         ensure_ascii=False) if args.json else
              '%s 的反向链接：%s（%d 章）revision=%d' % (args.backlinks, bl, len(bl), idx.revision))
        return 0

    d = idx.stats()
    d['scan_ms'] = round(took, 2)
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print('索引：%s' % d['path'])
        print('  schema=%d revision=%d 章=%d 角色=%d 地点=%d 伏笔=%d 文本块=%d 双链=%d 文件=%d' % (
            d['schema'], d['revision'], d['chapters'], d['characters'], d['places'],
            d['foreshadows'], d['setting_blocks'], d['wiki_links'], d['files']))
        print('  本次：解析 %d，跳过 %d（%.1f ms）' % (
            d['last_scan'].get('parsed', 0), d['last_scan'].get('skipped', 0), took))
    return 0


if __name__ == '__main__':
    sys.exit(main())
