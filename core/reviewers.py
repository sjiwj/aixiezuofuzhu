# -*- coding: utf-8 -*-
"""审稿团 · 三家锐评（对齐 YG 的 v3 参考实现）

设计原则（YG 原话：「如果加上'请从文风、结构、人物三个维度分析'，就会变成让模型套模板」）：
  1. 所有审稿人用同一句提示词，没有 focus、没有分维度切片
  2. 章号 <=3 用「黄金三章」标准，>3 用「第 N 章追读」标准（从文件名识别，或 --ch）
  3. --chars 角色卡：自动识别本章出场人物，注入其设定 + 4 条行为核对项
  4. --map 地图：传了给「相对位置表」；没传明确告知没有地图，禁止凭空判断地理
  5. 保留两条自己的优势：走网关统一计费（带 token 记账）、vote 合并（同时保留原始意见）

用法:
    python core/reviewers.py <本章md> [--chars 角色卡.md] [--map 地图.md] [--ch N]
                            [--prev 上一章.md] [--mode vote|merge|union] [--json [路径]]
"""
import concurrent.futures as futures
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO
import yamlite

REVIEWERS_PATH = CO.REVIEWERS_PATH
GATE_PATH = os.path.join(CO.ROOT, 'config', 'gate.yaml')
MIN_MAX_TOKENS = 3000
RETRY_MAX_TOKENS = 12000
_CFG = {'sig': None, 'data': None, 'error': None}
_GATE = {'sig': None, 'data': None, 'error': None}
BT = chr(96)   # 反引号，避免源码里出现裸字符

GOLDEN3_PROMPT = (
    '你是一个看了十几年网文的老读者，也是平台编辑。'
    '下面是这部书的开头几章。以「黄金三章」的标准锐评：'
    '这几章能不能留住人？哪里会划走？哪里真的抓人？直说，别客气。'
)

NORMAL_PROMPT = (
    '你是一个看了十几年网文的老读者，也是平台编辑。'
    '下面是第 {ch} 章。以连载追读的标准锐评：'
    '这一章读者会不会划走？哪里卡住？哪里抓人？直说，别客气。'
)

VERDICT_TAIL = (
    '\n\n最后单独一行给出结论，只写这四个字里的选择：'
    '「结论：追读」或「结论：弃读」。不要解释这一行。'
)

CHARS_PROMPT = (
    '\n\n【本章出场人物 · 行为逻辑硬约束】\n'
    '以下是这些人物在设定里的样子。请专门核对本章正文：\n'
    '1. 说话方式是否符合其语言风格（口头禅、句长、比喻来源）\n'
    '2. 行为是否符合其行为逻辑（遇冲突怎么反应、危机第一反应）\n'
    '3. 有没有做了"不许做的事"\n'
    '4. 有没有超出该阶段该知道/该做到的事\n'
    '发现问题请直接指出原文哪一句，并说明与设定的冲突。\n\n'
)

STATE_PROMPT = (
    '\n\n【角色移动轨迹核对】\n'
    '下面给出这些角色在本章之前的已知状态（位置 / 怎么到的 / 物品 / 身体 / 钱）。请核对：\n'
    '1. 这个角色上一章在哪？这一章开头在哪？中间有没有交代怎么过去的？\n'
    '2. 他说的「怎么去的」和地图的行程时间对得上吗？'
    '（比如：他说步行去的，但两地相隔三百里 → 不可能）\n'
    '3. 身上物品对不对？（上一章有柴刀，这章没用过也没说丢了 → 可能漏了；'
    '反过来，表里记「已丢失」的东西如果正文又在用 → 直接判矛盾）\n'
    '4. 身体状况对不对？（上一章受伤，这章生龙活虎 → 需要交代恢复）\n'
    '4.1 钱：状态表记有金额（比如「四十文」），正文若写「没钱」「没一文钱」「身无分文」'
    '→ 这是**矛盾**，直接指出，不要当成「迟来的补充」或「省略」。\n'
    '4.2 正文如果补交代了上一章的疏漏（比如补写清点了铜板），要说明它补上了什么，'
    '但不要因此忽略与状态表相反的说法。\n'
    '没交代但不矛盾的，标「未说明，建议补一句」；如果状态表本身和正文对不上，'
    '要指出是「状态表需要更新」，不要当成正文错误。\n'
    '注意：如果表里「最后更新」写的正是本章，说明这张表已经是**本章之后**的状态，'
    '此时应主要用正文判断，并提示「状态表可能提前提交，建议回滚到上一章结束状态」。\n\n'
)

NO_MAP_NOTICE = '【注意：本次未提供世界地图，无法核对距离与方向，请勿凭空判断地理。】\n\n'

MAP_PROMPT = (
    '【世界地图（权威）】\n'
    '下面是本书的空间事实表，含「相对位置表」与「行程时间矩阵」。审核时请核对：\n'
    '1. 正文里的距离、方向是否与此表一致\n'
    '2. 行程是否走得通（按基准速度：步行空手四十里/日、挑担三十里/日、快跑六十里/半日、夜行二十里）\n'
    '3. 有没有地图上不存在的地点被写了距离\n'
    '4. 正文说的行进时间，和「本书记录在案的行程」表对不对得上'
    '（表里写「挑担一日」，正文写「挑着担半天就到了」就是矛盾）\n'
    '5. 先判断角色当时的赶路状态（空手 / 挑担 / 受伤 / 赶时间 / 闲逛），'
    '再用这个状态的速度核对正文耗时可不可能。'
    '同样二十里，空手半日、挑担一日、带伤两日——状态不同结论不同。\n'
    '\n【超自然位移的处理规则（必须遵守）】\n'
    '如果正文出现「飞、御剑、瞬移、传送、被带走」这类超自然位移：\n'
    '  1. 不要用步行/骑马的速度去套\n'
    '  2. 先查「交通方式与速度」表里有没有这项能力：\n'
    '     - 已登记 -> 按登记的速度核对\n'
    '     - 未登记 -> 这一项标 inconclusive，写「正文出现了地图未登记的移动方式，需客户确认」，'
    '不要报成错误\n'
    '  3. 绝不自行判断「这个速度不可能」——修仙世界可以飞\n'
    '\n核对结论请放在正文最后，格式：\n'
    '「地理核对：一致 / 不一致（列出哪条）/ 无法判断（说明缺什么）」\n\n'
)

GROUP_TITLES = ('配角', '角色', '群像', '人物', '主角')


def load_config(force=False):
    try:
        st = os.stat(REVIEWERS_PATH)
        sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        sig = ('missing',)
    if not force and _CFG['data'] is not None and sig == _CFG['sig']:
        return _CFG['data']
    try:
        data = yamlite.load_file(REVIEWERS_PATH)
        if not isinstance(data, dict):
            raise ValueError('顶层不是映射')
    except Exception as e:
        _CFG.update({'sig': sig, 'error': '%s: %s' % (type(e).__name__, e)})
        return _CFG['data'] or {'mode': 'vote', 'reviewers': [], 'gate': []}
    _CFG.update({'sig': sig, 'data': data, 'error': None})
    return data


def reviewers_of(cfg=None):
    data = cfg or load_config()
    return [r for r in (data.get('reviewers') or []) if isinstance(r, dict) and r.get('id')]


def load_gate_data(force=False):
    try:
        st = os.stat(GATE_PATH)
        sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if not force and _GATE['data'] is not None and sig == _GATE['sig']:
        return _GATE['data']
    try:
        data = yamlite.load_file(GATE_PATH)
        if not isinstance(data, dict):
            raise ValueError('顶层不是映射')
    except Exception as e:
        _GATE.update({'sig': sig, 'error': '%s: %s' % (type(e).__name__, e)})
        return _GATE['data'] or {}
    _GATE.update({'sig': sig, 'data': data, 'error': None})
    return data


def parse_char_cards(path, text=None):
    """把角色卡切成 {人物名: 完整段落}。只认 ## 一、甲 和 ### （一）乙 两种标题。"""
    if text is None:
        with open(path, encoding='utf-8-sig') as f:
            text = f.read()
    lines = text.split('\n')
    marks = []
    for idx, ln in enumerate(lines):
        if not ln.startswith('#'):
            continue
        hashes = len(ln) - len(ln.lstrip('#'))
        if hashes not in (2, 3):
            continue
        rest = ln[hashes:].strip()
        if not rest:
            continue
        if rest[0].isdigit():
            continue
        nm = rest
        for sep in ('、', ')', '）'):
            pos = nm.find(sep)
            if 0 <= pos <= 3:
                nm = nm[pos + 1:].strip()
                break
        if nm.startswith('（') or nm.startswith('('):
            nm = nm[1:].strip()
        for a, b in (('（', '）'), ('(', ')')):
            while a in nm and b in nm:
                i1 = nm.find(a)
                i2 = nm.find(b, i1)
                if i1 < 0 or i2 < 0:
                    break
                nm = (nm[:i1] + nm[i2 + 1:]).strip()
        if not nm or len(nm) > 8:
            continue
        if any(g in nm for g in GROUP_TITLES):
            continue
        marks.append((idx, nm))

    cards = {}
    for i, (ln_idx, nm) in enumerate(marks):
        end_idx = marks[i + 1][0] if i + 1 < len(marks) else len(lines)
        seg = '\n'.join(lines[ln_idx:end_idx]).strip()
        if len(seg) > 100:
            cards[nm] = seg
    return cards


DIM_FILES = (
    ('timeline', '时间线.md', '【时间维核对】本章发生在第几天、跨了多久、地点变化走不走得通'),
    ('power', '力量体系.md', '【能力维核对】会不会这个能力、什么时候会的、升级速度、战力与金手指边界'),
    ('foreshadow', '伏笔.md', '【伏笔维核对】新埋的要登记、旧的要销号、埋太久没收的提醒'),
)


def settings_dir(chapter_rel, chars_path=None, map_path=None):
    """设定库目录：优先角色卡/地图同目录，其次 <章节>/../设定库。"""
    for base in (chars_path, map_path):
        if base:
            return os.path.dirname(os.path.abspath(base))
    return os.path.abspath(os.path.join(os.path.dirname(chapter_rel), '..', '设定库'))


def load_ledgers(chapter_rel, chars_path=None, map_path=None):
    """读 时间线/力量体系/伏笔 三个账本（文件自带『审稿团核对项』，直接注入，避免两处漂移）。"""
    base = settings_dir(chapter_rel, chars_path, map_path)
    out = {}
    for key, fname, _hint in DIM_FILES:
        p = os.path.join(base, fname)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding='utf-8-sig') as f:
                out[key] = {'path': p, 'text': f.read().strip()}
        except OSError:
            continue
    return out


def locate_state_file(chapter_rel, chars_path=None, map_path=None):
    """角色状态表：优先跟角色卡/地图同目录，其次 <章节>/../设定库/。"""
    cands = []
    for base in (chars_path, map_path):
        if base:
            cands.append(os.path.join(os.path.dirname(base), '角色状态.md'))
    cands.append(os.path.join(os.path.dirname(chapter_rel), '..', '设定库', '角色状态.md'))
    for c in cands:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return None


def parse_state_sections(text):
    """把角色状态表切成 {角色名: 段落}，跳过「更新规则」「审稿团怎么用」这类说明节。"""
    out, cur, buf = {}, None, []
    for line in (text or '').split('\n'):
        if line.startswith('## '):
            if cur:
                out[cur] = '\n'.join(buf).strip()
            title = line[3:].strip()
            for a, b in (('（', '）'), ('(', ')')):
                while a in title and b in title:
                    i1, i2 = title.find(a), title.find(b, title.find(a))
                    if i1 < 0 or i2 < 0:
                        break
                    title = (title[:i1] + title[i2 + 1:]).strip()
            cur, buf = title, [line]
        elif cur:
            buf.append(line)
    if cur:
        out[cur] = '\n'.join(buf).strip()
    for meta in ('更新规则', '审稿团怎么用', '规则'):
        out.pop(meta, None)
    return out


def pick_states(chapter_text, sections):
    """只注入本章提到过的角色（按出现次数）。"""
    found = [(chapter_text.count(nm), nm) for nm in sections if chapter_text.count(nm) > 0]
    found.sort(reverse=True)
    return [nm for _, nm in found]


def pick_characters(body, cards):
    found = []
    for nm in cards:
        c = body.count(nm)
        if c > 0:
            found.append((c, nm))
    found.sort(reverse=True)
    return [nm for _, nm in found]


def chapter_number(path, override=None):
    if override not in (None, ''):
        try:
            return int(override), str(override)
        except (TypeError, ValueError):
            return 99, str(override)
    name = os.path.basename(path).replace('.md', '')
    m = re.search(r'(\d+)', name)
    if m:
        return int(m.group(1)), m.group(1)
    m = re.search(r'第([零一二三四五六七八九十百]+)章', name)
    if m:
        cn = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
              '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        return cn.get(m.group(1), 99), m.group(1)
    return 99, '?'


def build_prompt(ch_no, ch_label, chapter_text, chapter_rel, prev_text=None,
                 chars_text=None, map_text=None, state_text=None, ledgers=None,
                 persona=None, reviewer_name=None):
    ch_int = ch_no if isinstance(ch_no, int) else 99
    sys_prompt = GOLDEN3_PROMPT if ch_int <= 3 else NORMAL_PROMPT.format(ch=ch_label)
    # 人设：只加「你是谁」，不加「你只看哪个维度」
    # （YG 设计：分维度会让模型套模板输出套话）
    if persona:
        who = reviewer_name or '审稿人'
        sys_prompt = ('你是%s。%s' % (who, persona)) + chr(10) + chr(10) + sys_prompt

    # 审稿历史：让审稿团记得这本书的顽疾（Persistent Runtime 思路）
    try:
        import review_history as RH
        parts = chapter_rel.replace('\\', '/').split('/')
        book_name = parts[-3] if len(parts) >= 3 else None
        if book_name:
            hist = RH.build_context(book_name, ch_label)
            if hist:
                sys_prompt = sys_prompt + chr(10) + chr(10) + hist
    except Exception:
        pass  # 历史读不到不影响审稿

    used_chars, char_block = [], ''
    if chars_text:
        cards = parse_char_cards(None, chars_text)
        used_chars = pick_characters(chapter_text, cards)
        if used_chars:
            char_block = CHARS_PROMPT + '\n\n'.join(cards[n] for n in used_chars) + '\n'
            sys_prompt += CHARS_PROMPT

    used_states, state_block = [], ''
    if state_text:
        sections = parse_state_sections(state_text)
        used_states = pick_states(chapter_text, sections)
        if used_states:
            state_block = ('\n\n【角色状态（本章之前）】\n'
                           + '\n\n'.join(sections[n] for n in used_states) + '\n')
            sys_prompt += STATE_PROMPT

    dim_blocks = []
    for key, _fname, hint in DIM_FILES:
        rec = (ledgers or {}).get(key)
        if not rec or not rec.get('text'):
            continue
        dim_blocks.append('%s\n【%s】\n%s\n' % (hint, _fname.replace('.md', ''), rec['text']))
        sys_prompt += ('\n\n' + hint + '\n请按下面这个账本里写的「审稿团核对项」逐条核对本章：\n')

    has_map = bool(map_text)
    if has_map:
        # 取「一 相对位置表 + 二 交通方式与速度 + 三 本书已记录的行程」（到 ## 四 之前）
        parts = []
        for pat in (r'##\s*一、[^\n]*\n(.*?)(?=\n##\s*二、|\Z)',
                    r'##\s*二、[^\n]*\n(.*?)(?=\n##\s*三、|\Z)',
                    r'##\s*三、[^\n]*\n(.*?)(?=\n##\s*四、|\Z)'):
            m = re.search(pat, map_text, re.S)
            if m:
                parts.append(m.group(1).strip())
        section = '\n\n---\n\n'.join(parts) if parts else map_text[:3000]
        map_ctx = MAP_PROMPT + section + '\n\n'
    else:
        map_ctx = NO_MAP_NOTICE

    ctx = prev_text + '\n\n' if prev_text else ''
    dim_body = ('\n\n' + '\n\n'.join(dim_blocks)) if dim_blocks else ''
    body = '%s%s%s%s%s【本章全文：%s】\n%s' % (map_ctx, ctx, char_block, state_block, dim_body,
                                               os.path.basename(chapter_rel), chapter_text)
    return sys_prompt + VERDICT_TAIL, body, used_chars, has_map, used_states


def _merge_billing(a, b):
    """两次调用的 token/费用累加（重试不重复计费口径）。"""
    b1 = (a or {}).get('_billing') or {}
    b2 = (b or {}).get('_billing') or {}
    merged = {
        'total_tokens': int(b1.get('total_tokens') or 0) + int(b2.get('total_tokens') or 0),
        'prompt_tokens': int(b1.get('prompt_tokens') or 0) + int(b2.get('prompt_tokens') or 0),
        'completion_tokens': int(b1.get('completion_tokens') or 0) + int(b2.get('completion_tokens') or 0),
        'total_cny': float(b1.get('total_cny') or 0) + float(b2.get('total_cny') or 0),
        'model': b2.get('model') or b1.get('model'),
        'upstream_model': b2.get('upstream_model') or b1.get('upstream_model'),
    }
    b = dict(b or {})
    b['_billing'] = merged
    return b


def _parse_verdict(text):
    """取最后那条「结论：追读/弃读」；没写就不猜（inconclusive）。"""
    if not isinstance(text, str) or not text.strip():
        return 'inconclusive'
    pattern = re.compile('[' + BT + r'\s*#>\-\u2014]+')
    for line in reversed(text.strip().splitlines()[-6:]):
        s = pattern.sub('', line)
        if '结论' in s or '判断' in s:
            if '追读' in s and '弃读' not in s:
                return 'pass'
            if '弃读' in s:
                return 'fail'
    return 'inconclusive'


def run_reviewer(reviewer, chapter_text, chapter_rel, max_tokens=None, timeout=240,
                 prev_text=None, chars_text=None, map_text=None, ch_no=None, ch_label=None,
                 state_text=None, ledgers=None):
    rid = reviewer.get('id')
    model = reviewer.get('model') or ''
    t0 = time.time()
    res = {'id': rid, 'name': reviewer.get('name') or rid, 'model': model,
           'weight': reviewer.get('weight', 1), 'enabled': reviewer.get('enabled', True),
           'verdict': 'inconclusive', 'verdict_label': '未判定',
           'text': '', 'tokens': 0, 'prompt_tokens': 0, 'completion_tokens': 0,
           'cny': 0.0, 'ms': 0, 'ok': False, 'error': None}
    if not model:
        res['error'] = '未配置 model'
        return res

    budget = int(max_tokens or reviewer.get('max_tokens') or MIN_MAX_TOKENS)
    if budget < MIN_MAX_TOKENS:
        budget = MIN_MAX_TOKENS
    sys_prompt, body, used_chars, has_map, used_states = build_prompt(
        ch_no, ch_label, chapter_text, chapter_rel, prev_text, chars_text, map_text, state_text,
        ledgers, persona=reviewer.get('persona'), reviewer_name=reviewer.get('name'))
    messages = [{'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': body[:26000]}]
    # 客户在 reviewers.yaml 里给了 params 就完全听它的（不同厂商认的参数不一样：
    # deepseek 认 thinking:disabled，glm/kimi 认 reasoning_effort）
    if isinstance(reviewer.get('params'), dict) and reviewer['params']:
        extra = dict(reviewer['params'])
    else:
        extra = {'thinking': {'type': 'disabled'}}
    call_cfg = {'model': model, 'temperature': reviewer.get('temperature', 0.8),
                'max_tokens': budget, 'extra_body': extra}

    try:
        resp = CO.chat(call_cfg, messages)
        text = CO.sanitize_worker_text(CO._extract_content(resp) or '')
        if not text:
            finish = ((resp.get('choices') or [{}])[0]).get('finish_reason')
            # 第 1 次重试：换成 reasoning_effort=low（glm/kimi 这类不认 thinking 开关）
            retry_cfg = dict(call_cfg)
            retry_cfg['extra_body'] = {'reasoning_effort': 'low'}
            try:
                resp_r = CO.chat(retry_cfg, messages)
                text_r = CO.sanitize_worker_text(CO._extract_content(resp_r) or '')
                resp = _merge_billing(resp, resp_r)
                text = text_r
                res['retried'] = 'reasoning_effort=low'
            except Exception:
                pass
            finish = ((resp.get('choices') or [{}])[0]).get('finish_reason')
            if not text and finish == 'length' and budget < RETRY_MAX_TOKENS:
                res['retried'] = (res.get('retried') or '') + '+budget×2'
                big = dict(call_cfg)
                big['max_tokens'] = min(budget * 2, RETRY_MAX_TOKENS)
                resp2 = CO.chat(big, messages)
                resp = _merge_billing(resp, resp2)
                text = CO.sanitize_worker_text(CO._extract_content(resp) or '')
    except Exception as e:
        detail = ''
        try:                     # HTTPError 的 body 里有网关给的 human-readable 原因
            detail = e.read().decode('utf-8', 'replace')[:300]   # type: ignore[attr-defined]
        except Exception:
            detail = str(e)
        if 'insufficient_user_quota' in detail:
            res['error'] = '余额不足：网关返回 insufficient_user_quota，请充值后重试'
        else:
            res['error'] = '%s: %s' % (type(e).__name__, detail or e)
        res['ms'] = int((time.time() - t0) * 1000)
        return res

    billing = resp.get('_billing') or {}
    usage = resp.get('usage') or {}
    res['prompt_tokens'] = int(billing.get('prompt_tokens') or usage.get('prompt_tokens') or 0)
    res['completion_tokens'] = int(billing.get('completion_tokens') or usage.get('completion_tokens') or 0)
    res['tokens'] = int(billing.get('total_tokens') or usage.get('total_tokens') or 0)
    res['cny'] = float(billing.get('total_cny') or 0)
    res['ms'] = int((time.time() - t0) * 1000)
    res['used_chars'] = used_chars
    res['used_states'] = used_states
    res['has_map'] = has_map

    if not text:
        res['error'] = 'empty_output（思考型模型可能吃光了 max_tokens）'
        return res
    res['text'] = text
    res['ok'] = True
    res['verdict'] = _parse_verdict(text)
    res['verdict_label'] = {'pass': '追读', 'fail': '弃读', 'inconclusive': '未判定'}[res['verdict']]
    return res


def merge_reviews(results, mode='vote'):
    """vote=过半弃读才 fail；merge=全部弃读；union=任一弃读。原始意见原样保留。"""
    active = [r for r in results if r.get('ok')]
    total = len(results) or 1
    drop = sum(1 for r in active if r.get('verdict') == 'fail')
    keep = sum(1 for r in active if r.get('verdict') == 'pass')
    undecided = [r.get('id') for r in active if r.get('verdict') == 'inconclusive']

    if mode == 'union':
        reviewer_fail = drop > 0
    elif mode == 'merge':
        reviewer_fail = bool(active) and drop == len(active)
    else:
        reviewer_fail = drop * 2 > total

    if not results:
        return {'mode': mode, 'verdict': 'inconclusive',
                'votes': {'reviewers': 0, 'ok': 0, 'drop': 0, 'keep': 0,
                          'undecided': [], 'failed': 0},
                'labels': {}}
    tie = (mode == 'vote' and drop == len(results) - drop and drop > 0)
    if reviewer_fail:
        verdict = 'fail'
    elif len(active) < len(results) or undecided or tie:
        # 平票（1:1）也是分歧，不能算通过
        verdict = 'inconclusive'
    else:
        verdict = 'pass'

    return {'mode': mode, 'verdict': verdict,
            'votes': {'reviewers': len(results), 'ok': len(active), 'drop': drop,
                      'keep': keep, 'undecided': undecided,
                      'failed': len(results) - len(active)},
            'labels': {r.get('id'): r.get('verdict_label') for r in results}}


def quality_score(results):
    total = sum(int(r.get('weight') or 0) for r in results) or 0
    earned = sum(int(r.get('weight') or 0) for r in results if r.get('verdict') == 'pass')
    ok = sum(1 for r in results if r.get('ok'))
    return {'max': total, 'earned': earned,
            'score': round(earned / total, 4) if total else 0.0,
            'coverage': {'checked': ok, 'total': len(results)}}


def run_gate(chapter_text, chapter_rel, gate_cfg=None, extra_text=None):
    """策略取自 reviewers.yaml，数据取自 config/gate.yaml；数据为空 -> inconclusive。"""
    policy = gate_cfg if gate_cfg is not None else (load_config().get('gate') or [])
    data = load_gate_data()
    text = chapter_text if extra_text is None else extra_text
    chars = len(re.findall(r'[\u4e00-\u9fa5]', text or ''))
    hits, skipped, passed, meta = [], [], [], {}

    def entry(gid):
        v = data.get(gid)
        return v if isinstance(v, dict) else {}

    for g in policy:
        if not isinstance(g, dict):
            continue
        gid = g.get('id')
        action = (g.get('action') or 'warn').lower()
        d = entry(gid)
        if gid == 'word_count':
            lo = d.get('min', g.get('min'))
            if not isinstance(lo, (int, float)):
                skipped.append({'id': gid, 'reason': '未配置 min（reviewers.yaml 与 gate.yaml 都没有）'})
            elif chars < lo:
                hits.append({'id': gid, 'name': g.get('name') or gid, 'action': action,
                             'severity': 'error' if action == 'block' else 'warn',
                             'message': '全章 %d 字，低于门禁下限 %s' % (chars, lo)})
            else:
                passed.append(gid)
        elif gid == 'sensitive':
            words = [w.strip() for w in (d.get('words') or []) if isinstance(w, str) and w.strip()]
            pats = [p.strip() for p in (d.get('patterns') or []) if isinstance(p, str) and p.strip()]
            meta['sensitive_words'] = len(words)
            meta['sensitive_patterns'] = len(pats)
            if not words and not pats:
                skipped.append({'id': gid, 'reason': '未配置词表（config/gate.yaml 的 sensitive.words / patterns 都是空）'})
                continue
            found, bad = [], []
            for w in words:
                if w in (text or ''):
                    found.append(w)
            for p in pats:
                try:
                    m = re.search(p, text or '', re.I)
                    if m:
                        found.append(m.group(0)[:20] or p)
                except re.error as e:
                    bad.append('%s (%s)' % (p, e))
            if found:
                hits.append({'id': gid, 'name': g.get('name') or gid, 'action': action,
                             'severity': 'error' if action == 'block' else 'warn',
                             'message': '敏感词命中 %d 处：%s' % (len(found), '、'.join(found[:8])),
                             'samples': found[:8]})
            elif bad:
                skipped.append({'id': gid, 'reason': '词表可用但正则无效：' + '; '.join(bad[:3])})
            else:
                passed.append(gid)
        elif gid == 'fact_error':
            rules = [r.strip() for r in (d.get('rules') or []) if isinstance(r, str) and r.strip()]
            meta['fact_error_rules'] = len(rules)
            if not rules:
                skipped.append({'id': gid, 'reason': '未配置交叉核对项（config/gate.yaml 的 fact_error.rules 为空）'})
            else:
                skipped.append({'id': gid, 'reason': '已配置 %d 项核对规则，但没有自动核对器，需审稿团/人工兜底' % len(rules)})
        else:
            skipped.append({'id': gid, 'reason': '未知门禁类型'})

    blocked = any(h['action'] == 'block' for h in hits)
    status = 'blocked' if blocked else ('warn' if hits else ('inconclusive' if skipped else 'pass'))
    return {'status': status, 'hits': hits, 'skipped': skipped, 'passed': passed,
            'checked': len(passed), 'total': len(policy),
            'data_path': GATE_PATH, 'data_error': _GATE.get('error'), 'meta': meta}


def dims_summary(state_text, map_text, ledgers):
    """五维注入状态，给 UI 和报告用。"""
    return {
        'space': bool(map_text),
        'time': bool((ledgers or {}).get('timeline')),
        'item': bool(state_text),
        'power': bool((ledgers or {}).get('power')),
        'foreshadow': bool((ledgers or {}).get('foreshadow')),
    }


def _prepare(chapter_rel, ch_override=None, chars_path=None, map_path=None, prev_path=None):
    ch_no, ch_label = chapter_number(chapter_rel, ch_override)
    chars_text = None
    if chars_path and os.path.exists(chars_path):
        with open(chars_path, encoding='utf-8-sig') as f:
            chars_text = f.read()
    map_text = None
    if map_path and os.path.exists(map_path):
        with open(map_path, encoding='utf-8-sig') as f:
            map_text = f.read()
    prev_text = None
    if prev_path and os.path.exists(prev_path):
        with open(prev_path, encoding='utf-8-sig') as f:
            prev_text = '【上一章全文：%s】\n%s' % (
                os.path.basename(prev_path).replace('.md', ''), f.read())
    return ch_no, ch_label, chars_text, map_text, prev_text


VENDOR_OF_MODEL = {
    'deepseek-flash': 'deepseek', 'deepseek-v4-pro': 'deepseek',
    'glm-5.3': 'glm', 'glm-5.3-flash': 'glm',
    'kimi-k3': 'kimi', 'kimi-k3.1-pro': 'kimi',
}


def apply_reviewer_override(cfg, only_ids=None, models=None):
    """返回一份新的 cfg：按 only_ids 过滤，按 models 覆盖模型并调整厂商参数。

    不修改传入的 cfg（深拷贝一份），也不写 reviewers.yaml。
    """
    import copy
    data = copy.deepcopy(cfg or {})
    reviewers = [r for r in (data.get('reviewers') or []) if isinstance(r, dict) and r.get('id')]
    if only_ids:
        wanted = set(only_ids)
        for r in reviewers:
            r['enabled'] = r.get('id') in wanted
    models = models or {}
    for r in reviewers:
        new_model = models.get(r.get('id'))
        if not new_model:
            continue
        r['model'] = new_model
        vendor = VENDOR_OF_MODEL.get(new_model, 'deepseek')
        params = dict(r.get('params') or {})
        if vendor == 'deepseek':
            params.pop('reasoning_effort', None)     # deepseek 不认这个，带着会 400
        elif 'reasoning_effort' not in params:
            params['reasoning_effort'] = 'low'       # glm/kimi 不认 thinking:disabled
        r['params'] = params
    data['reviewers'] = reviewers
    return data


def iter_team(chapter_text, chapter_rel, mode=None, only=None, max_tokens=None,
              timeout=240, max_workers=4, ch_override=None, chars_path=None,
              map_path=None, prev_path=None, cfg_override=None):
    """cfg_override：本次请求临时覆盖 reviewers.yaml（不落盘）。"""
    cfg = cfg_override if isinstance(cfg_override, dict) else load_config()
    mode = (mode or cfg.get('mode') or 'vote').lower()
    if mode not in ('merge', 'union', 'vote'):
        mode = 'vote'
    all_reviewers = reviewers_of(cfg)
    pool = [r for r in all_reviewers if r.get('enabled', True)]
    if only:
        wanted = {x.strip() for x in str(only).split(',') if x.strip()}
        # 显式 --only 视为覆盖 enabled 开关（临时拉某位审稿人来评）
        pool = [r for r in all_reviewers if r.get('id') in wanted]
    disabled = [r.get('id') for r in all_reviewers if not r.get('enabled', True)]

    ch_no, ch_label, chars_text, map_text, prev_text = _prepare(
        chapter_rel, ch_override, chars_path, map_path, prev_path)
    cards_matched = []
    if chars_text:
        cards_matched = pick_characters(chapter_text, parse_char_cards(None, chars_text))
    ledgers = load_ledgers(chapter_rel, chars_path, map_path)
    state_path = locate_state_file(chapter_rel, chars_path, map_path)
    state_text = None
    states_matched = []
    if state_path:
        try:
            with open(state_path, encoding='utf-8-sig') as f:
                state_text = f.read()
            states_matched = pick_states(chapter_text, parse_state_sections(state_text))
        except OSError:
            state_text = None
    revision = 'sha256:' + hashlib.sha256((chapter_text or '').encode('utf-8')).hexdigest()
    standard = '黄金三章' if ch_no <= 3 else ('第 %s 章追读' % ch_label)

    yield {'type': 'review_start', 'chapter': chapter_rel, 'mode': mode,
           'chapter_no': ch_no, 'standard': standard, 'source_revision': revision,
           'chars_file': bool(chars_text), 'chars_matched': cards_matched,
           'chars_injected': bool(cards_matched), 'map_injected': bool(map_text), 'prev_injected': bool(prev_text), 'prev_injected': bool(prev_text),
           'has_state': bool(state_text), 'state_path': state_path,
           'state_chars': states_matched,
           'dims': dims_summary(state_text, map_text, ledgers),
           'ledgers': {k: v['path'] for k, v in (ledgers or {}).items()},
           'reviewers': [{'id': r.get('id'), 'name': r.get('name') or r.get('id'),
                          'model': r.get('model'), 'weight': r.get('weight', 1)} for r in pool],
           'disabled_reviewers': disabled, 'config_error': _CFG.get('error')}

    t0 = time.time()
    results = []
    workers = max(1, min(max_workers, len(pool) or 1))
    with futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {}
        for r in pool:
            yield {'type': 'reviewer_start', 'id': r.get('id'),
                   'name': r.get('name') or r.get('id'), 'model': r.get('model')}
            futs[ex.submit(run_reviewer, r, chapter_text, chapter_rel, max_tokens, timeout,
                           prev_text, chars_text, map_text, ch_no, ch_label, state_text,
                           ledgers)] = r
        for fut in futures.as_completed(futs):
            try:
                res = fut.result()
            except Exception as e:
                r = futs[fut]
                res = {'id': r.get('id'), 'name': r.get('name') or r.get('id'),
                       'model': r.get('model'), 'weight': r.get('weight', 1),
                       'verdict': 'inconclusive', 'verdict_label': '未判定', 'text': '',
                       'tokens': 0, 'ok': False,
                       'error': '%s: %s' % (type(e).__name__, e), 'ms': 0}
            results.append(res)
            ev = {'type': 'reviewer_done'}
            ev.update(res)
            yield ev

    order = {r.get('id'): i for i, r in enumerate(pool)}
    results.sort(key=lambda r: order.get(r.get('id'), 99))
    merged = merge_reviews(results, mode)
    gate = run_gate(chapter_text, chapter_rel)
    quality = quality_score(results)
    totals = {'tokens': sum(r.get('tokens') or 0 for r in results),
              'prompt_tokens': sum(r.get('prompt_tokens') or 0 for r in results),
              'completion_tokens': sum(r.get('completion_tokens') or 0 for r in results),
              'cny': round(sum(r.get('cny') or 0 for r in results), 6)}
    # 自动流转：inconclusive/fail -> blocked（要人决定）；pass -> awaiting（等确认）
    try:
        import stages as ST
        path_abs = chapter_rel if os.path.isabs(chapter_rel) else os.path.join(CO.ROOT, chapter_rel)
        book = ST.book_of_path(path_abs)
        if book:
            votes = (merged or {}).get('votes') or {}
            drop, keep, failed = votes.get('drop', 0), votes.get('keep', 0), votes.get('failed', 0)
            hits = (gate or {}).get('hits') or []
            if (gate or {}).get('status') == 'blocked' and hits:
                stage, reason, action = 'blocked', (hits[0].get('message') or '门禁拦截'), 'choose'
            elif merged['verdict'] == 'inconclusive':
                stage = 'blocked'
                action = 'retry' if failed else 'choose'
                reason = ('审稿团 %d 路没跑通，结论不可用' % failed) if failed else (
                    '审稿团意见分歧：弃读 %d / 追读 %d，需要你定' % (drop, keep)
                    if (drop or keep) else '审稿团没给出结论，需要你看一眼')
            elif merged['verdict'] == 'fail':
                stage, reason, action = 'blocked', '审稿团判弃读（%d 票），建议重写' % drop, 'retry'
            else:
                stage, reason, action = 'awaiting', '审稿团判可追读（%d 票），等你确认' % keep, 'confirm'
            ST.set_stage(book, ch_no, stage, reason=reason, source='reviewers', action=action)
    except Exception:
        pass

    yield {'type': 'team_done', 'chapter': chapter_rel, 'source_revision': revision,
           'mode': mode, 'chapter_no': ch_no, 'standard': standard,
           'chars_file': bool(chars_text), 'chars_matched': cards_matched,
           'chars_injected': bool(cards_matched), 'map_injected': bool(map_text), 'prev_injected': bool(prev_text), 'prev_injected': bool(prev_text),
           'has_state': bool(state_text), 'state_path': state_path,
           'state_chars': states_matched,
           'dims': dims_summary(state_text, map_text, ledgers),
           'ledgers': {k: v['path'] for k, v in (ledgers or {}).items()},
           'reviewers': results, 'disabled_reviewers': disabled,
           'merged': merged, 'gate': gate, 'quality': quality, 'totals': totals,
           'elapsed_ms': int((time.time() - t0) * 1000),
           'config_error': _CFG.get('error')}


def run_team(chapter_text, chapter_rel, write=True, **kw):
    final = None
    for ev in iter_team(chapter_text, chapter_rel, **kw):
        if ev.get('type') == 'team_done':
            final = ev
    if final is None:
        return {'chapter': chapter_rel, 'mode': 'vote', 'reviewers': [],
                'merged': {'mode': 'vote', 'verdict': 'inconclusive', 'votes': {}, 'labels': {}},
                'gate': {'status': 'inconclusive', 'hits': [], 'skipped': [], 'total': 0},
                'quality': {'max': 0, 'earned': 0, 'score': 0.0,
                            'coverage': {'checked': 0, 'total': 0}},
                'totals': {'tokens': 0, 'cny': 0}, 'elapsed_ms': 0,
                'config_error': _CFG.get('error')}
    out = {k: v for k, v in final.items() if k != 'type'}
    if write:
        try:
            out['report_path'] = write_report(out, chapter_rel)
        except OSError as e:
            out['report_path'] = None
            out['report_error'] = str(e)
    return out


def report_path_for(chapter_rel):
    """报告落在 <章节目录>/../reports/审稿结果-<章名>.md（跟 YG 的参考实现一致）。"""
    stem = os.path.splitext(os.path.basename(chapter_rel))[0]
    return os.path.abspath(os.path.join(os.path.dirname(chapter_rel), '..', 'reports',
                                        '审稿结果-%s.md' % stem))


def render_report(out):
    """把一次审稿结果渲染成带摘要头的 Markdown。"""
    m = out.get('merged') or {}
    votes = m.get('votes') or {}
    totals = out.get('totals') or {}
    q = out.get('quality') or {}
    chars = out.get('chars_matched') or []
    lines = ['# 审稿结果 · %s' % os.path.splitext(os.path.basename(out.get('chapter') or ''))[0], '']
    lines.append('> 标准：%s | 章号：%s | 模式：%s' % (
        out.get('standard') or '-', out.get('chapter_no', '-'), out.get('mode') or '-'))
    dims = out.get('dims') or {}
    dim_txt = ' '.join('%s=%s' % (k, '✓' if v else '✗')
                       for k, v in (('空间', dims.get('space')), ('时间', dims.get('time')),
                                    ('物品', dims.get('item')), ('能力', dims.get('power')),
                                    ('伏笔', dims.get('foreshadow'))))
    lines.append('> 角色注入：%s | 地图：%s' % (
        '、'.join(chars) if chars else '未注入',
        '已注入（含行程时间矩阵）' if out.get('map_injected') else '未注入'))
    lines.append('> 五维：%s' % dim_txt)
    lines.append('> 合并：%s（%s 票：弃读 %s / 追读 %s / 未判定 %s / 失败 %s）| 质量分：%s/%s' % (
        (m.get('verdict') or '-').upper(),
        votes.get('ok', 0), votes.get('drop', 0), votes.get('keep', 0),
        len(votes.get('undecided') or []), votes.get('failed', 0),
        q.get('earned', 0), q.get('max', 0)))
    lines.append('> 花费：%s tok / ¥%s / %.1fs' % (
        totals.get('tokens', 0), totals.get('cny', 0), (out.get('elapsed_ms') or 0) / 1000))
    lines.append('')
    for r in out.get('reviewers') or []:
        lines += ['---', '', '## %s（%s）· %s · %s tok · %.1fs' % (
            r.get('id'), r.get('model'), r.get('verdict_label') or '未判定',
            r.get('tokens', 0), (r.get('ms') or 0) / 1000), '']
        lines.append(r.get('text') or ('（未跑通：%s）' % r.get('error')))
        lines.append('')
    gate = out.get('gate') or {}
    lines += ['---', '', '## 门禁（独立判定，不并入质量分）', '',
              '- 状态：%s' % (gate.get('status') or '-'),
              '- 命中：%s' % (gate.get('hits') or '无')]
    for s in gate.get('skipped') or []:
        lines.append('- 未判定：%s —— %s' % (s.get('id'), s.get('reason')))
    lines.append('')
    lines += ['## 合并明细', '', chr(96) * 3, json.dumps(m, ensure_ascii=False, indent=2), chr(96) * 3, '']
    return '\n'.join(lines)


def write_report(out, chapter_rel=None, path=None):
    target = path or report_path_for(chapter_rel or out.get('chapter'))
    os.makedirs(os.path.dirname(target) or '.', exist_ok=True)
    with open(target, 'w', encoding='utf-8') as f:
        f.write(render_report(out))
    return target


def _main():
    args = sys.argv[1:]
    if not args:
        print('用法: python core/reviewers.py <本章md> [--chars 角色卡.md] [--map 地图.md] '
              '[--ch N] [--prev 上一章.md] [--mode vote|merge|union] [--json [路径]]')
        return 0
    path = args[0]

    def opt(name, default=None):
        if name in args:
            i = args.index(name)
            if i + 1 < len(args) and not args[i + 1].startswith('--'):
                return args[i + 1]
        return default

    names = ('--chars', '--map', '--ch', '--prev', '--mode', '--json', '--only', '--max-tokens')
    no_report = '--no-report' in args
    opts = {k: opt(k) for k in names}
    want_json = '--json' in args
    with open(path, encoding='utf-8-sig') as f:
        text = f.read()

    out = run_team(text, path, write=not no_report, mode=opts['--mode'], only=opts['--only'],
                   max_tokens=int(opts['--max-tokens']) if opts['--max-tokens'] else None,
                   ch_override=opts['--ch'], chars_path=opts['--chars'],
                   map_path=opts['--map'], prev_path=opts['--prev'])
    if want_json:
        payload = json.dumps(out, ensure_ascii=False, indent=2)
        jp = opts['--json']
        if jp:
            p = os.path.abspath(jp)
            os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(payload)
        print(payload)
        return 0

    print('审稿团 %s  标准=%s  模式=%s  用时 %.1fs  消耗 %d tok / CNY %.4f' % (
        os.path.basename(path), out.get('standard'), out['mode'],
        out['elapsed_ms'] / 1000, out['totals']['tokens'], out['totals']['cny']))
    print('角色注入：%s   地图注入：%s' % (
        '是' if out.get('chars_injected') else '否', '是' if out.get('map_injected') else '否'))
    for r in out['reviewers']:
        print('\n' + '=' * 70)
        print('%s（%s）%s  %d tok  %dms' % (
            r['id'], r['model'], r.get('verdict_label'), r['tokens'], r['ms']))
        print('=' * 70)
        print(r.get('text') or ('（未跑通：%s）' % r.get('error')))
    m = out['merged']
    print('\n' + '-' * 70)
    print('合并(%s)：%s   %s' % (m['mode'], m['verdict'].upper(),
                                json.dumps(m['votes'], ensure_ascii=False)))
    g = out['gate']
    print('门禁：%s  命中 %d / 未判 %d' % (g['status'], len(g['hits']), len(g['skipped'])))
    for s in g['skipped']:
        print('   - %s 未判定：%s' % (s['id'], s['reason']))
    q = out['quality']
    print('质量分：%s/%s (%s)  覆盖 %s/%s' % (q['earned'], q['max'], q['score'],
                                         q['coverage']['checked'], q['coverage']['total']))
    if out.get('report_path'):
        print('报告：%s' % out['report_path'])
    return 0


if __name__ == '__main__':
    sys.exit(_main())

# ---------------------------------------------------------------------------
# 审稿团裁决（照 docs/架构-通用版/04-审稿团使用规范.md 第四节）
# ---------------------------------------------------------------------------

CONSENSUS_PROMPT = """你在做审稿意见的裁决。下面是 N 个审稿人对同一章的意见。

规则（严格照做）：
1. 三个人都提到的同一个问题 -> 进 must_fix
2. 两个人提到，且是同一个问题的不同说法 -> 进 must_fix
3. 只有一个人提到 -> 进 pending（可能是口味）
4. 空话套话（节奏略慢 / 人物不够丰满 / 建议加个反转）-> 进 ignored
5. 批评必须具体到原文某一句或某个事实，否则一律进 ignored

输出严格的 JSON，不要任何解释文字：
{
  "must_fix": [
    {"issue": "一句话说清是什么问题", "quote": "原文里对应的那句", "who": ["审稿人id"], "why": "为什么必须改"}
  ],
  "pending": [
    {"issue": "...", "who": ["id"]}
  ],
  "ignored": [
    {"reason": "为什么算空话", "sample": "原文片段"}
  ]
}

审稿意见如下：
"""


def _review_text_of(r):
    for k in ('review', 'text', 'content', 'raw', 'opinion', 'body'):
        v = r.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ''


def extract_consensus(results, cfg=None, model=None):
    """把 N 家意见交给模型裁决成 must_fix / pending / ignored。

    规范第四节：三家共识必改；两家同一问题改；一家独有放着；空话忽略。
    没有可用的意见时返回空组 + ok=False，不静默通过。
    """
    active = [r for r in (results or []) if r.get('ok')]
    opinions = []
    for r in active:
        t = _review_text_of(r)
        if t:
            opinions.append({'id': r.get('id') or '?', 'label': r.get('label') or '', 'text': t[:6000]})
    if len(opinions) < 2:
        return {'ok': False, 'error': '可裁决的意见少于 2 家', 'must_fix': [], 'pending': [], 'ignored': [], 'reviewers': len(opinions)}

    body = []
    for o in opinions:
        body.append('=== 审稿人 %s %s ===\n%s' % (o['id'], ('(' + o['label'] + ')') if o['label'] else '', o['text']))
    prompt = CONSENSUS_PROMPT + '\n\n'.join(body)

    try:
        layer = CO.resolve_layer('quality') or {}
        use_model = model or layer.get('model') or 'deepseek-flash'
        call_cfg = {'model': use_model, 'temperature': 0.1, 'max_tokens': 2000}
        resp = CO.chat(call_cfg, [{'role': 'user', 'content': prompt}])
        raw = CO._extract_content(resp) or ''
    except Exception as e:
        return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e), 'must_fix': [], 'pending': [], 'ignored': [], 'reviewers': len(opinions)}

    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return {'ok': False, 'error': '模型没返回 JSON', 'raw': raw[:400], 'must_fix': [], 'pending': [], 'ignored': [], 'reviewers': len(opinions)}
    try:
        data = json.loads(m.group(0))
    except Exception as e:
        return {'ok': False, 'error': 'JSON 解析失败: %s' % e, 'raw': raw[:400], 'must_fix': [], 'pending': [], 'ignored': [], 'reviewers': len(opinions)}

    def arr(k):
        v = data.get(k)
        return v if isinstance(v, list) else []

    return {'ok': True, 'must_fix': arr('must_fix'), 'pending': arr('pending'), 'ignored': arr('ignored'),
            'reviewers': len(opinions),
            'counts': {'must_fix': len(arr('must_fix')), 'pending': len(arr('pending')), 'ignored': len(arr('ignored'))}}
