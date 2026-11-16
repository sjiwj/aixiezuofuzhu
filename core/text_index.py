# -*- coding: utf-8 -*-
"""中文检索：内置词表（角色名/地名）+ 最长匹配 + 2-gram 兜底 + SQLite FTS5

为什么不用 jieba：它是 C 扩展，打进 Electron 很麻烦；而且我们只需要
「角色名/地名/物品名」这类专有名词，词表可以直接从账本自动生成。

用法:
    python core/text_index.py --book <书名> --build
    python core/text_index.py --book <书名> --search 滩
    python core/text_index.py --book <书名> --vocab
"""
import argparse
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

DB_NAME = '.index.db'
VOCAB_NAME = '.tokens.json'
MAX_WORD = 8


def _read(p):
    try:
        with open(p, encoding='utf-8-sig') as f:
            return f.read()
    except OSError:
        return ''


def _bare(n):
    n = re.sub(r'^[一二三四五六七八九十百]+、', '', (n or '').strip()).strip()
    n = re.sub(r'^（[一二三四五六七八九十百]+）', '', n).strip()
    for a, b in (('（', '）'), ('(', ')')):
        while a in n and b in n:
            i1, i2 = n.find(a), n.find(b, n.find(a))
            if i1 < 0 or i2 < 0:
                break
            n = (n[:i1] + n[i2 + 1:]).strip()
    return n


STOP_CHARS = ('的', '是', '在', '了', '和', '与', '就', '都', '也', '还', '被', '把')
NOISE_WORDS = {'悬着', '已收', '待定', '后续', '后续待定', '内容', '建议', '状态', '备注', '编号',
               '相对方位', '距离', '地形', '方式', '速度', '条件', '路线', '步行', '挑担',
               '快跑', '境界', '门槛', '典型耗时', '战力倍数', '章', '故事内时间',
               '关键事件', '距上一章', '关键角色', '关键地点', '一句话事件', '地点'}
MD_CHARS = '[*_' + chr(96) + '~#|]'


def _clean_word(w):
    """去 markdown / 引号 / 标点，过长度与句子特征过滤。"""
    w = str(w or '')
    w = re.sub(MD_CHARS, '', w)
    w = w.strip(' \t\u3000「」『』“”\'\"（）()【】[]，,。.、：:；;！!？?—-')
    w = w.strip()
    w = re.sub(r'^(主角|配角|反派|路人|次要角色)[·・.、]+', '', w).strip()
    if not (2 <= len(w) <= 12):
        return None
    if any(c in w for c in '（）()【】[]「」『』“”\'"' + chr(96)):
        return None        # 括号/引号没配对干净的碎片
    if any(c in w for c in '、，,。；;'):
        return None        # 多条目短语，不是名字
    if any(c in w for c in '那这其此'):
        return None        # 「梦里那条走廊」「中间那个字」这类指代句
    if w in NOISE_WORDS:
        return None
    if len(w) > 6 and any(c in w for c in STOP_CHARS):
        return None        # 「买年岁的人是」这类句子碎片
    if not re.search(r'[\u4e00-\u9fa5A-Za-z0-9]', w):
        return None
    return w


def _head_names(text):
    """只从 ## 标题抽名字；括号里的别名也单独收（老头（<书名>掌柜）→ 老头 + <书名>掌柜）。"""
    out = []
    for line in (text or '').split('\n'):
        if not line.startswith('## '):
            continue
        raw = line[3:].strip()
        if any(k in raw for k in ('规则', '用法', '怎么用')):
            continue
        aliases = re.findall(r'[（(]([^（()）]{2,12})[)）]', raw)
        main = re.sub(r'[（(][^（()）]*[)）]', '', raw).strip()
        main = re.sub(r'^[一二三四五六七八九十百]+、', '', main).strip()
        main = re.sub(r'^\d+[、.]', '', main).strip()
        for cand in [main] + aliases:
            w = _clean_word(cand)
            if w and w not in ('主角', '配角'):
                out.append(w)
    return out


def _table_first_col(text, header_key):
    """只取「表头含 header_key」的第一张表的第一列。"""
    header, out = None, []
    for line in (text or '').split('\n'):
        s = line.strip()
        if not s.startswith('|'):
            if header is not None and out:
                break
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if header is None:
            if any(header_key in c for c in cells):
                header = cells
            continue
        if set(''.join(cells)) <= set('-: '):
            continue
        if cells and cells[0]:
            out.append(cells[0])
    return out


def _foreshadow_words(text):
    """伏笔表：只从「内容」列抽，优先引号里的短语，其次整格（要过 _clean_word）。"""
    words = []
    for line in (text or '').split('\n'):
        s = line.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if len(cells) < 3 or not re.match(r'F\d{2}', cells[0]):
            continue
        content = cells[2]
        quoted = re.findall(r'[「『“"]([^」』”"]{2,12})[」』”"]', content)
        for q in quoted:
            w = _clean_word(q)
            if w:
                words.append(w)
        if not quoted:
            w = _clean_word(content)
            if w:
                words.append(w)
    return words


def build_vocab(book, root=None):
    """从账本的结构化「名字位」抽词：## 标题 / 地点列 / 境界列 / 伏笔引号短语。"""
    base = os.path.join(root or CO.projects_root(), book)
    sdir = os.path.join(base, '设定库')
    words = set()
    for fname in ('角色卡.md', '角色状态.md'):
        words.update(_head_names(_read(os.path.join(sdir, fname))))
    words.update(w for w in map(_clean_word, _table_first_col(
        _read(os.path.join(sdir, '世界地图.md')), '地点')) if w)
    words.update(w for w in map(_clean_word, _table_first_col(
        _read(os.path.join(sdir, '力量体系.md')), '境界')) if w)
    words.update(_foreshadow_words(_read(os.path.join(sdir, '伏笔.md'))))
    return sorted(words, key=lambda w: (-len(w), w))


def save_vocab(book, words, root=None):
    p = os.path.join(root or CO.projects_root(), book, VOCAB_NAME)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump({'words': words}, f, ensure_ascii=False, indent=1)
    return p


def load_vocab(book, root=None):
    p = os.path.join(root or CO.projects_root(), book, VOCAB_NAME)
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f).get('words') or []
    except (OSError, ValueError):
        return []


def tokenize(text, vocab):
    """最长匹配优先（词表），剩下的按 2-gram 兜底；单字只保留词表里出现过的字。"""
    s = str(text or '')
    words = sorted(vocab, key=len, reverse=True)
    vocab_chars = {ch for w in words for ch in w if re.match(r'[\u4e00-\u9fa5]', ch)}
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if not re.match(r'[\u4e00-\u9fa5A-Za-z0-9]', ch):
            i += 1
            continue
        hit = None
        for w in words:
            if len(w) > MAX_WORD:
                continue
            if s.startswith(w, i):
                hit = w
                break
        if hit:
            # 词表命中：整词 + 它的 2-gram + 单字都入库，
            # 这样「示例滩」既能整词命中，也能被「滩」「回滩」命中
            out.append(hit)
            for k in range(len(hit) - 1):
                out.append(hit[k:k + 2])
            out.extend(list(hit))
            i += len(hit)
            continue
        if i + 1 < n and re.match(r'[\u4e00-\u9fa5A-Za-z0-9]', s[i + 1]):
            out.append(s[i:i + 2])      # 2-gram 兜底
        if ch in vocab_chars:            # 单字只留词表里出现过的（滩/铺/镇…），控制索引体积
            out.append(ch)
        i += 1
    return out


def db_path(book, root=None):
    return os.path.join(root or CO.projects_root(), book, DB_NAME)


def connect(book, root=None):
    p = db_path(book, root)
    con = sqlite3.connect(p)
    con.execute('CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5('
                'tokens, chapter UNINDEXED, kind UNINDEXED, ref UNINDEXED)')
    return con


def build(book, root=None):
    vocab = build_vocab(book, root)
    save_vocab(book, vocab, root)
    base = os.path.join(root or CO.projects_root(), book)
    cdir = os.path.join(base, '章节')
    con = connect(book, root)
    with con:
        con.execute('DELETE FROM memories')
        n = 0
        if os.path.isdir(cdir):
            for f in sorted(os.listdir(cdir)):
                if not f.endswith('.md'):
                    continue
                ch = f[:3]
                text = _read(os.path.join(cdir, f))
                # 只索引正文，不索引文件名/标题（避免「002-第二章-示例滩.md」把 002 也带进来）
                body = re.sub(r'^\s*#.*$', '', text, count=1, flags=re.M)
                toks = tokenize(body, vocab)
                con.execute('INSERT INTO memories(tokens, chapter, kind, ref) VALUES (?,?,?,?)',
                            (' '.join(toks), ch, 'chapter', f))
                n += 1
                # 账本条目也进索引（按文件）
        sdir = os.path.join(base, '设定库')
        if os.path.isdir(sdir):
            for f in sorted(os.listdir(sdir)):
                if not f.endswith('.md'):
                    continue
                text = _read(os.path.join(sdir, f))
                toks = tokenize(text, vocab)
                con.execute('INSERT INTO memories(tokens, chapter, kind, ref) VALUES (?,?,?,?)',
                            (' '.join(toks), '', 'setting', f))
    con.close()
    return {'ok': True, 'vocab': len(vocab), 'chapters': n,
            'db': db_path(book, root), 'vocab_path': os.path.join(base, VOCAB_NAME)}


def search(book, query, limit=20, root=None):
    vocab = load_vocab(book, root) or build_vocab(book, root)
    toks = tokenize(query, vocab)
    if not toks:
        return {'ok': True, 'query': query, 'tokens': [], 'hits': []}
    # 查询只用于长度>=2 的 token（词/2-gram）；单字仅当查询本身就是单字时才用
    primary = [t for t in toks if len(t) >= 2] or toks
    con = connect(book, root)
    expr = ' OR '.join('"%s"' % t for t in primary)
    rows = con.execute(
        'SELECT chapter, kind, ref, bm25(memories) AS rank FROM memories '
        'WHERE memories MATCH ? ORDER BY rank LIMIT ?', (expr, limit)).fetchall() \
        if False else con.execute(
        'SELECT chapter, kind, ref, bm25(memories) AS rank FROM memories '
        'WHERE memories MATCH ? ORDER BY rank LIMIT ?', (expr, limit)).fetchall()
    con.close()
    base = os.path.join(root or CO.projects_root(), book)
    cdir = os.path.join(base, '章节')
    bodies = {}
    for f in (os.listdir(cdir) if os.path.isdir(cdir) else []):
        if f.endswith('.md'):
            bodies[f[:3]] = _read(os.path.join(cdir, f))
    q = query.strip()
    hits = []
    for r in rows:
        ch, kind, ref, rank = r
        exact = bool(ch) and q and q in bodies.get(ch, '')
        hits.append({'chapter': ch, 'kind': kind, 'ref': ref,
                     'score': round(-rank, 4), 'exact': exact})
    # 有精确子串命中时，只报精确的（模糊命中留在 fuzzy 里供排查）
    exact_hits = [h for h in hits if h['exact']]
    fuzzy_hits = [h for h in hits if not h['exact']]
    if exact_hits:
        hits = exact_hits + fuzzy_hits[:3]
    return {'ok': True, 'query': query, 'tokens': toks, 'primary': primary, 'expr': expr,
            'chapters': sorted({h['chapter'] for h in (exact_hits or hits) if h['chapter']}),
            'exact_count': len(exact_hits),
            'hits': hits}


def main():
    ap = argparse.ArgumentParser(description='中文检索（内置词表 + 2-gram + FTS5）')
    ap.add_argument('--book', required=True)
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--search', default=None)
    ap.add_argument('--vocab', action='store_true')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    if args.build:
        r = build(args.book)
        print('已建索引：词表 %d 词，章节 %d 章' % (r['vocab'], r['chapters']))
        print('  db: %s' % r['db'])
        print('  词表: %s' % r['vocab_path'])
        return 0
    if args.vocab:
        v = load_vocab(args.book) or build_vocab(args.book)
        print('词表 %d 词：%s' % (len(v), '、'.join(v[:40])))
        return 0
    if args.search:
        r = search(args.book, args.search)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print('查询：%s  → 切词 %s' % (r['query'], r['tokens']))
            print('命中章节：%s' % (r['chapters'] or '（无）'))
            for h in r['hits'][:8]:
                print('  %-8s %-8s %s' % (h['chapter'] or '-', h['kind'], h['ref']))
        return 0
    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
