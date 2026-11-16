#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""结构指标统计 v2 —— 判断章纲是否真的管住了结构（口径 2026-11-07 重写）

三个指标，全部改成「可核对 / 可配置 / 不假装」：

  1) 主冲突位置   人工锚点 + 段落位置
     锚点写在 structure_anchors.json（作者指定这一章的冲突句在哪几段）。
     程序只算：首冲突字位、前 20% / 20-50% / 后 50% 分布、与前置章对比。
     没配锚点 -> status=unconfigured，绝不输出 0%。

  2) 章纲落实度   章纲 <details> 块「必须做到的事」逐条对照正文
     引号内字面（「…」）逐字核对；含「先…再…」的条目核对先后顺序；
     否定分句（不许/不要/不得）无法机械核对，单独标出。
     没有 <details> 块 -> status=unconfigured。

  3) 设定外物件   只报专有名词 / 物件候选，且一律标注「疑似」
     引号内（对话/引语）先整体剔除，绝不从对话取词；
     轨道 A（结构型专名）= 书名号 / 姓氏+字 / 地名后缀 / 角色后缀；
     轨道 B（物件）= 量词+2-4 字名词（一斗米、两寸白线、一把柴刀）或
       持有动作（把…揣进 / 别在腰后 / 摸出… / 提着…）+2-4 字名词；
       末字必须落在实物尾字上，且不在「身上物品」白名单里；
       白名单默认取 角色状态.md 当前状态；加 --state-as-of 006 则取按章时点快照
       （只用章号严格小于 006 的 .story/state/chapter_*.json，即 006 开篇前的状态）；
     两条轨道合并输出：强候选 = warn（出现≥2 次），只出现一次的物件与
     设定库词表切不动的残段（2-5 字）= info。

只读：不写任何文件。
"""
import argparse
import io
import json
import os
import re
import sys

NL = chr(10)
CJK_RE = re.compile(r'[\u4e00-\u9fff]')
HEADING_RE = re.compile(r'^\s{0,3}#')
QUOTED_RE = re.compile(r'[「『“][^」』”\n]*[」』”]')
SINGLE_QUOTED_RE = re.compile(r'[‘][^’\n]*[’]')
TITLE_RE = re.compile(r'《([^》\n]{1,20})》')
LIT_RE = re.compile(r'[「『“]([^」』”\n]{1,30})[」』”]')

BUCKETS = ('前20%', '20-50%', '后50%')

# ---------------------------------------------------------------- 通用小工具

def read_text(path):
    with io.open(path, encoding='utf-8') as f:
        return f.read()


def cjk_len(s):
    return len(CJK_RE.findall(s))


def is_heading(line):
    return bool(HEADING_RE.match(line))


def body_paragraphs(text):
    """正文段落：去 frontmatter、去标题行、去空行。返回 [(文件行号, 段落文本)]"""
    lines = text.split('\n')
    start = 0
    if lines and lines[0].strip() == '---':
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                start = i + 1
                break
    out = []
    for i in range(start, len(lines)):
        s = lines[i].strip()
        if not s or is_heading(lines[i]):
            continue
        out.append((i + 1, s))
    return out


def chapter_no(path):
    """章号统一成 3 位（008），和全书大纲表格里的写法一致"""
    m = re.match(r'^(\d+)', os.path.basename(path))
    return '%03d' % int(m.group(1)) if m else None


def chapter_files(chapter_dir):
    out = {}
    for name in os.listdir(chapter_dir):
        if not name.endswith('.md'):
            continue
        n = chapter_no(name)
        if n:
            out[n] = os.path.join(chapter_dir, name)
    return out


# ------------------------------------------------------- 指标1：主冲突位置

def load_anchors(path):
    if not path or not os.path.exists(path):
        return None
    try:
        return json.loads(read_text(path))
    except ValueError as e:
        print('锚点文件不是合法 JSON: %s (%s)' % (path, e), file=sys.stderr)
        return None


def _bucket(ratio):
    if ratio < 0.2:
        return BUCKETS[0]
    if ratio <= 0.5:
        return BUCKETS[1]
    return BUCKETS[2]


def resolve_chapter_anchors(cfg, paras):
    """把锚点解析成字位。返回 (anchors, unplaced)"""
    total = sum(cjk_len(p) for _, p in paras)
    offsets = []
    acc = 0
    for _, p in paras:
        offsets.append(acc)
        acc += cjk_len(p)

    resolved, unplaced = [], []
    for a in cfg.get('conflict') or []:
        quote = (a.get('quote') or '').strip()
        para = a.get('para')
        hit = None
        if para and 1 <= para <= len(paras):
            p_text = paras[para - 1][1]
            if not quote or quote in p_text:
                within = cjk_len(p_text.split(quote)[0]) if quote else 0
                hit = (para, offsets[para - 1] + within, 'exact' if quote else 'para_only')
        if hit is None and quote:
            for idx, (_, p_text) in enumerate(paras):
                if quote in p_text:
                    hit = (idx + 1, offsets[idx] + cjk_len(p_text.split(quote)[0]),
                           'relocated' if para else 'by_quote')
                    break
        if hit is None:
            unplaced.append({'note': a.get('note') or '', 'quote': quote, 'para': para})
            continue
        p_idx, off, how = hit
        ratio = (off / total) if total else 0.0
        resolved.append({
            'para': p_idx,
            'line': paras[p_idx - 1][0],
            'quote': quote,
            'note': a.get('note') or '',
            'matched': how,
            'offset': off,
            'ratio': round(ratio, 4),
            'bucket': _bucket(ratio),
        })
    return resolved, unplaced


def conflict_metric(path, chapter_dir, anchors):
    text = read_text(path)
    paras = body_paragraphs(text)
    total = sum(cjk_len(p) for _, p in paras)
    key = chapter_no(path)
    cfg_all = (anchors or {}).get('chapters') or {}
    cfg = cfg_all.get(key)

    if not cfg or not (cfg.get('conflict')):
        return {
            'status': 'unconfigured',
            'chars_basis': 'body_only',
            'chars': total,
            'paragraphs': len(paras),
            'why': '第 %s 章没有配冲突锚点，程序不猜冲突在哪，所以不给百分比' % (key or '???'),
            'hint': '在 structure_anchors.json 的 chapters.%s.conflict 里填冲突句（quote 或 para）' % (key or '???'),
            'fix': [
                '打开脚本同目录 structure_anchors.json',
                '在 chapters 下加 "%s": {"conflict": [{"quote": "正文里的冲突句原文", "note": "为什么算冲突"}]}' % (key or '???'),
                'quote 只要正文里出现过即可，程序自己算它在第几段、占全文多少',
                '一段不确定就填多条，分布会一起统计',
            ],
            'example': {
                'chapter': '008',
                'conflict': [{'quote': '他说我年岁不够', 'note': '老头第一次说出「当三天」的交易条件，冲突在此成立'}],
            },
        }

    resolved, unplaced = resolve_chapter_anchors(cfg, paras)
    if not resolved:
        return {
            'status': 'unconfigured',
            'chars_basis': 'body_only',
            'chars': total,
            'paragraphs': len(paras),
            'unplaced': unplaced,
            'why': '锚点里的原句在正文里一句都找不到，多半是正文重写过',
            'hint': '按当前正文重新填 quote',
            'fix': ['重新复制正文里的原句作为 quote', '或改填 para（第几段）而不是 quote'],
        }

    dist = dict((b, 0) for b in BUCKETS)
    for a in resolved:
        dist[a['bucket']] += 1
    first = min(resolved, key=lambda a: a['offset'])

    out = {
        'status': 'ok',
        'chars_basis': 'body_only',
        'chars': total,
        'paragraphs': len(paras),
        'anchors': resolved,
        'unplaced': unplaced,
        'first_conflict': {
            'para': first['para'], 'line': first['line'], 'offset': first['offset'],
            'ratio': first['ratio'], 'bucket': first['bucket'], 'quote': first['quote'],
        },
        'distribution': dist,
    }
    out['prev'] = _prev_compare(key, chapter_dir, anchors, cfg_all)
    return out


def _prev_compare(key, chapter_dir, anchors, cfg_all):
    if not key:
        return {'status': 'unconfigured', 'reason': '本章章号无法解析'}
    files = chapter_files(chapter_dir)
    lower = sorted((n for n in cfg_all if n.isdigit() and int(n) < int(key)), key=int, reverse=True)
    for n in lower:
        p = files.get(n)
        if not p:
            continue
        paras = body_paragraphs(read_text(p))
        resolved, _ = resolve_chapter_anchors(cfg_all[n], paras)
        if not resolved:
            continue
        first = min(resolved, key=lambda a: a['offset'])
        cur = None
        return {
            'status': 'ok',
            'chapter': n,
            'file': os.path.basename(p),
            'ratio': first['ratio'],
            'bucket': first['bucket'],
            'note': ('' if int(n) == int(key) - 1
                     else '第 %d 章不存在或无锚点，取最近的已配置前置章' % (int(key) - 1)),
        }
    if int(key) <= 1:
        return {'status': 'unconfigured', 'reason': '本章是第 1 章，前面没有章可比'}
    missing = str(int(key) - 1).zfill(len(key))
    return {'status': 'unconfigured',
            'reason': '前一个已配置且存在的章：无（第 %s 章文件%s）' % (
                missing, '缺失' if missing not in files else '未配置锚点')}


# ------------------------------------------------------ 指标2：章纲落实度

ROW_RE = re.compile(r'^\|\s*0*(\d+)\s*\|', re.M)
DETAILS_RE = re.compile(r'<details>(.*?)</details>', re.S)
MUST_RE = re.compile(r'\*\*\s*必须做到的事\s*\*\*')
NEXT_HEAD_RE = re.compile(r'\n\s*\*\*[^*\n]+\*\*')
ITEM_RE = re.compile(r'^\s*(\d+)\s*[.、)]\s*(.+)$', re.M)


def find_plan_block(outline_text, no):
    """按「章号行 → 下一章号行」限定范围找 <details>，防止把 009 的块当成 008 的"""
    rows = [(m.start(), m.group(1)) for m in ROW_RE.finditer(outline_text)]
    for i, (pos, ch) in enumerate(rows):
        if int(ch) != int(no):
            continue
        end = rows[i + 1][0] if i + 1 < len(rows) else len(outline_text)
        d = DETAILS_RE.search(outline_text, pos, end)
        if not d:
            return None, '本章（%s）没有 <details> 章纲块' % no
        block = d.group(1)
        head = block[:240]
        m = re.search(r'0*(\d+)\s*分场', head)
        if m and int(m.group(1)) != int(no):
            return block, '块内标注的章号是 %s，与 %s 不符' % (m.group(1), no)
        return block, None
    return None, '大纲里找不到第 %s 章那一行' % no


def must_do_items(block):
    m = MUST_RE.search(block)
    if not m:
        return None
    seg = block[m.end():]
    nxt = NEXT_HEAD_RE.search(seg)
    if nxt:
        seg = seg[:nxt.start()]
    return [{'n': int(n), 'text': t.strip()} for n, t in ITEM_RE.findall(seg)]


def _ref_without_state(ref, setting_dir):
    """设定库全文去掉 角色状态.md —— 状态表是流水，不是设定

    白名单本来就来自状态表的「身上物品」；如果同一行又当成「设定库里提过所以不算新」，
    时点白名单就永远不可能报出本章新登记的物件（006 的白线就是这么漏的）。
    """
    path = os.path.join(setting_dir, STATE_BASENAME) if setting_dir else ''
    if not path or not os.path.exists(path):
        return ref
    try:
        t = read_text(path)
    except (IOError, OSError, UnicodeDecodeError):
        return ref
    return ref.replace(t, '', 1) if t else ref


def _known_lexicon(setting_dir):
    """设定库 2-6 字子串集合，用作「已知词」词表（分词用）"""
    lex = set()
    if not setting_dir or not os.path.isdir(setting_dir):
        return lex, ''
    buf = []
    for root, _, files in os.walk(setting_dir):
        for f in sorted(files):
            if f.endswith('.md'):
                try:
                    buf.append(read_text(os.path.join(root, f)))
                except (IOError, OSError, UnicodeDecodeError):
                    continue
    ref = '\n'.join(buf)
    for m in re.finditer(r'[\u4e00-\u9fff]+', ref):
        s = m.group(0)
        for n in range(2, 7):
            for i in range(len(s) - n + 1):
                lex.add(s[i:i + n])
    return lex, ref


def _clause_term(clause, lex, body):
    """分句里挑一个可核对项：优先引号字面，其次「正文里真出现过的」最长词组"""
    m = LIT_RE.search(clause)
    if m:
        return m.group(1).strip()
    best = ''
    for m in re.finditer(r'[一-鿿]{2,}', clause):
        s = m.group(0)
        for n in range(min(4, len(s)), 1, -1):
            for i in range(len(s) - n + 1):
                cand = s[i:i + n]
                if (cand in COMMON_WORDS or cand[0] in BAD_START or cand[-1] in BAD_START
                        or cand[0] in COMMON_CHARS):
                    continue
                if cand in body and len(cand) > len(best):
                    best = cand
    if best:
        return best
    spans = [s for s in split_spans(clause, lex)
             if 2 <= len(s) <= 4 and s not in COMMON_WORDS]
    spans.sort(key=len, reverse=True)
    return spans[0] if spans else ''


def _order_check(text, item, lex):
    """「先…再…」的顺序是否成立：返回 (order, 用了哪两个词)"""
    if '先' not in item or not re.search('再|然后', item):
        return 'unknown', None
    head, _, tail = item.partition('先')
    m = re.search('再|然后', tail)
    if not m:
        return 'unknown', None
    a = _clause_term(tail[:m.start()], lex, text)
    b = _clause_term(tail[m.end():], lex, text)
    if not a or not b:
        return 'unknown', None
    ia, ib = text.find(a), text.find(b)
    if ia < 0 or ib < 0:
        return 'unknown', {'先': a, '再': b}
    return ('ok' if ia < ib else 'violated'), {'先': a, '再': b}


def _weak_keywords(item, lex, ref):
    """条目里没有引号字面时，退一步取「设定库里有」的 2-4 字名词当弱检查点"""
    grams = []
    for m in re.finditer(r'[\u4e00-\u9fff]{2,4}', item):
        g = m.group(0)
        if g in lex and ref.count(g) >= 2:
            grams.append(g)
    grams.sort(key=len, reverse=True)
    return grams[:3]


def _current_row(outline_text, no):
    for line in outline_text.split(NL):
        m = re.match(r'^\|\s*0*(\d+)\s*\|', line)
        if m and int(m.group(1)) == int(no):
            return line.strip()
    return ''


def _plan_pointer(outline_text, no):
    """unconfigured 必须交代两件事：为什么没有、照哪一章写"""
    rows = [(m.start(), m.group(1)) for m in ROW_RE.finditer(outline_text)]
    example = None
    for i, (pos, ch) in enumerate(rows):
        end = rows[i + 1][0] if i + 1 < len(rows) else len(outline_text)
        d = DETAILS_RE.search(outline_text, pos, end)
        if d and int(ch) != int(no):
            first_line = outline_text.count(NL, 0, d.start()) + 1
            last_line = outline_text.count(NL, 0, d.end()) + 1
            body = re.sub(NL + '{2,}', NL, d.group(1)).strip()
            example = {'chapter': '%03d' % int(ch), 'lines': '%d-%d' % (first_line, last_line),
                       'excerpt': body[:400]}
            if int(ch) == int(no) + 1:
                break
    out = {
        'why': '第 %s 章在大纲表格里只有一句话，没有 <details> 分场章纲块，'
               '所以没有「必须做到的事」可以逐条核对' % no,
        'current_row': _current_row(outline_text, no),
        'fix': [
            '打开 <项目>/大纲/全书大纲.md',
            '找到表格里第 %s 章那一行（就是上面 current_row 那一行）' % no,
            '在该行表格下方补 <details><summary>%s 分场章纲</summary> … </details>' % no,
            '块内五段按顺序写：**场次** / **必须做到的事** / **本章推进** / **不许做** / **文风锚点**',
            '「必须做到的事」写成编号列表，每条尽量带「…」原话字面，程序才能逐条核对',
        ],
    }
    if example:
        out['example'] = example
    return out


def plan_metric(text, outline_path, no, setting_dir):
    if not outline_path or not os.path.exists(outline_path):
        return {'status': 'no_outline', 'outline': outline_path or '',
                'reason': '找不到大纲文件',
                'fix': ['确认 <项目>/大纲/全书大纲.md 存在', '或用 --outline 指定章纲文件']}
    otext = read_text(outline_path)
    block, warn = find_plan_block(otext, no)
    if block is None:
        out = {'status': 'unconfigured', 'outline': outline_path,
               'chapter_plan': no, 'reason': warn}
        out.update(_plan_pointer(otext, no))
        return out
    if warn:
        out = {'status': 'mismatch', 'outline': outline_path, 'chapter_plan': no, 'reason': warn}
        out.update(_plan_pointer(otext, no))
        return out
    items = must_do_items(block)
    if not items:
        out = {'status': 'unconfigured', 'outline': outline_path, 'chapter_plan': no,
               'reason': '<details> 块里没有「必须做到的事」'}
        out.update(_plan_pointer(otext, no))
        return out

    lex, ref = _known_lexicon(setting_dir)
    out_items = []
    missing = []
    n_hit = n_missing = n_unchecked = 0
    for it in items:
        lits = []
        for lit in LIT_RE.findall(it['text']):
            lit = lit.strip()
            if lit and lit not in [l['literal'] for l in lits]:
                lits.append({'literal': lit, 'weak': len(lit) <= 2})
        if lits:
            for l in lits:
                l['count'] = text.count(l['literal'])
                l['found'] = l['count'] > 0
            absent = [l['literal'] for l in lits if not l['found']]
            order, order_terms = _order_check(text, it['text'], lex)
            if order_terms:
                it['order_terms'] = order_terms
            if absent:
                status = 'missing'
                n_missing += 1
                missing.append({'n': it['n'], 'literals': absent})
            elif order == 'violated':
                status = 'order_violated'
                n_missing += 1
                missing.append({'n': it['n'], 'order': '先...再... 的顺序反了'})
            else:
                status = 'hit'
                n_hit += 1
            note = '否定分句（不许/不要/不得）未机械核对' if re.search(r'不许|不要|不得|禁止', it['text']) else ''
            out_items.append({'n': it['n'], 'text': it['text'], 'status': status,
                              'basis': 'quoted_literals', 'checks': lits,
                              'order': order, 'order_terms': it.get('order_terms'),
                              'note': note})
        else:
            kws = _weak_keywords(it['text'], lex, ref)
            basis = 'setting_nouns'
            if not kws:
                kws = [s for s in split_spans(it['text'], lex)
                       if 2 <= len(s) <= 4 and s not in COMMON_WORDS
                       and s[0] not in SPAN_BAD_EDGE and s[-1] not in SPAN_BAD_EDGE]
                kws.sort(key=len, reverse=True)
                kws = kws[:3]
                basis = 'span_nouns'
            if kws:
                checks = [{'literal': k, 'count': text.count(k), 'found': text.count(k) > 0, 'weak': True} for k in kws]
                bad = [c['literal'] for c in checks if not c['found']]
                status = 'missing_weak' if bad else 'hit_weak'
                if bad:
                    n_missing += 1
                    missing.append({'n': it['n'], 'literals': bad, 'weak': True})
                else:
                    n_hit += 1
                out_items.append({'n': it['n'], 'text': it['text'], 'status': status,
                                  'basis': basis, 'checks': checks, 'order': 'unknown',
                                  'note': '无引号字面，按名词切片核对（弱核对，不是原话比对）'})
            else:
                n_unchecked += 1
                out_items.append({'n': it['n'], 'text': it['text'], 'status': 'unchecked',
                                  'basis': 'none', 'checks': [], 'order': 'unknown',
                                  'note': '既无引号字面、也无设定库名词，无法机械核对'})

    return {
        'status': 'ok',
        'outline': outline_path,
        'chapter_plan': no,
        'items_total': len(items),
        'hit': n_hit,
        'missing': n_missing,
        'unchecked': n_unchecked,
        'missing_list': missing,
        'items': out_items,
    }


# ------------------------------------------------------ 指标3：设定外物件

SURNAMES = set('赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏窦章云苏潘葛范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝安常傅皮卞齐康伍余元卜顾孟平黄穆萧尹')
PLACE_SUFFIX = ('镇', '村', '庄', '滩', '山', '河', '江', '湖', '城', '府', '县', '州', '关',
                '渡', '桥', '巷', '街', '坊', '楼', '阁', '寺', '庙', '岭', '谷', '湾', '塘',
                '坪', '寨', '堡', '沟', '铺', '店', '号', '园', '陵', '桥')
ROLE_SUFFIX = ('掌柜', '老头', '老汉', '婆子', '郎中', '货郎', '伙计', '寡妇', '汉子',
               '妇人', '后生', '娘子', '公子', '先生', '师父', '东家', '小二', '猎户', '夫人')

# 轨道 B：物件。没有书名号、没有姓氏、没有地名/称呼后缀的东西，只能靠「怎么被数」和
# 「怎么被拿着」来抓。两条模式都要求末字落在实物尾字上，防止把「一片天」「三寸」
# 「一件东西」当成物件。
OBJ_MEASURE = '把张条根块片只件双枚杆柄口碗斗袋包卷捆幅支盏摞寸尺截'
RE_OBJ_QUANT = re.compile(r'[一二两三四五六七八九十半几数]([%s])([一-鿿]{2,4})'
                          % OBJ_MEASURE)
RE_OBJ_TAKE_A = re.compile(r'把([一-鿿]{2,4})'
                           r'(?:揣|塞|别|挂|系|收|拿|放|搁|插|藏|掖|递|扔|捡|捏|攥|握|提|抱|扛|拎)')
RE_OBJ_TAKE_B = re.compile(r'([一-鿿]{2,4})'
                           r'(?:揣进|塞进|别在|挂在|收进|摸出|掏出|捏在|攥在|提在|握在'
                           r'|系在|放进|扔进|揣回|挂回|别回)')
RE_OBJ_TAKE_C = re.compile(r'(?:提着|拿着|攥着|捏着|抱着|背着|扛着|拎着|握着|系着|挂着'
                           r'|揣着|别着|收着|藏着|摸出|掏出|取出)([一-鿿]{2,4})')
OBJ_TAIL = set('刀鞋袋包线绳布纸牌碗秤灯衣褂裤帽巾席斗桶罐缸瓶壶盒匣箱篮篓担篙棍棒'
               '石饼盐糖肉柴炭针剪斧锯钉锁钥钱笔墨砚烛草被子板匾链镜铃环簪坠')
# 货币单列：铜板/铜钱这类由 角色状态.md「钱」字段管，不算「设定外物件」，
# 否则每章都会报一堆「真物件但没信息量」的条目
OBJ_MONEY = set(('铜板', '铜钱', '铜元', '银子', '金子', '碎银', '制钱'))
ITEM_FIELD_RE = re.compile(r'\*\*\s*身上物品\s*\*\*[：:]\s*(.+)')
BAD_START = set('的了着过是在有和与就都不没很这那你我他她它们个一二三四五六七八九十百千万上下里中前后左右来去到说看把被给让从对为以而且然但所以如可什么怎自己还再又像要会能得地之其已将每各等则便随某另该此'
                '站往抽带跟赶走摸拿放坐躺睡醒摇攥蹲爬绕咬舔咽嚼抓握插拔劈砍装着穿脱洗擦抹按提抬低伸收揣掏递接吞吐呼喘咳抖晃撞砸扔丢捡扫地边面旁底处间慢紧才刚正更最太多个些点只每各'
                '进出回过到经沿顺拐朝望向骂喊叫笑哭叹'
                '条块根片张只件份阵股双对')
BAD_START_CHAR_ONE = set('一两几数半成百千')
NAME_BAD2 = set('的了着过是在有和与就都不没很这那你我他她它们个来到去说看把被给让从对为以而且然但所以如可什么怎自己还再又像要会能得地之其已每各等则便'
                 '光红黄蓝白黑青紫灰彩粉绿褐')        # 挡「金红」「黄光」这类颜色切片
COMMON_CHARS = set('的了着过是在有和与就都不没很这那你我他她它们个一二三四五六七八九十百千万上下里中前后左右来去到说看把被给让从对为以而且然但所以如果可什么怎自己还再又像要会能得地之其已吧呢啊呀哦嗯将并且或虽每各等是则便却若才刚正更最太多个些点只又再还往抽带跟赶站走摸拿放坐躺睡醒摇捏捏攥蹲爬绕踢咬舔咽嚼抓握插拔劈砍装着穿脱洗擦抹按提抬低伸收揣掏递接递吞吐呼喘咳抖晃撞砸扔丢捡扫地扫次遍声步件条张片块根份场交留许须必')
SPAN_BAD_EDGE = set('许要须必能会可让使合交留')
COMMON_WORDS = set("""
时候 一会 起来 出来 进去 回来 忽然 已经 还是 一样 一下 一些 有点 觉得 知道 可以 没有
一个 这个 那个 自己 他们 我们 你们 什么 怎么 为什么 因为 所以 但是 然后 而且 于是
就是 不是 只是 这样 那样 这里 那里 现在 刚才 一直 一点 慢慢 渐渐 声音 眼睛 脸上 手上
心里 脚上 身上 地上 门口 屋里 墙上 路上 街上 镇上 抬头 低头 回头 转身 站住 停住 坐下
蹲下 走过 走到 看见 想了想 土路 荒草 石头 膝盖 蜡烛 陶碗 镰刀 布鞋 石板 石阶 脚踝
手背 街东 镇口 柜台 篮子 短褂 衣裳 裤脚 露水 草绳 绳头 线头
东边 西边 南边 北边 左边 右边 前边 后边 上边 下边 里头 外头 里头 面前 背后
想起 想着 记起 记得 不记得 看见 看不见 听不见 走近 走远 站起 撑住 扶住 松开 攥住
明天 昨儿 昨日 今日 上回 前日 大前日 昨夜 天亮 天黑 半夜 后半夜 早起 擦黑 阴天
石板路 土坡 废墙 田埂 井边 河边 路口 村口 镇口 集市 药铺 当铺 门脸 算盘 荷叶
卤肉 卤肉摊 摊主 蒲扇 苍蝇 干草 柴刀 木斗 米斗 布包 蓝布 破席 油布 房顶 床板
板床 正屋 院门 铁丝 铁锈 石子 碎石 泥印 脚印 脚趾 指头 指腹 手心 虎口 脸颊 颧骨
眼角 眼珠 眼窝 下巴 嘴唇 嘴角 喉咙 肋骨 胳膊 骨头 褶子 青筋 日头 时辰 一炷香
半炷香 一刻 上边 篓子 担子 草叶 草籽 小腿 脚底 鞋底 鞋帮 柴棍 绳子 荒地 圆圈
街东头 街西头 几样 摆摊 平视 方向 石桥 石阶 灰瓦 土墙 篱笆 窗户 油灯 灯芯 布袋 粗布 麻布 蓑衣 斗笠 挑担 赶猪
妇人 青菜 胖子 伙计 掌柜 老头 后生 郎中 货郎 汉子 娘子 身子 影子 印子 痕印
东西 地方 样子 法子 说法 事儿 力气 味道 颜色 一下子 一会儿 一阵 一片 一半 一句
""".split())


def split_spans(narr, lex):
    """设定库词表贪心分词：切不动的连续字才是候选"""
    spans = []
    for run in re.finditer(r'[\u4e00-\u9fff]+', narr):
        s = run.group(0)
        i, cur = 0, ''
        while i < len(s):
            hit = 0
            for k in range(min(6, len(s) - i), 1, -1):
                if s[i:i + k] in lex:
                    hit = k
                    break
            if hit:
                if cur:
                    spans.append(cur)
                    cur = ''
                i += hit
            elif s[i] in COMMON_CHARS:
                if cur:
                    spans.append(cur)
                    cur = ''
                i += 1
            else:
                cur += s[i]
                i += 1
        if cur:
            spans.append(cur)
    return spans


def _ok_name(term, ref, known_words):
    if not term or len(term) < 2 or len(term) > 5:
        return False
    if term in known_words or term in ref or term[0] in BAD_START or term[-1] in BAD_START:
        return False
    return True


STATE_BASENAME = '角色状态.md'
STATE_GONE_RE = re.compile(r'丢失|丢了|没了|用掉|当掉|当出|不见|已无')
STATE_DELTA_RE = re.compile(r'^chapter_(\d+)\.json$')


def split_state_items(value):
    """「身上物品」字段值 -> 物件名列表

    括号里的补充说明（藏在床底、揣怀里、绕在手指上）整段去掉，那是位置描述，不是物件名。
    「柴刀、外衫、草鞋均已丢失」这类整句带丢失/用掉的，整组不登记 —— 已经不在身上的
    东西还留在白名单里，后文真的丢了东西就查不出来。
    """
    out = []
    seg = re.sub(r'（[^）]*）|\([^)]*\)', '', value or '')
    for group in re.split(r'[；;。]', seg):
        if STATE_GONE_RE.search(group):
            continue
        for part in re.split(r'[、，,]', group):
            part = part.strip().strip('*` ')
            if 2 <= len(part) <= 6:
                out.append(part)
    return out


def load_known_items(setting_dir):
    """作者在 角色状态.md「身上物品」里登记过的物件 -> 已知物件白名单（当前时点）

    只认这一行；没有这个文件就返回空集，不猜。
    """
    items = set()
    path = os.path.join(setting_dir, STATE_BASENAME) if setting_dir else ''
    if not path or not os.path.exists(path):
        return items
    try:
        text = read_text(path)
    except (IOError, OSError, UnicodeDecodeError):
        return items
    for line in text.split(NL):
        m = ITEM_FIELD_RE.search(line)
        if m:
            items.update(split_state_items(m.group(1)))
    return items


def state_subjects(setting_dir):
    """角色状态.md 的二级标题 = 本书角色名单，用来挡跨项目/跨书污染的快照"""
    path = os.path.join(setting_dir, STATE_BASENAME) if setting_dir else ''
    if not path or not os.path.exists(path):
        return set()
    try:
        text = read_text(path)
    except (IOError, OSError, UnicodeDecodeError):
        return set()
    out = set()
    for line in text.split(NL):
        m = re.match(r'^##\s+([^\s（(]+)', line)
        if m:
            out.add(m.group(1).strip())
    return out


def load_state_asof(project, as_of, allowed_subjects=None):
    """按章时点取「身上物品」白名单：只认章号严格小于 as_of 的快照。

    .story/state/chapter_00N.json 的 state_deltas 是「第 N 章结束时」的状态。
    审第 N 章要用的是「第 N 章开篇之前」的状态 = 第 N-1 章结束的状态，所以 N 自己
    的快照不算：006 的快照里已经写了「一截白线」，拿它当白名单等于自己证明自己。
    本书 角色状态.md 里写下过同一条规矩：「审第 N 章时，这张表应该是第 N-1 章结束的状态」。

    快照的 subject 不在本书角色名单里的（例如 003 那张写的是另一本书的「陆远」），
    整条跳过并记录，不静默采信。
    """
    out = {'items': set(), 'files_used': [], 'chapters_seen': [],
           'foreign': {}, 'later': {}, 'fallback': None}
    state_dir = os.path.join(project, '.story', 'state') if project else ''
    if not state_dir or not os.path.isdir(state_dir):
        out['fallback'] = '找不到 .story/state 目录'
        return out

    seen, per_chapter = [], []
    for name in sorted(os.listdir(state_dir)):
        m = STATE_DELTA_RE.match(name)
        if not m:
            continue
        chap = '%03d' % int(m.group(1))
        seen.append(chap)
        try:
            doc = json.loads(read_text(os.path.join(state_dir, name)))
        except (ValueError, IOError, OSError, UnicodeDecodeError):
            out['foreign'].setdefault('(无法解析)', []).append(name)
            continue
        items = set()
        for d in doc.get('state_deltas') or []:
            if d.get('field') != '身上物品':
                continue
            subj = d.get('subject') or ''
            if allowed_subjects and subj and subj not in allowed_subjects:
                out['foreign'].setdefault(subj, []).append(name)
                continue
            items.update(split_state_items(d.get('value') or ''))
        if items:
            per_chapter.append((chap, name, items))
            if int(chap) < int(as_of):
                out['items'].update(items)
                out['files_used'].append(name)

    for chap, _name, items in sorted(per_chapter):
        if int(chap) >= int(as_of):
            for it in sorted(items):          # 排序：dict 插入顺序不能随 set 哈希变
                if it not in out['items'] and it not in out['later']:
                    out['later'][it] = chap
    out['chapters_seen'] = sorted(set(seen))
    if not out['files_used']:
        out['fallback'] = '章号 < %s 的快照里没有可用的「身上物品」' % as_of
    return out


def _is_known_item(term, known_items):
    """白名单命中：同名；或登记时带了量词（「一截白线」「两合米」）也算登记过"""
    if term in known_items:
        return True
    if len(term) < 2:                          # 单字（「刀」）不按后缀归并，容易假命中
        return False
    return any(len(k) > len(term) and len(k) - len(term) <= 2 and k.endswith(term)
               for k in known_items)


def _obj_ok(term, known_items, ref, known_words):
    if not (2 <= len(term) <= 4):
        return False
    if term[-1] not in OBJ_TAIL:        # 末字不是实物 -> 一片天 / 三寸 / 一件东西
        return False
    if any(c in BAD_START for c in term):
        return False
    if _is_known_item(term, known_items) or term in known_words or term in ref:
        return False
    return True


def object_candidates(narr, known_items, ref, known_words):
    """轨道 B：返回 (强候选, 登记过的命中, 只出现一次的)

    强候选 = 出现≥2 次的实物名词；只出现一次的单列，进 info 不进 warn。
    """
    raw = {}

    def _add(term, tag):
        term = term.lstrip('他把被将她我你')
        if not term:
            return
        raw.setdefault(term, set()).add(tag)

    for m in RE_OBJ_QUANT.finditer(narr):
        _add(m.group(2), '量词')
    for rx, tag in ((RE_OBJ_TAKE_A, '持有动作'), (RE_OBJ_TAKE_B, '持有动作'),
                    (RE_OBJ_TAKE_C, '持有动作')):
        for m in rx.finditer(narr):
            _add(m.group(1), tag)

    strong, registered, once = [], [], []
    for term in raw:
        cnt = narr.count(term)
        if _is_known_item(term, known_items):
            registered.append({'term': term, 'count': cnt, 'tags': sorted(raw[term])})
            continue
        if term in OBJ_MONEY:
            continue
        if not _obj_ok(term, known_items, ref, known_words):
            continue
        item = {'term': term, 'kind': '物件·' + ('量词+名词' if '量词' in raw[term] else '持有动作'),
                'count': cnt}
        (strong if cnt >= 2 else once).append(item)
    strong.sort(key=lambda x: (-x['count'], x['term']))
    registered.sort(key=lambda x: x['term'])
    once.sort(key=lambda x: x['term'])
    return strong, registered, once


def setting_metric(path, setting_dir, project=None, state_as_of=None):
    text = read_text(path)
    lines = text.split('\n')
    narr = '\n'.join(l for l in lines if not is_heading(l))
    narr = QUOTED_RE.sub('|', narr)          # 引号内一律不查（对话/引语）
    narr = SINGLE_QUOTED_RE.sub('|', narr)

    lex, ref = _known_lexicon(setting_dir)
    if not ref:
        return {'status': 'no_setting', 'setting_dir': setting_dir,
                'reason': '找不到 设定库 目录，无法判断「设定外」'}
    known_words = COMMON_WORDS | set(PLACE_SUFFIX) | set(ROLE_SUFFIX)
    ref_objs = _ref_without_state(ref, setting_dir)

    # 白名单：默认「此刻」= 角色状态.md 当前状态；--state-as-of NNN = 第 NNN 章开篇前的快照
    known_items = load_known_items(setting_dir)
    state_meta = None
    if state_as_of:
        proj = project or os.path.dirname(os.path.dirname(os.path.abspath(path)))
        state_meta = load_state_asof(proj, state_as_of, state_subjects(setting_dir))
        if state_meta.get('fallback'):
            state_meta['effective'] = 'current'      # 快照不可用时不装懂，退回当前表并说明
        else:
            known_items = state_meta['items']

    strong = []

    for t in TITLE_RE.findall(narr):
        t = t.strip()
        if _ok_name(t, ref, known_words):
            strong.append({'term': t, 'kind': '书名号', 'count': narr.count(t)})

    name_start = SURNAMES | set('小老阿大')

    def _left(s, end, limit=3):
        """从 end 往左取连续实字（碰到虚词/标点即断），最多 limit 个"""
        got = []
        i = end - 1
        while i >= 0 and len(got) < limit:
            ch = s[i]
            if not CJK_RE.match(ch) or ch in BAD_START:
                break
            got.append(ch)
            i -= 1
        return ''.join(reversed(got))

    for i, ch in enumerate(narr):
        if ch not in SURNAMES:
            continue
        if i > 0 and narr[i - 1] in BAD_START_CHAR_ONE:     # 「一张干瘦的脸」的「张」
            continue
        base = narr[i:i + 2]
        if len(base) < 2 or not CJK_RE.match(base[1]):
            continue
        if base[1] in NAME_BAD2:                            # 姓后面紧跟虚词/动词，不是名字
            continue
        if base in ref or base in known_words:
            continue
        cand = base
        ext = narr[i:i + 3]
        if (len(ext) == 3 and CJK_RE.match(ext[2]) and ext not in ref
                and ext[-1] not in BAD_START and narr.count(ext) >= 2):
            cand = ext
        if narr.count(cand) < 2:        # 人名在正文里不会只出现一次；只出现一次多半是普通词切片
            continue
        if _ok_name(cand, ref, known_words):
            strong.append({'term': cand, 'kind': '姓氏+名', 'count': narr.count(cand)})

    for suf in PLACE_SUFFIX:
        for m in re.finditer(re.escape(suf), narr):
            pre = _left(narr, m.start())
            if len(pre) < 2:            # 2 字地名基本都是普通词（石桥/荒滩），不报
                continue
            # 由长到短试：能落到「设定库里已有的短词」（如 当铺）就不报
            if any(pre[-L:] + suf in ref for L in range(len(pre), 0, -1)):
                continue
            cand = pre + suf
            if _ok_name(cand, ref, known_words):
                strong.append({'term': cand, 'kind': '地名后缀', 'count': narr.count(cand)})

    for suf in ROLE_SUFFIX:
        for m in re.finditer(re.escape(suf), narr):
            if m.start() < 1:
                continue
            head = narr[m.start() - 1]
            if head not in name_start:   # 只认「姓/小/老/阿 + 称呼」，挡掉「跟老头」
                continue
            cand = head + suf
            if cand in ref:
                continue
            if _ok_name(cand, ref, known_words):
                strong.append({'term': cand, 'kind': '称呼后缀', 'count': narr.count(cand)})

    # 轨道 B：物件（量词 / 持有动作）。没有后缀的物件只能从这两条路进来。
    obj_strong, obj_registered, obj_once = object_candidates(
        narr, known_items, ref_objs, known_words)
    if state_meta and state_meta.get('later'):
        for x in obj_strong:                       # 本章之后才登记 -> 本章就是首见章
            chaps = []
            if state_meta['later'].get(x['term']):
                chaps.append(state_meta['later'][x['term']])
            for k, c in state_meta['later'].items():   # 「一截白线」这种带量词的登记
                if len(k) > len(x['term']) and len(k) - len(x['term']) <= 2 \
                        and k.endswith(x['term']):
                    chaps.append(c)
            if chaps:
                x['registered_after'] = min(chaps)
    for x in obj_strong:
        item = {'term': x['term'], 'kind': x['kind'], 'count': x['count']}
        if x.get('registered_after'):
            item['registered_after'] = x['registered_after']
        strong.append(item)

    seen, sus = set(), []
    for s in strong:
        if s['term'] in seen:
            continue
        seen.add(s['term'])
        sus.append(s)

    spans = split_spans(narr, lex)
    weak_cnt = {}
    long_spans = {}
    for sp in spans:
        if 2 <= len(sp) <= 5:
            weak_cnt[sp] = weak_cnt.get(sp, 0) + 1
        elif len(sp) > 5:
            long_spans[sp] = long_spans.get(sp, 0) + 1

    weak = []
    for term, cnt in weak_cnt.items():
        if term in seen or cnt < 2 or term in known_words:
            continue
        if any(term != o and term in o and weak_cnt[o] == cnt for o in weak_cnt):
            continue
        weak.append({'term': term, 'count': cnt, 'weak': True})
    for x in obj_once:                  # 只出现一次的物件：给 info，不给 warn
        if x['term'] in seen:
            continue
        seen.add(x['term'])
        weak.append({'term': x['term'], 'count': x['count'], 'weak': True,
                     'kind': x['kind']})
    weak.sort(key=lambda x: (-x['count'], -len(x['term']), x['term']))
    capped = weak[:12]

    issues = []
    for x in sus:
        msg = '疑似设定库外专有名词：%s（%s，%d 次）' % (x['term'], x['kind'], x['count'])
        if x.get('registered_after'):
            msg += '；本章之后（%s 快照）才登记，本章是首见' % x['registered_after']
        iss = {'metric': 'setting_names', 'severity': 'warn', 'code': 'suspect_proper_noun',
               'term': x['term'], 'kind': x['kind'], 'count': x['count'], 'message': msg}
        if x.get('registered_after'):
            iss['registered_after'] = x['registered_after']
        issues.append(iss)
    for x in capped:
        issues.append({'metric': 'setting_names', 'severity': 'info', 'code': 'weak_oov_span',
                       'term': x['term'], 'count': x['count'],
                       'message': '弱信号（可能只是一般词汇）：%s（%d 次）' % (x['term'], x['count'])})

    if state_meta is None:
        basis = 'current'
        state_out = {'basis': basis,
                     'rule': '用 设定库/角色状态.md 当前「身上物品」当白名单（= 最后一章结束的状态）'}
    else:
        fallback = state_meta.get('fallback')
        basis = 'current' if fallback else 'state-as-of:%s' % state_as_of
        state_out = {
            'basis': basis,
            'requested': 'state-as-of:%s' % state_as_of,
            'rule': '只用章号严格小于 %s 的 .story/state/chapter_*.json 的「身上物品」当白名单'
                    '（审第 N 章用第 N-1 章结束的状态；第 N 章自己的快照已含本章新增，不算）'
                    % state_as_of,
            'files_used': state_meta.get('files_used') or [],
            'chapters_seen': state_meta.get('chapters_seen') or [],
            'excluded_foreign': state_meta.get('foreign') or {},
            'registered_after': state_meta.get('later') or {},
            'fallback': fallback,
        }

    return {
        'status': 'ok',
        'setting_dir': setting_dir,
        'known_items_basis': basis,
        'known_items_state': state_out,
        'quote_policy': '引号内（「」『』“”‘’）整体剔除，不参与候选',
        'issues': issues,
        'suspects': sus,
        'suspects_note': '疑似，不是断言；请人工确认是否真为设定库外的新名词',
        'weak': capped,
        'weak_note': '弱信号：设定库词表切不动的残段 / 只出现一次的物件，可能只是一般词汇',
        'weak_total': len(weak),
        'objects': {
            'policy': '量词+2-4字名词 / 持有动作+2-4字名词；末字须为实物尾字；'
                      '白名单 = 角色状态.md「身上物品」里作者登记过的物件',
            'known_items': sorted(known_items),
            'registered_hits': obj_registered,
            'strong': obj_strong,
            'once': obj_once,
        },
        'long_spans': sorted(long_spans.items(), key=lambda kv: -kv[1])[:5],
    }


# ----------------------------------------------------------------- 输出

def collect(path, args):
    chapter_dir = os.path.dirname(os.path.abspath(path))
    project = os.path.dirname(chapter_dir)
    outline = args.outline or os.path.join(project, '大纲', '全书大纲.md')
    if args.outline is None and not os.path.exists(outline):
        cand = []
        d = os.path.join(project, '大纲')
        if os.path.isdir(d):
            cand = [os.path.join(d, f) for f in os.listdir(d) if f.endswith('.md')]
        if cand:
            outline = sorted(cand)[0]
    setting_dir = args.setting_dir or os.path.join(project, '设定库')
    no = args.plan_chapter or chapter_no(path)

    text = read_text(path)
    anchors = args._anchors
    res = {
        'file': os.path.basename(path),
        'path': os.path.abspath(path),
        'chapter': chapter_no(path),
        'chars': cjk_len(text),
        'conflict': conflict_metric(path, chapter_dir, anchors),
        'plan': plan_metric(text, outline, no, setting_dir) if no else
                {'status': 'unconfigured', 'reason': '章号无法解析'},
        'setting_names': setting_metric(path, setting_dir, project, args.state_as_of),
    }

    issues = list(res['setting_names'].get('issues') or [])
    c = res['conflict']
    if c['status'] != 'ok':
        issues.append({'metric': 'conflict', 'severity': 'warn', 'code': 'conflict_' + c['status'],
                       'message': c.get('why') or c.get('hint') or c.get('reason') or ''})
    p = res['plan']
    if p['status'] == 'ok':
        for m in p.get('missing_list') or []:
            issues.append({'metric': 'plan', 'severity': 'warn', 'code': 'must_do_missing',
                           'item': m['n'],
                           'message': '章纲要求未落实：第 %d 条 —— %s'
                                      % (m['n'], m.get('literals') or m.get('order'))})
        if p.get('unchecked'):
            issues.append({'metric': 'plan', 'severity': 'info', 'code': 'must_do_unchecked',
                           'message': '%d 条章纲要求既无引号字面也无设定库名词，无法机械核对'
                                      % p['unchecked']})
    else:
        issues.append({'metric': 'plan', 'severity': 'warn', 'code': 'plan_' + p['status'],
                       'message': p.get('why') or p.get('reason') or ''})
    res['issues'] = issues
    return res


def print_human(r):
    print('=' * 72)
    print('%-22s %s 章   正文 %d 字' % (r['file'], r['chapter'], r['conflict'].get('chars') or r['chars']))

    c = r['conflict']
    print('  主冲突位置')
    if c['status'] != 'ok':
        print('      unconfigured —— 不猜，也不给 0%')
        print('      为什么   %s' % (c.get('why') or c.get('reason') or ''))
        for s in c.get('fix') or []:
            print('      · %s' % s)
    else:
        f = c['first_conflict']
        print('      首冲突   第 %d 段（文件第 %d 行）第 %d 字 / %d 字 = %.1f%%  → %s'
              % (f['para'], f['line'], f['offset'], c['chars'], f['ratio'] * 100, f['bucket']))
        print('      分布     %s' % '  '.join('%s:%d' % (b, c['distribution'][b]) for b in BUCKETS))
        for a in c['anchors']:
            tag = {'exact': 'OK', 'para_only': '段落号命中', 'by_quote': '按原句定位',
                   'relocated': '段落号对不上，按原句重定位'}[a['matched']]
            print('        第%3d段 %5.1f%% %-6s %s%s' % (
                a['para'], a['ratio'] * 100, a['bucket'], (a['quote'] or '')[:28],
                '' if tag == 'OK' else '  [%s]' % tag))
        if c['unplaced']:
            print('      对不上的锚点 %d 条: %s' % (len(c['unplaced']),
                                           ' / '.join(u['quote'][:16] for u in c['unplaced'])))
        p = c['prev']
        if p['status'] == 'ok':
            d = (f['ratio'] - p['ratio']) * 100
            print('      对比     %s 章 %.1f%%(%s) → 本章 %.1f%%  差 %+.1f 个百分点'
                  % (p['chapter'], p['ratio'] * 100, p['bucket'], f['ratio'] * 100, d))
            if p.get('note'):
                print('               %s' % p['note'])
        else:
            print('      对比     unconfigured —— %s' % p.get('reason'))

    p = r['plan']
    print('  章纲落实度')
    if p['status'] != 'ok':
        print('      %s —— 不猜，也不给 0/0' % p['status'])
        print('      为什么   %s' % (p.get('reason') or ''))
        if p.get('why') and p.get('why') != p.get('reason'):
            print('               %s' % p['why'])
        if p.get('current_row'):
            print('      现在这行 | %s' % p['current_row'][:90])
        for s in p.get('fix') or []:
            print('      · %s' % s)
        ex = p.get('example')
        if ex:
            print('      照它写   第 %s 章有块（%s 第 %s 行），摘录：'
                  % (ex['chapter'], os.path.basename(p.get('outline') or ''), ex['lines']))
            for line in ex['excerpt'].split(NL)[:14]:
                print('        | %s' % line)
    else:
        print('      做到 %d / 缺 %d / 无法机械核对 %d   （共 %d 条，章纲第 %s 块）'
              % (p['hit'], p['missing'], p['unchecked'], p['items_total'], p['chapter_plan']))
        for it in p['items']:
            mark = {'hit': 'OK  ', 'hit_weak': 'OK? ', 'missing': 'MISS',
                    'missing_weak': 'MISS', 'order_violated': 'ORDER',
                    'unchecked': '----'}[it['status']]
            detail = '、'.join('%s%s' % (c['literal'], '' if c['found'] else '(缺)') for c in it['checks'])
            ot = it.get('order_terms')
            if ot:
                detail = (detail + '   ' if detail else '') + '先[%s] → 再[%s]：%s' % (
                    ot['先'], ot['再'], it['order'])
            print('        %s %d. %s' % (mark, it['n'], it['text'][:40]))
            if detail:
                print('               %s' % detail[:100])

    s = r['setting_names']
    print('  设定外物件（疑似）')
    if s['status'] != 'ok':
        print('      %s —— %s' % (s['status'], s.get('reason')))
    else:
        print('      [warn] 强候选 %d 条  %s' % (len(s['suspects']), '、'.join(
            '%s/%s/%d次%s' % (x['term'], x['kind'], x['count'],
                              ('[%s才登记]' % x['registered_after'])
                              if x.get('registered_after') else '')
            for x in s['suspects']) or '（无）'))
        print('      [info] 弱信号 %d 条（显示前 %d）  %s' % (
            s['weak_total'], len(s['weak']),
            '、'.join('%s/%d次' % (x['term'], x['count']) for x in s['weak']) or '（无）'))
        ob = s.get('objects') or {}
        reg = ob.get('registered_hits') or []
        print('      物件轨道 量词/持有动作：登记过不报 %d 条%s；强 %d；只出现一次 %d' % (
            len(reg), ('（%s）' % '、'.join(x['term'] for x in reg)) if reg else '',
            len(ob.get('strong') or []), len(ob.get('once') or [])))
        ks = s.get('known_items_state') or {}
        files = ks.get('files_used') or []
        print('      白名单    known_items_basis=%s  登记 %d 条%s' % (
            s.get('known_items_basis'), len(ob.get('known_items') or []),
            ('  取 %s' % '、'.join(f.replace('chapter_', '').replace('.json', '')
                                  for f in files)) if files else ''))
        if ks.get('fallback'):
            print('                快照不可用，已退回当前表：%s' % ks['fallback'])
        foreign = ks.get('excluded_foreign') or {}
        if foreign:
            print('                跳过非本书主语快照：%s' % '、'.join(
                '%s(%s)' % (k, '/'.join(v)) for k, v in sorted(foreign.items())))
        print('      口径     引号内（对话）整体剔除，不参与取词')


def main():
    ap = argparse.ArgumentParser(
        description='结构指标统计 v2：主冲突位置（锚点）/ 章纲落实度 / 设定外物件（疑似）')
    ap.add_argument('paths', nargs='+', help='章节 .md 路径')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    ap.add_argument('--anchors', default=None,
                    help='锚点配置，默认脚本同目录 structure_anchors.json')
    ap.add_argument('--outline', default=None, help='章纲文件，默认 <项目>/大纲/全书大纲.md')
    ap.add_argument('--setting-dir', default=None, help='设定库目录，默认 <项目>/设定库')
    ap.add_argument('--plan-chapter', type=int, default=None,
                    help='用第 N 章的章纲块来核对本章正文（诊断用）')
    ap.add_argument('--state-as-of', dest='state_as_of', default=None, metavar='NNN',
                    help='按章时点取「身上物品」白名单：只用章号严格小于 NNN 的 '
                         '.story/state/chapter_*.json（审第 N 章 = 第 N-1 章结束的状态）。'
                         '不传 = 用 角色状态.md 当前状态')
    args = ap.parse_args()
    if args.state_as_of is not None:
        if not str(args.state_as_of).isdigit():
            ap.error('--state-as-of 要章号，例如 006')
        args.state_as_of = '%03d' % int(args.state_as_of)

    here = os.path.dirname(os.path.abspath(__file__))
    anchors_path = args.anchors or os.path.join(here, 'structure_anchors.json')
    args._anchors = load_anchors(anchors_path)

    results, bad = [], 0
    for p in args.paths:
        if not os.path.exists(p):
            print('跳过(不存在): %s' % p, file=sys.stderr)
            bad += 1
            continue
        results.append(collect(p, args))

    if args.json:
        print(json.dumps({
            'tool': 'structure_stats', 'version': 2,
            'anchors': anchors_path if args._anchors else '(未加载)',
            'chapters': results,
        }, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print_human(r)
        if len(results) > 1:
            print('=' * 72)
            print('汇总：')
            for r in results:
                c = r['conflict']
                fc = ('%.1f%%' % (c['first_conflict']['ratio'] * 100)) if c['status'] == 'ok' else 'unconfigured'
                p = r['plan']
                pl = ('%d/%d 缺%d' % (p['hit'], p['items_total'], p['missing'])) if p['status'] == 'ok' else p['status']
                print('  %-18s %5d字  首冲突@%-12s 章纲 %-14s 疑似%d'
                      % (r['file'], r['chars'], fc, pl, len(r['setting_names'].get('suspects') or [])))
    return 1 if bad and not results else 0


if __name__ == '__main__':
    sys.exit(main())
