# -*- coding: utf-8 -*-
"""世界观策划流水线（13 步 · 照 docs/架构-通用版/10-世界观策划流水线-13agent.md）

设计原则（抄文档原文）：
  · 用不用、用哪几步，由**作品本身**决定，不由题材决定
  · 每一步前面都有一个判断问题。答"有"，就做；答"没有"，跳过
  · 不给预设答案（不写"修仙该有几级"）

存储：
  projects/<book>/策划/00-状态.json     每步状态
  projects/<book>/策划/<步编号>-<名字>.md  每步产出
"""
import io
import json
import os
import re
import time

# 13 步定义：(编号, 名字, 必需?, 判断问题, 产出文件名)
# 顺序照文档 §六：① 发散 → ② 评估 → ③ 落地 →【按需 8 步】→ ④ 推演冲突 → ⑫ 结构
# （2026-11-09 修：原来 04 排在 12 后面，先排结构再推冲突，与文档相反）
STEPS = [
    ('01', '发散',     True,  '', '方案池'),
    ('02', '评估',     True,  '', '优选方案'),
    ('03', '落地',     True,  '', '设定成品'),
    ('05', '文风变体', False, '同一个设定，你想看几种不同写法的对比吗？', '文风变体'),
    ('06', '能力体系', False, '这本书里，人物的能力会随故事推进而变强吗？', '能力体系'),
    ('07', '主角优势', False, '主角有没有一样别人没有的东西？', '主角优势'),
    ('08', '开局方案', False, '你希望我出几种不同的开头方案，让你挑？', '开局方案'),
    ('09', '群像',     False, '除了主角，还有多个重要角色吗？', '群像'),
    ('10', '文笔定型', False, '你需要一份「句式怎么写」的模板，保证全书一致吗？', '文笔定型'),
    ('11', '黄金三章', False, '这是网络平台连载吗？前三章决定读者留不留？', '黄金三章'),
    ('13', '配角专项', False, '你有 5 个以上需要「各自有戏」的配角吗？', '配角专项'),
    ('04', '推演冲突', True,  '', '冲突与钩子'),
    ('12', '结构',     True,  '', '大纲细纲'),
]


# 哪几步「没有人就只能出草稿」。用于排序和提示，不用于拦截：
# 作者可以不建人物卡一路跑完，只是这几步的产出会停在"类型层"。
NEEDS_PEOPLE = frozenset(('04', '07', '08', '09', '11', '12', '13'))


def _has_people(book):
    """书里有没有"人"：角色卡/ 下存在像样的 .md 就算有。

    不看 角色卡.md 那个索引（模板生成，只有几行双链），也不看 角色.md（空模板）。
    """
    d = os.path.join(_book_dir(book), '设定库', '角色卡')
    if not os.path.isdir(d):
        return False
    try:
        for f in os.listdir(d):
            if f.endswith('.md') and os.path.getsize(os.path.join(d, f)) > 40:
                return True
    except OSError:
        return False
    return False


def _root():
    """projects 根目录。与 plugin/lib/index.js 的 projectsRoot() 保持同序。"""
    cands = [
        os.environ.get('NOVELAPP_PROJECTS'),
        os.path.join(os.environ.get('NOVELAPP_ROOT') or os.getcwd(), 'projects'),
        os.path.join(os.environ.get('NOVELAPP_DATA') or
                     os.path.join(os.environ.get('APPDATA') or '', 'novelapp-desktop', 'data'),
                     'projects'),
    ]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return cands[-1]


def _dir(book):
    d = os.path.join(_root(), book, '策划')
    return d


def _state_path(book):
    return os.path.join(_dir(book), '00-状态.json')


def _read_json(p, default=None):
    try:
        with io.open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def _write_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))
    os.replace(tmp, p)


def default_state(book):
    """全新状态：必需 5 步 pending，按需 8 步 undecided（还没回答判断问题）。"""
    steps = {}
    for sid, name, req, q, out in STEPS:
        steps[sid] = {
            'id': sid, 'name': name, 'required': req, 'question': q,
            'status': 'pending' if req else 'undecided',
            'skip_reason': '', 'updated': '',
        }
    return {'book': book, 'version': 1, 'steps': steps}


def load_state(book):
    st = _read_json(_state_path(book), None)
    if not st or not isinstance(st.get('steps'), dict):
        return default_state(book)
    # 补齐新增的步骤 / 字段（老状态文件不炸）
    base = default_state(book)
    for sid, d in base['steps'].items():
        cur = st['steps'].get(sid)
        if not isinstance(cur, dict):
            st['steps'][sid] = d
        else:
            for k, v in d.items():
                cur.setdefault(k, v)
    st['book'] = book
    st.setdefault('version', 1)
    return st


def save_state(book, state):
    state['book'] = book
    _write_json(_state_path(book), state)
    return state


def set_step(book, sid, status=None, skip_reason=None):
    """改一步的状态。status ∈ pending / doing / done / skipped / undecided。"""
    st = load_state(book)
    cur = st['steps'].get(sid)
    if not cur:
        raise ValueError('未知步骤：%s' % sid)
    if status is not None:
        if status not in ('pending', 'doing', 'done', 'skipped', 'undecided'):
            raise ValueError('非法状态：%s' % status)
        cur['status'] = status
        if status == 'skipped':
            cur['skip_reason'] = str(skip_reason or '')
        elif status in ('done', 'doing'):
            cur['skip_reason'] = ''
    cur['updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
    # 必需步骤不能标 skipped（文档：必需 5 步任何作品都要走）
    if cur['required'] and cur['status'] == 'skipped':
        cur['status'] = 'pending'
        cur['skip_reason'] = ''
    save_state(book, st)
    return cur


def step_file(book, sid):
    """返回某一步产出的文件绝对路径（不一定存在）。"""
    for s in STEPS:
        if s[0] == sid:
            return os.path.join(_dir(book), '%s-%s.md' % (s[0], s[1]))
    return ''


def read_step(book, sid):
    p = step_file(book, sid)
    if not p or not os.path.exists(p):
        return ''
    try:
        with io.open(p, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


def write_step(book, sid, text):
    p = step_file(book, sid)
    if not p:
        raise ValueError('未知步骤：%s' % sid)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(text or '')
    os.replace(tmp, p)
    return p


def summary(book):
    """给 UI 的一屏数据：13 步 + 状态 + 产出字数 + 进度。"""
    st = load_state(book)
    out = []
    done = 0
    required_done = 0
    required_total = 0
    lacks_people = not _has_people(book)
    for sid, name, req, q, outname in STEPS:
        cur = st['steps'].get(sid) or {}
        text = read_step(book, sid)
        item = {
            'id': sid, 'name': name, 'required': bool(req), 'question': q,
            'status': cur.get('status') or 'pending',
            'skip_reason': cur.get('skip_reason') or '',
            'updated': cur.get('updated') or '',
            'chars': len(text),
            'has_output': bool(text.strip()),
            'needs_people': sid in NEEDS_PEOPLE,
            'blocked_by_people': (sid in NEEDS_PEOPLE and lacks_people),
        }
        if req:
            required_total += 1
            if item['status'] == 'done':
                required_done += 1
        if item['status'] == 'done':
            done += 1
        out.append(item)
    # 下一个该做的：必需优先，其次按需；缺人物的步骤往后让
    # （作者可以强行做，这里只决定"默认指到哪一步"，不做拦截）
    nxt = ''
    blocked_first = ''
    for item in out:
        if item['status'] in ('done', 'skipped'):
            continue
        if not item['required']:
            continue
        if item['blocked_by_people']:
            blocked_first = blocked_first or item['id']
            continue
        nxt = item['id']
        break
    if not nxt:
        for item in out:
            if item['status'] in ('done', 'skipped'):
                continue
            if item['blocked_by_people']:
                blocked_first = blocked_first or item['id']
                continue
            nxt = item['id']
            break
    if not nxt:
        # 只剩"缺人物"的步骤：指过去，UI 会提示先补人（仍允许强行做）
        nxt = blocked_first
    return {
        'book': book,
        'steps': out,
        'lacks_people': lacks_people,
        'brief': get_brief(book),
        'genre': _book_genre(book),
        'library': list_library(),
        'refs': get_refs(book),
        'blocked_ids': [i['id'] for i in out if i['blocked_by_people']],
        'progress': {
            'done': done, 'total': len(STEPS),
            'required_done': required_done, 'required_total': required_total,
            'can_freeze': required_done == required_total,
            'next': nxt,
        },
    }

# ---------------------------------------------------------------------------
# 步骤 AI 辅助（照 docs/架构-通用版/10-世界观策划流水线-13agent.md）
# ---------------------------------------------------------------------------
# 原则（文档原文）：
#   · 只提供「怎么判断要不要做这一步」，不提供「你必须有什么」
#   · 不给预设答案（不写「修仙该有几级」）
#   · ① 只发散不筛选；② 选出最高分 + 写清它弱在哪

STEP_PROMPTS = {
    '01': (
        '你在帮一位作者想出几个不同的开书方向。',
        '要求：\n'
        '1. 先列出这个题材里最常见的 5 种写法（只列，不评价）\n'
        '2. 每一条问：如果反过来写会怎样？\n'
        '3. 产出 5 个「核心机制完全不同」的方向，每个一句话说清核心是什么\n'
        '\n'
        '铁律：只发散，不筛选。这时候不要判断好坏，不要推荐哪个。\n'
        '不要给「修仙该有几级」「都市异能该怎么设定」这类预设答案。\n'
        '\n'
        '参照物怎么用：\n'
        '· 上文给了「拆书库」的拆解，就按那些书的实际做法来列，并点名是哪一本\n'
        '  （例：凡人修仙传是体系清楚、门槛硬、节奏慢）。\n'
        '· 只有「推荐书单」这类导读，就只用它的一句话说特点，不要展开讲情节。\n'
        '· 什么都没有时，明确写「以下是通用套路归纳，不是对具体作品的判断」，\n'
        '  不要假装读过某本书、不要编书名。\n'
        '· 参照书是拿来「看别人怎么解决同一个问题」的，不是拿来抄的：\n'
        '  列完常见写法后，反过来写的方向要是你自己的，不要把别人书里的设定搬过来。\n'
        '· 作者勾了几本参照书，就做「融合」：每本贡献它最擅长的一条，合成一个方向。\n'
        '  要写清「A 给的是代价设计，B 给的是开篇节奏」，并说明它们为什么能拼到一起；\n'
        '  拼不上的地方直接指出来，不要硬凑——融合不是把几本书的特点摞在一起。\n'
        '\n'
        '直接给产出。不要写「设定库目前是空模板」「我先不填……」「整体思路是」这类说明，\n'
        '也不要复述我给你的要求。第一行就是「## 常见的 5 种写法」。\n'
        '\n'
        '输出格式：\n'
        '## 常见的 5 种写法\n'
        '1. ...\n'
        '...\n'
        '\n'
        '## 5 个方向\n'
        '### 方向 A：<一句话核心>\n'
        '- 常见写法是……反过来是……\n'
        '### 方向 B：...\n'
    ),
    '02': (
        '你在帮一位作者评估几个开书方向。',
        '要求：对每个方向按五个维度打分（每项 10 分），然后选出最高分，并写清「它弱在哪」。\n'
        '\n'
        '五个维度：\n'
        '· 新颖度   这个方向别人写过吗\n'
        '· 自洽性   内部逻辑站得住吗\n'
        '· 戏剧冲突 能不能自然产生矛盾\n'
        '· 文风适配 和作者想写的气质合不合\n'
        '· 落地性   作者能不能写完\n'
        '\n'
        '输出格式：\n'
        '## 打分表\n'
        '| 方向 | 新颖 | 自洽 | 冲突 | 文风 | 落地 | 合计 |\n'
        '|---|---|---|---|---|---|---|\n'
        '| A | 7 | 8 | ... | | | |\n'
        '\n'
        '## 选它\n'
        '<哪个方向，为什么>\n'
        '\n'
        '## 它弱在哪\n'
        '<必须写，不许空着>\n'
    ),
    '03': (
        '你在帮一位作者把选定的方向想清楚，写成一份能自圆其说的设定。',
        '必须回答这四条（想清楚即可，不用面面俱到）：\n'
        '· 这个世界的核心规则是什么\n'
        '· 规则会自然产生什么后果\n'
        '· 人物在这个世界里怎么活\n'
        '· 哪些地方还没想清楚（标出来，不要硬编）\n'
        '\n'
        '输出格式：\n'
        '## 核心规则\n## 自然后果\n## 人物怎么活\n## 未想清楚清单\n'
        '\n'
        '铁律：够用即冻结。别追求面面俱到，写的时候用到再补。\n'
        '不要替作者定「力量体系分几级」这种东西，让作者自己写。\n'
    ),
    '04': (
        '你在帮一位作者从世界规则推演冲突。',
        '从这个世界的规则出发推：\n'
        '· 谁会因此受益，谁会因此受损\n'
        '· 这两种人怎么对立\n'
        '· 过去发生过什么（历史）\n'
        '· 主角会面对什么非此即彼的选择\n'
        '· 有什么长期悬着的问题\n'
        '\n'
        '输出格式：\n'
        '## 受益者 / 受损者\n## 阵营对立\n## 历史事件\n## 人物两难\n## 长线钩子\n'
        '\n'
        '铁律：冲突必须从规则推出来，不许外力硬塞。\n'
        '每条冲突都要指明「它来自哪条规则」。\n'
    ),
    '12': (
        '你在帮一位作者把设定排成能写完的形状。',
        '输出三层结构：\n'
        '· 总纲：主题 / 主线 / 最终要解决什么 / 人物怎么变\n'
        '· 分卷：每卷什么目标 / 卷末发生什么不可逆的事\n'
        '· 细纲：开局几章每章大概写什么\n'
        '\n'
        '输出格式：\n'
        '## 总纲\n## 分卷\n## 开局细纲\n'
        '\n'
        '注意：不知道作者要写多少卷，就先给 2-3 卷的骨架，标「待定」。\n'
    ),
}


def _book_dir(book):
    return os.path.join(_root(), book)


def _read_setting(book, name):
    for sub in ('设定库', '策划'):
        p = os.path.join(_book_dir(book), sub, name)
        if os.path.exists(p):
            try:
                with io.open(p, encoding='utf-8') as f:
                    return f.read()
            except OSError:
                return ''
    return ''


# 上下文预算（字）：单步产出上限 + 总量上限
_CTX_REQUIRED_CHARS = 3000
_CTX_OPTIONAL_CHARS = 2000
_CTX_TOTAL_CHARS = 24000
_SETTING_FILES = 6
_SETTING_CHARS = 1200


def _book_genre(book):
    """项目信息.md 里的「题材」。没填（未定/待填）就当没有，不硬猜。"""
    t = _read_text(os.path.join(_book_dir(book), '项目信息.md'))
    m = re.search(r'^\s*[-*]?\s*(?:题材|基调|风格|类型)\s*[:：]\s*(.+)$', t, re.M)
    if not m:
        return ''
    v = m.group(1).strip()
    return '' if v in ('未定', '待填', '（待填）', '-', '—') else v


def get_brief(book):
    """作者自己写的一句「想写成什么」。可以是空的 —— 空着就按通用套路发散。"""
    st = _read_json(_state_path(book), None) or {}
    return str(st.get('brief') or '')


def set_brief(book, text):
    st = load_state(book)
    st['brief'] = str(text or '').strip()[:600]
    save_state(book, st)
    return st['brief']


def _read_text(p):
    try:
        with io.open(p, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return ''


# 开书参照：拆书库在 data/拆书库，不在 projects 下
_LIB_SUMMARY = 1200
_LIB_HOOK = 600
_MAX_REFS = 6


def _lib_dir():
    """拆书库根目录。data 根有三处可能，逐个试。"""
    for base in (os.environ.get('NOVELAPP_DATA'),
                 os.path.dirname(_root()),
                 os.path.join(os.environ.get('APPDATA') or '', 'novelapp-desktop', 'data')):
        if not base:
            continue
        cand = os.path.join(base, '拆书库')
        if os.path.isdir(cand):
            return cand
    return ''


def list_library():
    """拆书库里已经拆过哪些书（给 01 的勾选列表用）。"""
    lib = _lib_dir()
    out = []
    if not lib:
        return out
    d = os.path.join(lib, '书籍拆解')
    try:
        names = sorted(n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n)))
    except OSError:
        return out
    for nm in names:
        t = _read_text(os.path.join(d, nm, '十合一.md'))
        h = _read_text(os.path.join(d, nm, '01-开篇钩子.md'))
        if not (t.strip() or h.strip()):
            continue
        out.append({'name': nm, 'has_summary': bool(t.strip()), 'has_hook': bool(h.strip())})
    return out


def get_refs(book):
    """作者勾了要参考哪几本。空 = 一本都不参考（只给导读）。

    库里已经不存在的书名自动丢掉：作者勾过书、后来又清了拆书库，
    不清的话上下文会出现「参照书 xx」但下面没内容，UI 也还高亮着。
    """
    st = _read_json(_state_path(book), None) or {}
    r = st.get('refs')
    picked = [str(x) for x in r] if isinstance(r, list) else []
    if not picked:
        return []
    exist = set(b['name'] for b in list_library())
    return [x for x in picked if x in exist]


def set_refs(book, refs):
    st = load_state(book)
    st['refs'] = [str(x)[:60] for x in (refs or [])][:_MAX_REFS]
    save_state(book, st)
    return st['refs']


def _library_digest(book):
    """开书时的参照材料：作者勾选的那几本（十合一 + 开篇钩子）+ 推荐书单。

    为什么不默认全带：拆 10 本全塞进去会把上下文冲爆，而且作者未必想学那几本。
    勾了就只带勾的；一本不勾就只给推荐书单（导读），点明「没有拆解，别假装读过」。
    """
    lib = _lib_dir()
    if not lib:
        return []
    out = []
    d = os.path.join(lib, '书籍拆解')
    refs = get_refs(book)
    for nm in refs:
        t = _read_text(os.path.join(d, nm, '十合一.md'))
        h = _read_text(os.path.join(d, nm, '01-开篇钩子.md'))
        if not (t.strip() or h.strip()):
            continue
        block = '【参照书 · %s】\n' % nm
        if t.strip():
            block += '十合一：\n' + t.strip()[:_LIB_SUMMARY] + '\n'
        if h.strip():
            block += '开篇钩子：\n' + h.strip()[:_LIB_HOOK]
        out.append(block)
    if refs:
        out.append('【这本（几）书是作者亲自挑的参照】\n'
                   '融合时要说清每本贡献了什么（「A 给的是代价设计，B 给的是开篇节奏」），\n'
                   '并说明为什么它们能拼到一起；拼不上的地方要指出来，不要硬凑。')
    else:
        out.append('【作者没有挑参照书。只有下面的导读，没有拆解。】\n'
                   '只能用语一句话说特点，不要展开讲情节，也不要假装读过某一本。')
    rec = _read_text(os.path.join(lib, '推荐书单.md'))
    if rec.strip():
        out.append('【拆书库 · 推荐书单（只是导读，不是拆解）】\n' + rec.strip()[:1200])
    return out


def _settings_digest(book):
    """设定库摘要：设定库/ 下的一层 .md 与子目录里的 .md（如 角色卡/甲.md）。

    2026-11-09 修：原来只认「世界地图.md / 力量体系.md / 角色卡.md」三个硬编码
    文件名，策划产出的 06-能力体系.md 这类文件永远进不来。
    """
    base = os.path.join(_book_dir(book), '设定库')
    picked = []
    try:
        for nm in sorted(os.listdir(base)):
            full = os.path.join(base, nm)
            if nm.lower().endswith('.md'):
                picked.append(nm)
            elif os.path.isdir(full):
                try:
                    for sub in sorted(os.listdir(full)):
                        if sub.lower().endswith('.md'):
                            picked.append(os.path.join(nm, sub))
                except OSError:
                    pass
    except OSError:
        picked = []
    out = []
    for nm in picked[:_SETTING_FILES]:
        t = _read_setting(book, nm)
        if t.strip():
            out.append('【设定库 · %s】\n%s' % (nm, t.strip()[:_SETTING_CHARS]))
    return out


def _context_for(book, sid):
    """给模型看的上文：所有已动手步骤的产出（必需优先）+ 设定库摘要。

    2026-11-09 修：原来只喂「必需步骤」，按需步骤（06 能力体系 / 07 主角优势 /
    09 群像 / 13 配角专项…）的产出进不了 04 推演冲突、12 结构的上下文，违反文档
    §六「④ 要吃掉所有已产出的设定」。现在 done/doing 且非 skipped 的产出全进：
    必需每步 3000 字、按需每步 2000 字，总量封顶 24000 字。
    """
    st = load_state(book)
    req, opt = [], []
    for s in STEPS:
        if s[0] == sid:
            continue
        cur = st['steps'].get(s[0]) or {}
        if cur.get('status') == 'skipped':
            continue
        t = read_step(book, s[0])
        if not t.strip():
            continue
        tag = '已完成' if cur.get('status') == 'done' else '草稿'
        cap = _CTX_REQUIRED_CHARS if s[2] else _CTX_OPTIONAL_CHARS
        block = '【%s · %s %s】\n%s' % (tag, s[0], s[1], t.strip()[:cap])
        (req if s[2] else opt).append(block)
    parts = req + opt + _settings_digest(book)
    # 发散和评估要有参照物：题材 + 作者想写的方向 + 拆书库，三样喂进去才不泛泛
    if sid in ('01', '02'):
        head = []
        g = _book_genre(book)
        b = get_brief(book)
        if g:
            head.append('【这本书的题材】%s' % g)
        if b:
            head.append('【作者想写的方向】%s' % b)
        if not g and not b:
            head.append('【这本书的题材】作者还没说。可以按最宽泛的框架推，'
                        '但要在开头一句话说明你假设了什么，别假装知道他要写什么。')
        parts = head + parts + _library_digest(book)
    out = '\n\n'.join(parts)
    if len(out) > _CTX_TOTAL_CHARS:
        out = out[:_CTX_TOTAL_CHARS] + '\n\n（上文超长，已截到 %d 字）' % _CTX_TOTAL_CHARS
    return out



# --- 按需 8 步的 prompt（有这个概念才做；每步先问判断问题）---

STEP_PROMPTS.update({
    '05': (
        '你在帮一位作者看同一设定的几种不同写法（只改气质，不改内容）。',
        '做法：\n'
        '· 版本 A：作者现在的写法\n'
        '· 版本 B：气质相反的一版\n'
        '· 版本 C：极简大纲版（只留骨架）\n'
        '\n'
        '铁律：机制和因果一字不动，只改口吻、节奏、密度。\n'
        '\n'
        '输出格式：\n## 版本 A（现有气质）\n## 版本 B（相反气质）\n## 版本 C（骨架）\n'
        '\n最后写一段「三个版本的差别在哪」，说明改的是哪几项。\n'
    ),
    '06': (
        '你在帮一位作者设计能力体系。',
        '必须回答：\n'
        '· 强是怎么来的（从哪获取）\n'
        '· 一共分几级\n'
        '· 每一级要跨过什么门槛\n'
        '· 每一级有什么代价或风险\n'
        '· 什么限制了他的上限\n'
        '\n'
        '输出格式：\n## 来源\n## 分级\n## 门槛\n## 代价\n## 上限\n'
        '\n'
        '铁律：不许照搬别的书的分级名（不写「练气筑基金丹」这类现成套路），\n'
        '分级名由这本书的规则自己长出来。如果作者已给了名称，就用他的。\n'
    ),
    '07': (
        '你在帮一位作者想清楚主角的「别人没有的东西」。',
        '不一定是系统。可能是天赋 / 身份 / 消息渠道 / 别人不知道的记忆 / 一个愿意帮他的人。\n'
        '\n'
        '必须回答：\n'
        '· 这个东西具体能做什么、不能做什么\n'
        '· 它有什么代价或反噬\n'
        '· 别人会不会想抢\n'
        '· 它会在什么时候失效\n'
        '\n'
        '输出格式：\n## 是什么\n## 能做什么 / 不能做什么\n## 代价\n## 谁会想抢\n## 什么时候失效\n'
    ),
    '08': (
        '你在帮一位作者出几种不同的开局方案。',
        '出 3-5 种，每种说清：\n'
        '· 第一段是什么画面\n'
        '· 读者第一眼看到主角在做什么\n'
        '· 这个开头承诺了什么（读者会期待什么）\n'
        '· 它的风险（可能劝退哪类读者）\n'
        '\n'
        '输出格式：\n### 方案 1：<一句话>\n- 第一段：…\n- 承诺：…\n- 风险：…\n'
        '\n只出方案，不推荐。选哪个由作者定。\n'
    ),
    '09': (
        '你在帮一位作者做群像。',
        '必须回答：\n'
        '· 有哪些阵营/立场\n'
        '· 每个人想要什么\n'
        '· 他们之间谁和谁有旧账\n'
        '· 谁会背叛，为了什么\n'
        '\n'
        '输出格式：\n## 阵营\n## 各自要什么\n## 旧账表\n| 谁 | 和谁 | 什么旧账 |\n## 可能的背叛\n'
    ),
    '10': (
        '你在帮一位作者定文笔模板，保证全书写法一致。',
        '从作者已有正文里提取，不要凭空定：\n'
        '· 句子长度习惯（短句为主还是长句）\n'
        '· 段落长度\n'
        '· 对话密度\n'
        '· 用不用比喻、从哪取\n'
        '· 情绪怎么写（直说 / 靠动作 / 靠环境）\n'
        '\n'
        '输出格式：\n## 句长\n## 段长\n## 对话密度\n## 比喻\n## 情绪写法\n'
        '\n每条都要引用一句现有正文做证据，不许只给结论。\n'
    ),
    '11': (
        '你在帮一位写网络连载的作者做黄金三章。',
        '必须回答：\n'
        '· 第一章要给读者什么（钩子 / 身份 / 处境）\n'
        '· 第二章推进什么\n'
        '· 第三章留下什么\n'
        '· 三章之内必须出现的东西（冲突 / 目标 / 代价）\n'
        '\n'
        '输出格式：\n## 第一章\n## 第二章\n## 第三章\n## 三章必须出现的\n'
        '\n'
        '提醒：这一整套规矩是平台机制推导出来的，不是写作本身的规律。\n'
        '如果作者写的是出版/短篇/纯文学，这套不适用。\n'
    ),
    '13': (
        '你在帮一位作者给配角做专项（5 个以上有戏份的配角）。',
        '为每个人回答：\n'
        '· 表面上是什么人\n'
        '· 实际上是什么人\n'
        '· 他的专属特点（一个癖好 / 一句口头禅 / 一个习惯）\n'
        '· 他自己想要什么（和主角无关的）\n'
        '· 他藏了什么秘密\n'
        '· 他最后会怎样\n'
        '\n'
        '输出格式：每个配角一节，六条齐全。\n'
        '\n如果作者素材里只有 2-3 个配角，就只做这几个，不要硬凑到 5 个。\n'
    ),
})


def ask_step(book, sid, extra=''):
    """对一个步骤跑一次 AI 辅助，返回 {'ok','text','model'}。"""
    import coordinator as CO

    if sid not in STEP_PROMPTS:
        return {'ok': False, 'error': '未知步骤：' + str(sid)}
    role, body = STEP_PROMPTS[sid]
    ctx = _context_for(book, sid)
    user = body
    if ctx:
        if sid in ('01', '02'):
            # 发散/评估的上下文里混着"参照书"和"已写步骤"，标签要分开，
            # 否则模型会把参照书当普通背景，一路只讲通用套路（实测过）。
            user += ('\n\n---\n\n【下面是你手边的参照书与已有材料。'
                     '列「常见写法」或判断「别人写过吗」时，要点名用的是哪一本，'
                     '不要只说套路；没有拆解只有导读时，只用导读的一句话说特点。】\n' + ctx)
        else:
            user += '\n\n---\n\n作者已有的材料：\n' + ctx
    if extra and str(extra).strip():
        user += '\n\n---\n\n作者补充：\n' + str(extra).strip()

    layer = CO.resolve_layer('thinking') or {}
    model = layer.get('model') or 'deepseek-v4-pro'
    cfg = {'model': model, 'temperature': 0.7, 'max_tokens': int(layer.get('max_tokens') or 8000)}
    if layer.get('thinking') is True:
        cfg['extra_body'] = {'thinking': {'type': 'enabled'}}

    try:
        resp = CO.chat(cfg, [
            {'role': 'system', 'content': role},
            {'role': 'user', 'content': user},
        ])
        text = CO.sanitize_worker_text(CO._extract_content(resp) or '')
    except Exception as e:
        return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}
    if not text.strip():
        return {'ok': False, 'error': '模型没有输出'}
    return {'ok': True, 'text': text, 'model': model, 'chars': len(text)}
