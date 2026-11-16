# -*- coding: utf-8 -*-
"""写作上下文：把「这一章该知道的一切」拼成一份 prompt

输出结构（供 /api/write 直接拼进 system）：
    书信息 / 本章章纲 / 前情正文（最近 1-2 章尾部）/ 章节摘要 /
    本章出场角色卡 / 角色状态 / 地理与时限 / 相关承诺与信息差 / 文风
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO
import reviewers as RV
from context_budget import BUDGET, budget_report, clip_items, clip_text, format_report

MAX_PREV_CHARS = 1800      # 前一章取尾部多少字
MAX_PROMPT_CHARS = 14000   # 整体上限，防止把 prompt 撑爆

# 上下文预算总开关：NOVELAPP_NO_BUDGET=1 时跳过所有截断（= 改造前行为，用于 A/B 对比）。
# 只认 '1' / 'true' / 'yes' / 'on'，其余（含未设置）都是「预算开着」。
NO_BUDGET_ENV = 'NOVELAPP_NO_BUDGET'


def _budget_on():
    """每次装配现读环境变量，方便同一进程里 A/B（不要缓存成模块常量）。"""
    v = (os.environ.get(NO_BUDGET_ENV) or '').strip().lower()
    return v not in ('1', 'true', 'yes', 'on')


def _read(p):
    try:
        with open(p, encoding='utf-8-sig') as f:
            return f.read()
    except OSError:
        return ''


def _book_dir(book):
    return os.path.join(CO.projects_root(), book)


def _sections(text):
    """按 ## 切块 -> {标题: 正文}"""
    out = {}
    for m in re.finditer(r'^##\s+(.+?)\s*$', text, re.M):
        start = m.end()
        nxt = re.search(r'^##\s+', text[start:], re.M)
        body = text[start:start + (nxt.start() if nxt else len(text) - start)]
        out[m.group(1).strip()] = body.strip()
    return out


def _book_meta(book):
    """书名 + 题材/基调（项目信息.md + 章节摘要）"""
    meta = {'name': book, 'genre': '', 'note': ''}
    text = _read(os.path.join(_book_dir(book), '项目信息.md'))
    for line in text.split('\n'):
        m = re.match(r'^\s*[-*]?\s*(题材|基调|风格|类型)\s*[:：]\s*(.+)$', line)
        if m:
            if m.group(1) == '题材':
                meta['genre'] = m.group(2).strip()
            else:
                meta['note'] += ('%s：%s；' % (m.group(1), m.group(2).strip()))
    return meta


def _outline_struct(book, ch):
    """读 009 那一行下面紧跟的 <details> 分场章纲块（若有）。"""
    d = os.path.join(_book_dir(book), '大纲')
    if not os.path.isdir(d):
        return ''
    row_re = re.compile(r'^\|\s*%s\s*\|' % ch)
    for f in sorted(f for f in os.listdir(d) if f.endswith('.md')):
        text = _read(os.path.join(d, f))
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if not row_re.match(line):
                continue
            # 从这一行往下找 <details> ... </details>
            for j in range(i + 1, min(i + 80, len(lines))):
                if '<details>' in lines[j]:
                    buf = []
                    for k in range(j + 1, min(j + 120, len(lines))):
                        if '</details>' in lines[k]:
                            raw_block = '\n'.join(buf).strip()
                            raw_block = re.sub(r'<summary>.*?</summary>\s*', '', raw_block,
                                               flags=re.S)
                            raw_block = re.sub(r'^\s*<[^>]+>\s*$', '', raw_block,
                                               flags=re.M)
                            return raw_block.strip()
                        buf.append(lines[k])
                    return '\n'.join(buf).strip()
                if lines[j].startswith('|') and row_re.match(lines[j]):
                    break
    return ''


def _outline(book, ch):
    """本章章纲：优先 大纲/<NNN>*.md，其次 大纲/全书大纲.md 里的对应段落。"""
    d = os.path.join(_book_dir(book), '大纲')
    if not os.path.isdir(d):
        return ''
    files = sorted(f for f in os.listdir(d) if f.endswith('.md'))
    for f in files:
        if f.startswith(ch) or ('第%s章' % ch.lstrip('0')) in f or ('第%s章' % ch) in f:
            return _read(os.path.join(d, f)).strip()
    for f in files:
        text = _read(os.path.join(d, f))
        m = re.search(r'^#{1,4}\s*第\s*%s\s*章[^\n]*\n(.*?)(?=^#{1,4}\s*第\s*\d+\s*章|\Z)'
                      % ch.lstrip('0'), text, re.S | re.M)
        if m:
            return m.group(1).strip()
    # 表格形态：| 004 | 计划写什么 | 置信度 |
    for f in files:
        text = _read(os.path.join(d, f))
        for line in text.split('\n'):
            m = re.match(r'^\|\s*(\d{1,3})\s*\|\s*([^|]+?)\s*\|', line)
            if m and m.group(1).zfill(3) == ch:
                return '第 %s 章：%s' % (ch, m.group(2).strip())
    return ''


def _prev_chapters(book, ch):
    """前 1-2 章：返回 [(文件名, 尾部正文)]，最近的在最后。"""
    d = os.path.join(_book_dir(book), '章节')
    if not os.path.isdir(d):
        return []
    cur = int(ch)
    files = []
    for f in sorted(os.listdir(d)):
        if not f.endswith('.md') or '.bak' in f:
            continue
        m = re.match(r'^(\d{1,3})-', f)
        if m and int(m.group(1)) < cur:
            files.append((int(m.group(1)), f))
    files.sort()
    out = []
    for num, f in files[-2:]:
        text = _read(os.path.join(d, f))
        out.append((f, text.strip()[-MAX_PREV_CHARS:]))
    return out


def _summaries(book, ch):
    """章节摘要里 前面各章 的条目。"""
    text = _read(os.path.join(_book_dir(book), '设定库', '章节摘要.md'))
    cur = int(ch)
    picked = []
    for m in re.finditer(r'^###\s*(\d{1,3})[^\n]*\n(.*?)(?=^###\s|\Z)', text, re.S | re.M):
        if int(m.group(1)) < cur:
            picked.append((m.group(1), m.group(2).strip()))
    return picked[-3:]


def _characters_dir(book):
    """读 设定库/角色卡/ 下所有 .md，拼成一份「合并角色卡」。

    每个文件的第一行是 '# 甲（主角）'，转回 parse_char_cards 能认的
    '## 一、甲（主角）' 形式；否则一人一卡会被当成同一个角色。
    按文件名排序，保证每次装配结果稳定。
    """
    d = os.path.join(_book_dir(book), '设定库', '角色卡')
    if not os.path.isdir(d):
        return ''
    names = sorted(n for n in os.listdir(d) if n.endswith('.md') and not n.startswith('.'))
    if not names:
        return ''
    parts = []
    for i, n in enumerate(names):
        t = _read(os.path.join(d, n))
        if not t:
            continue
        t = t.lstrip()
        # '# 甲（主角）' -> '## 一、甲（主角）'
        if t.startswith('# '):
            t = '## ' + _CN_ORD[i % len(_CN_ORD)] + '、' + t[2:]
        parts.append(t.rstrip())
    return (chr(10) + chr(10)).join(parts)


_CN_ORD = '一二三四五六七八九十'


def _characters(book, probe_text):
    """角色卡：按正文/章纲里出现过的名字挑（复用 reviewers.pick_characters）。

    两种存法都支持：
      · 新：设定库/角色卡/甲.md（一人一张卡，UI 上是可收起的分支）
      · 旧：设定库/角色卡.md（全部角色挤一个文件，已降级为索引）
    目录优先；目录里没东西才读单文件。
    """
    text = _characters_dir(book)
    if not text:
        text = _read(os.path.join(_book_dir(book), '设定库', '角色卡.md'))
    if not text:
        return []
    cards = RV.parse_char_cards(None, text)
    names = RV.pick_characters(probe_text or '', cards)
    if not names:                    # 没匹配到就给前 4 个主要角色
        names = list(cards)[:4]
    return [(n, cards[n].strip()) for n in names]


def _states(book, probe_text):
    text = _read(os.path.join(_book_dir(book), '设定库', '角色状态.md'))
    if not text:
        return []
    sections = RV.parse_state_sections(text)
    names = RV.pick_states(probe_text or '', sections)
    # 主角必须在列表里且排第一（六问第 2 问只看 states[0]）
    # 主角名从原文拿（parse_state_sections 会把括号内容去掉，
    # 所以 sections 的 key 里已经没有「主角」两字）
    m = re.search(r'^##\s*([^（(\n]+)[（(][^）)]*主角[^）)]*[）)]', text, re.M)
    if m:
        mn = m.group(1).strip()
        if mn in sections:
            names = [mn] + [n for n in (names or []) if n != mn]
    if not names:
        names = list(sections)[:4]
    return [(n, sections[n].strip()) for n in names]


def _promises(book, ch):
    """还没兑付的承诺（状态=进行/未兑付），按开启章排。"""
    d = os.path.join(_book_dir(book), '设定库', '承诺')
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if not f.endswith('.md'):
            continue
        text = _read(os.path.join(d, f))
        fm = {}
        m = re.match(r'^---\r?\n([\s\S]*?)\r?\n---', text)
        if m:
            for line in m.group(1).split('\n'):
                if ':' in line:
                    k, v = line.split(':', 1)
                    fm[k.strip()] = v.strip()
        status = fm.get('状态', '')
        if status in ('已完成', '已兑付', '废弃', 'closed', 'done'):
            continue
        out.append({'id': fm.get('编号') or f.replace('.md', ''),
                    'title': fm.get('标题') or f.replace('.md', ''),
                    'due': fm.get('兑付期限', ''), 'status': status,
                    'open_ch': fm.get('开启章', '')})
    return out[:12]


def _infogaps(book):
    """读者还不知道的信息差（写作时不能写漏嘴）。"""
    d = os.path.join(_book_dir(book), '设定库', '信息差')
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d))[:10]:
        if not f.endswith('.md'):
            continue
        text = _read(os.path.join(d, f))
        m = re.match(r'^---\r?\n([\s\S]*?)\r?\n---', text)
        fm = {}
        if m:
            for line in m.group(1).split('\n'):
                if ':' in line:
                    k, v = line.split(':', 1)
                    fm[k.strip()] = v.strip()
        out.append({'id': fm.get('编号') or f.replace('.md', ''),
                    'title': fm.get('标题') or f.replace('.md', '')})
    return out


def _style(book):
    for name in ('文风宪法.md', '文风.md', '写作规范.md'):
        t = _read(os.path.join(_book_dir(book), '设定库', name))
        if t.strip():
            return t.strip()[:2000]
    return ''


def _ledger(book, name, limit=1500):
    return _read(os.path.join(_book_dir(book), '设定库', name)).strip()[:limit]


def _prev_tail_all(book, ch):
    """上一章全文（不截断），用于「接续」块。"""
    d = os.path.join(_book_dir(book), '章节')
    if not os.path.isdir(d):
        return None, ''
    ch_int = int(ch)
    best = None
    for f in sorted(os.listdir(d)):
        if not f.endswith('.md'):
            continue
        m = re.match(r'(\d{1,3})', f)
        if not m:
            continue
        n = int(m.group(1))
        if n < ch_int and n >= 1:
            if best is None or n > best[0]:
                best = (n, f)
    if not best:
        return None, ''
    return best[1], _read(os.path.join(d, best[1])).strip()


def _last_lines(text, n=3):
    """取最后 n 个非空段。"""
    paras = [x.strip() for x in text.split('\n') if x.strip()]
    return paras[-n:] if len(paras) >= n else paras


def _forbid_block(outline_struct):
    """默认四条 + 章纲里自带的「不许做」。"""
    base = [
        '- 不许自行添加章纲/前情里没有的人物',
        '- 不许新增设定物件（新道具/新规则/新地名），要加必须先写进 设定库/ 并登记',
        '- 不许改动已有距离、时间跨度、人物关系',
        '- 不许写「第 N 章」「上一章」这类元叙述',
    ]
    if outline_struct and '不许做' in outline_struct:
        seg = outline_struct.split('不许做', 1)[1]
        for ln in seg.split('\n'):
            s = ln.strip()
            if s.startswith('- '):
                base.append(s)
    return '\n'.join(dict.fromkeys(base))


def _current_volume(book, ch):
    """本章属于第几卷。解析 大纲/全书大纲.md 里 `### 卷一 · 名字（001–060）`。
    解析不到返回 ''。"""
    d = os.path.join(_book_dir(book), '大纲')
    if not os.path.isdir(d):
        return ''
    ch_int = int(ch)
    pat = re.compile(
        r'###\s*卷([一二三四五六七八九十]+)[^（(]*[（(](\d{1,4})\s*[–\-~]\s*(\d{1,4})[）)]')
    for f in sorted(x for x in os.listdir(d) if x.endswith('.md')):
        text = _read(os.path.join(d, f))
        for m in pat.finditer(text):
            lo, hi = int(m.group(2)), int(m.group(3))
            if lo <= ch_int <= hi:
                return '卷' + m.group(1)
    return ''


def _pick_promises(book, ch, outline_struct):
    """本章该推进哪几条承诺。
    优先：章纲里写了「本章推进：P-XXX」；
    否则：自动挑 —— 强度高 + 最久没推进的 1-2 条。
    返回 (chosen, source)，source ∈ {'plan','auto','none'}。
    """
    try:
        import promises as PM
    except Exception:
        return [], 'none'
    ch_int = int(ch)
    cur_vol = _current_volume(book, ch)
    all_p = [p for p in PM.load_all(book) if p.get('状态') == '进行']
    if not all_p:
        return [], 'none'
    # 卷过滤：承诺写了「可推进卷」且不含当前卷 → 排除
    if cur_vol:
        filtered = []
        for p in all_p:
            vols = str(p.get('可推进卷') or '').strip()
            if vols and cur_vol not in [v.strip() for v in re.split(r'[,，、]', vols) if v.strip()]:
                continue
            filtered.append(p)
        all_p = filtered
        if not all_p:
            return [], 'none'

    # 章纲指定（必须是库里的编号）
    if outline_struct:
        ids = re.findall(r'P-\d{3}', outline_struct)
        if ids:
            want = []
            for pid in dict.fromkeys(ids):
                for p in all_p:
                    if p.get('编号') == pid:
                        want.append(p)
                        break
            if want:
                return want, 'plan'

    # 自动挑：高强度的先，其次最久没推进
    def key(p):
        strength_rank = {'高': 0, '中': 1, '低': 2}.get(str(p.get('强度') or ''), 3)
        last = PM.to_int(p.get('最后推进章'), 0)
        gap = ch_int - last
        return (strength_rank, -gap)
    picked = sorted(all_p, key=key)[:2]
    return picked, 'auto'


def _six_questions(book, ch, outline_struct, prevs, sums, states, promises, gaps):
    chosen, chosen_src = _pick_promises(book, ch, outline_struct)
    """开写前六问：能从库算出来的算出来，算不出来的标明「需作者确认」。"""
    lines = []
    ch_int = int(ch)

    # Q1 上一章结尾
    fname, full = _prev_tail_all(book, ch)
    if full:
        tail = _last_lines(full, 3)
        lines.append('### 1. 上一章怎么结束的')
        lines.append('上一章：%s（全文 %d 字）' % (fname, len(full)))
        lines.append('最后三段：')
        for tl in tail:
            lines.append('> ' + tl)
    else:
        lines.append('### 1. 上一章怎么结束的')
        lines.append('（这是第一章，没有上一章）' if ch_int <= 1 else '（未找到上一章正文，需作者确认）')

    # Q2 主角状态
    lines.append('')
    lines.append('### 2. 主角现在什么状态')
    main_state = None
    for n, s in (states or []):
        if '主角' in n and '配角' not in n:
            main_state = (n, s)
            break
    if not main_state and states:
        main_state = states[0]
    if main_state:
        lines.append('按《设定库/角色状态.md》：')
        for ln in main_state[1].split('\n'):
            if ln.strip():
                lines.append('- ' + ln.strip().lstrip('- '))
    else:
        lines.append('（角色状态表里没有主角条目，需先补）')

    # Q3 承诺
    lines.append('')
    lines.append('### 3. 本章推进哪些承诺')
    if chosen:
        tag = '章纲指定' if chosen_src == 'plan' else '系统建议（章纲未指定，按强度+最久未推进挑）'
        lines.append('**%s：**' % tag)
        for p in chosen:
            lines.append('- **%s %s**（强度：%s，最后推进：第 %s 章）'
                         % (p.get('编号'), p.get('标题'), p.get('强度') or '中',
                            p.get('最后推进章') or '?'))
            body = (p.get('_body') or '').strip().split('\n')
            plan_line = ''
            for i2, ln in enumerate(body):
                if '兑付计划' in ln and i2 + 1 < len(body):
                    plan_line = body[i2 + 1].strip()
                    break
            if plan_line:
                lines.append('  兑付方向：' + plan_line)
        lines.append('')
        lines.append('本章必须让读者往前走一步，不要求一次兑现。')
    else:
        lines.append('（承诺表为空）')
    if promises:
        others = [p for p in promises if p.get('id') not in {c.get('编号') for c in chosen}]
        if others:
            lines.append('')
            lines.append('其余进行中的承诺（本章不必动，但别写反）：' )
            lines.append('、'.join('%s %s' % (p['id'], p['title']) for p in others))
    lines.append('**新埋的必须写进 设定库/承诺/ 并登记编号，不许只在正文里提**')

    # Q4 节奏位置
    lines.append('')
    lines.append('### 4. 本章在节奏里的位置')
    has_struct = bool(outline_struct)
    lines.append('（由章纲判断，若无明确标注请按「推进」处理，不要写成高潮）'
                 if has_struct else '（章纲未分场，需作者确认：这是铺垫 / 上升 / 高潮 / 过渡）')

    # Q5 前文核对
    lines.append('')
    lines.append('### 5. 涉及的人/地/规则，前文对得上吗')
    if sums:
        lines.append('已注入最近 %d 章的摘要，写之前先对一遍：' % len(sums))
        lines.append('- 人物在哪、说什么腔调，以角色卡和状态表为准')
        lines.append('- 地点与距离，以世界地图为准（不一致时改正文，不改地图）')
        lines.append('- 规则（年岁/境界/寿元），以力量体系为准，不许自创')
    else:
        lines.append('（没有章节摘要，无法核对前文，建议先补 设定库/章节摘要.md）')

    # Q6 重复用法
    lines.append('')
    lines.append('### 6. 本章要用的说法/动作，前文用过几次')
    lines.append('**写之前自查三条：**')
    lines.append('- 同一个动作（掂了掂/看了看）在全章不超过 3 次；超了不是换词，是问这个动作该不该有')
    lines.append('- 口头禅可以重复，但要符合人物；不是口头禅的重复一律改')
    lines.append('- 一个场景里同一类动作（摸/看/站起）超过 3 次，换切入角度')

    return '\n'.join(lines)


# ── 预算落点：每段都「先按旧格式渲染，再按预算截断」────────────────────
#    _fit_* 在预算关闭时返回旧渲染结果本身，所以 NOVELAPP_NO_BUDGET=1 的
#    system 与改造前逐字节相同（这是硬指标，改这几个函数要重新做 diff）。


def _render_items(items, render, sep):
    return sep.join(render(x) for x in items)


def _cap_per_item(items, budget_key, on):
    """单条截断：Laper 的「12 人 × 每人 600 字」是每卡上限，不是整段总量。

    2026-11-08：初版把 cast_chars 当整段总量（600），大书上每张卡只剩约 50 字，
    角色卡被切得只剩名字。现在先按 BUDGET['<key>_card_chars'] 单条截，再走整段。
    没有配置 *_card_chars 的 key 原样返回。
    """
    if not on:
        return items
    cap = BUDGET.get(budget_key + '_card_chars')
    if not cap:
        return items
    out = []
    for it in items:
        if isinstance(it, (list, tuple)) and len(it) >= 2:
            out.append((it[0], clip_text(str(it[1]), cap)) + tuple(it[2:]))
        else:
            out.append(it)
    return out


def _fit_items(items, budget_key, on, render, sep='\n'):
    """结构化账本（角色卡/角色状态/承诺/信息差）：条数上限 + 字数上限。

    返回 (raw, body)：raw 是改造前的渲染（不截断，用来对比和记账），
    body 是本次实际注入的文本。on=False 时两者相同 = 改造前行为。
    """
    raw = _render_items(items, render, sep)
    if not on:
        return raw, raw
    items = _cap_per_item(items, budget_key, on)      # 先按单条上限裁（如每卡 600）
    body = clip_items(items, BUDGET[budget_key + '_items'], render, sep=sep)
    return raw, clip_text(body, BUDGET[budget_key + '_chars'])


def _fit_blob(text, budget_key, on):
    """整篇 markdown 账本（力量体系/时间线/地图）：只按字数截断。

    条数配额（realm_items 等）对整篇文件不生效——按「## 小节」切会把表格和小节
    的从属关系切碎，反而制造自洽问题，所以整篇只走 clip_text，条数记为 1。
    """
    if not on:
        return text, text
    return text, clip_text(text, BUDGET[budget_key + '_chars'])


def build_context(book, chapter, extra_hint=''):
    """返回 {'system': str, 'chars': int, 'sections': {...}, 'probe': str}

    装配顺序与改造前完全一致（六问 → 书信息 → 章纲 → 前情摘要 → 上一章全文 →
    角色卡 → 角色状态 → 力量体系 → 时间线 → 承诺 → 信息差 → 不许做 → 文风），
    每一段在注入前过一遍 context_budget 的输出契约：**只截断，不删段**。

    NOVELAPP_NO_BUDGET=1 → 跳过全部截断，返回的 system 与改造前逐字节相同。
    预算开着时返回值多一个 'budget' 键（每段实际字数/条数 vs 上限，供调试和 UI）；
    关掉时没有这个键，所以关掉时整个返回 dict 也和改造前一样。
    """
    ch = str(chapter).zfill(3)
    on = _budget_on()
    used = {}

    def record(key, raw, body, items=None):
        """只记账，不改内容。raw != body 说明这一段被截断了（记下原字数）。"""
        if not on:
            return
        rec = {'chars': len(body), 'items': items}
        if len(body) != len(raw):
            rec['raw_chars'] = len(raw)
        used[key] = rec

    meta = _book_meta(book)
    outline_struct = _outline_struct(book, ch)
    outline = outline_struct or _outline(book, ch)
    prevs = _prev_chapters(book, ch)
    sums = _summaries(book, ch)
    probe = '\n'.join([outline] + [p[1] for p in prevs] + [extra_hint])
    chars = _characters(book, probe)
    states = _states(book, probe)
    promises = _promises(book, ch)
    gaps = _infogaps(book)
    style = _style(book)
    power = _ledger(book, '力量体系.md', 1200)
    timeline = _ledger(book, '时间线.md', 900)

    parts = []
    # ── 开写前六问（放最前，先对齐状态，再看任务）──
    q6 = _six_questions(book, ch, outline_struct, prevs, sums, states, promises, gaps)
    if q6:
        parts.append('## 开写前必答（这六条已替你查好，直接照着写）\n' + q6)
        record('sixq', q6, q6)
    head = '# 你在写《%s》第 %s 章' % (book, ch.lstrip('0') or ch)
    if meta['genre']:
        head += '\n题材：%s' % meta['genre']
    if meta['note']:
        head += '\n' + meta['note'].rstrip('；')
    parts.append(head)

    if outline:
        if outline_struct:
            parts.append('## 本章任务（分场，必须照着写）\n' + outline_struct)
            record('outline', outline_struct, outline_struct)
        else:
            parts.append('## 本章章纲（必须落到正文里）\n' + outline)
            record('outline', outline, outline)
    if sums:
        body = '\n'.join('第 %s 章：%s' % (n, t) for n, t in sums)
        parts.append('## 前情摘要\n' + body)
        record('summaries', body, body, len(sums))
    # 上一章全文（接续用），把 1800 字尾部升级为全文，超长才截
    pv_name, pv_full = _prev_tail_all(book, ch)
    if pv_full:
        pv_body = pv_full
        note = ''
        if len(pv_body) > 6000:
            pv_body = pv_body[:6000] + '\n\n（上一章过长，已截断到前 6000 字）'
            note = '（截断）'
        raw_prev = pv_body
        if on:
            # before_chars=3000 生效；BUDGET['before_lines']=12 是 Laper 契约原值，
            # 但这一段是「上一章全文，用来接住语感」，真按 12 行切只剩几百字，
            # 与这一段存在的目的冲突，所以默认只走字数上限。
            pv_body = clip_text(pv_body, BUDGET['before_chars'])
            if pv_body != raw_prev:
                note = '·已按预算截断'
        record('before', raw_prev, pv_body)
        parts.append('## 上一章全文（%s%s，用来接住语感、场景与人物状态）\n%s'
                     % (pv_name, note, pv_body))
    if chars:
        raw, body = _fit_items(chars, 'cast', on,
                               lambda it: '%s\n%s' % (it[0], it[1]), sep='\n\n')
        parts.append('## 本章相关角色\n' + body)
        record('cast', raw, body, len(chars))
    if states:
        raw, body = _fit_items(states, 'state', on,
                               lambda it: '%s\n%s' % (it[0], it[1]), sep='\n\n')
        parts.append('## 角色状态（本章之前，写的时候别写反）\n' + body)
        record('state', raw, body, len(states))
    if power:
        raw, body = _fit_blob(power, 'realm', on)
        parts.append('## 力量体系（不许越级，不许自创规则）\n' + body)
        record('realm', raw, body)
    if timeline:
        raw, body = _fit_blob(timeline, 'timeline', on)
        parts.append('## 时间线（续写要接得上）\n' + body)
        record('timeline', raw, body)
    if promises:
        raw, body = _fit_items(promises, 'promise', on,
                               lambda p: '- %s %s（期限：%s）'
                               % (p['id'], p['title'], p['due'] or '待定'), sep='\n')
        parts.append('## 待推进/待兑付的承诺（本章能推进就推进，别凭空发明新伏笔）\n' + body)
        record('promise', raw, body, len(promises))
    if gaps:
        raw, body = _fit_items(gaps, 'infogap', on,
                               lambda g: '- %s %s' % (g['id'], g['title']), sep='\n')
        parts.append('## 信息差（这些是读者还不知道的事，别在正文里说破）\n' + body)
        record('infogap', raw, body, len(gaps))
    # 铁律：任何一章都适用的「不许做」
    forbid = _forbid_block(outline_struct)
    if forbid:
        parts.append('## 不许做\n' + forbid)
        record('no_do', forbid, forbid)
    if style:
        parts.append('## 文风约束\n' + style)
        record('style', style, style)

    text = '\n\n'.join(parts)
    if len(text) > MAX_PROMPT_CHARS:
        text = text[:MAX_PROMPT_CHARS] + '\n\n（上下文过长，已截断）'
    out = {'system': text, 'chars': len(text), 'sections': {
        'outline': bool(outline), 'outline_struct': bool(outline_struct),
                'prev': len(prevs), 'summaries': len(sums),
        'characters': [n for n, _ in chars], 'states': [n for n, _ in states],
        'promises': len(promises), 'infogaps': len(gaps), 'style': bool(style),
        'power': bool(power), 'timeline': bool(timeline)},
        'probe': probe[:400]}
    if on:
        rep = budget_report(used)
        rep['prompt_chars'] = len(text)
        rep['prompt_budget'] = MAX_PROMPT_CHARS
        out['budget'] = rep
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--book', required=True)
    ap.add_argument('--chapter', required=True)
    ap.add_argument('--full', action='store_true')
    a = ap.parse_args()
    ctx = build_context(a.book, a.chapter)
    print('上下文 %d 字（≈%d tokens）' % (ctx['chars'], int(ctx['chars'] / 1.6)))
    print('命中：', json.dumps(ctx['sections'], ensure_ascii=False))
    rep = ctx.get('budget')
    if rep:
        for line in format_report(rep):
            print(line)
    else:
        print('（%s=1：未套预算，输出与改造前一致）' % NO_BUDGET_ENV)
    if a.full:
        print('-' * 60)
        print(ctx['system'])


if __name__ == '__main__':
    main()
