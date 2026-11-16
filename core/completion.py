# -*- coding: utf-8 -*-
"""完结可行性 —— 把「这篇会不会崩」算成一个数字

核心洞察（见 docs/product/研讨结论-差异化突围.md 洞察 1）：
    每一次埋伏笔、立承诺，都是向读者借注意力。
    崩 = 存量承诺超过剩余章节的偿还能力（期限错配）；太监 = 违约；烂尾 = 削发。

本模块只回答一个问题：
    剩下的章节，够不够把这些账还完？不够的话，最少砍几条？

设计约束（硬）：**不要求作者重新填表**。全部输入都来自已有数据 ——
    设定库/承诺/P-*.md   front matter（强度 / 状态 / 可推进卷 / 兑付期限 / 最后推进章）+ 履历
    章节/*.md            已写章数、最大章号、缺号
    大纲/*.md            卷起止（→ 承诺的兑付截止章）、计划章数

单位统一在「强度点」上，避免条数与强度混算：
    M    未偿存量   = Σ 强度点（状态「进行」的承诺）
    k    历史速率   = Σ 强度点(已兑付) / 已写章数          [强度点/章]
    cpp  章/点      = 1 / k（有历史）；= COST_FACTOR（无历史）
    N'   需要章数   = M × cpp
    N    剩余章数   = 计划章数 - 已写章数

除零边界（真实数据就会踩到）：
    k = 0 表示「一章都没兑付」，不是「还款速度无穷慢」。
    M / k 不能算 → 退化成成本模型：每条承诺的兑付成本 c = 强度点 × COST_FACTOR，
    保守 N' = Σc（一条一条还），乐观 N'_min = max(c)（可并行还），
    结果一律标 estimated=True，不当历史实测报。

命令行入口见 scripts/completion_feasibility.py。
"""
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import promises  # noqa: E402  同目录账本模块，复用项目根与 front matter 解析

# ── 强度数值化 ───────────────────────────────────────────────────────────
# 高 = 3：读者期待强，欠着就是硬伤，必须兑付
# 中 = 2：可兑付，也可降级为「读者记得有这么回事」的半兑付
# 低 = 1：可以降级为背景，砍掉读者几乎不会察觉
STRENGTH_POINTS = {'高': 3, '中': 2, '低': 1}
DEFAULT_STRENGTH = '中'          # 强度字段缺失/写错时的兜底（标 estimated）

# 系数：1 点强度 = 3 章兑付成本。取 3 的三个锚点全部来自本项目已有常量：
#   1) core/promises.py DEBT_THRESHOLD = 10：「强度高 + 超 10 章没推进」判为节奏债
#      → 高的成本 3 点 × 3 = 9 章，刚好压在阈值下面 1 章（留推进余量）
#   2) 产品说明书：「伏笔埋超 5 章会提醒」→ 中 2 点 × 3 = 6 章，略高于提醒线
#   3) 黄金三章 → 低 1 点 × 3 = 3 章，最弱的一条承诺最多占掉开篇三章的量
COST_FACTOR = 3.0

CN_DIGIT = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

VOL_RE = re.compile(r'(卷[一二三四五六七八九十]+)[^\n（(]*[（(]\s*(\d{2,4})\s*[–\-—~−]\s*(\d{2,4})\s*[）)]')
PLAN_RE = re.compile(r'共\s*约?\s*(\d+)\s*章')
HIST_RE = re.compile(r'^\s*[-*]\s*(\d{3})\s*[：:]')
PURE_NUM_RE = re.compile(r'^\d{3,4}$')


def _as_list(v):
    """front matter 里可能是 list，也可能是 '卷三,卷四' 这样的字符串"""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v or '').strip()
    if not s:
        return []
    return [x.strip() for x in re.split(r'[,，、;；]', s) if x.strip()]


def vol_index(name):
    """卷一 → 1，卷七 → 7；认不出返回 None"""
    m = re.match(r'卷([一二三四五六七八九十]+)', str(name or ''))
    if not m:
        return None
    s = m.group(1)
    if s == '十':
        return 10
    if s.startswith('十'):
        return 10 + CN_DIGIT.get(s[1], 0)
    if '十' in s:
        a, b = s.split('十', 1)
        return CN_DIGIT.get(a, 0) * 10 + CN_DIGIT.get(b, 0)
    return CN_DIGIT.get(s)


def strength_of(p):
    """→ (强度名, 点数, 是否兜底)"""
    s = str(p.get('强度') or '').strip()
    if s in STRENGTH_POINTS:
        return s, STRENGTH_POINTS[s], False
    return DEFAULT_STRENGTH, STRENGTH_POINTS[DEFAULT_STRENGTH], True


def weight_of(p):
    """承诺的「权重」→ 点数；没写/写坏返回 None（调用方回退到强度映射）

    口径照 OpenWrite 的 ForeshadowingNode.weight（1-10 连续），替代 高/中/低 三档。
    只在 front matter 真的写了「权重: 8」时才生效 —— 老书一个字都不用改。
    """
    raw = str(p.get('权重') or '').strip()
    if not raw:
        return None
    m = re.search(r'\d{1,2}', raw)
    if not m:
        return None
    v = int(m.group(0))
    return v if 1 <= v <= 10 else None


def last_touch_of(p):
    """最后推进章 —— front matter 与履历取大者

    真实数据里就有不一致：P-005 的 最后推进章: 003，而履历已写到「004：推进」。
    只信 front matter 会把「最近动过」的账算成陈旧，砍单顺序就会错。
    → (采用值, front matter 值, 履历最大值)
    """
    front = promises.to_int(p.get('最后推进章'))
    hist = 0
    for line in str(p.get('_body') or '').split('\n'):
        m = HIST_RE.match(line)
        if m:
            hist = max(hist, int(m.group(1)))
    return max(front, hist), front, hist


def chapters_info(book):
    """章节/*.md —— 只要 .md（.bak- / .draft 后缀排除）"""
    d = os.path.join(promises._projects_root(), book, '章节')
    nums = []
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if not fn.endswith('.md'):
                continue
            m = re.match(r'^(\d{3})', fn)
            if m:
                nums.append(int(m.group(1)))
    nums = sorted(set(nums))
    top = max(nums) if nums else 0
    missing = [n for n in range(1, top + 1) if n not in nums]
    return {'dir': d, 'count': len(nums), 'max': top, 'missing': missing}


def outline_info(book):
    """大纲/*.md —— 卷起止 + 计划章数（作者已经写好了，不用重填）"""
    d = os.path.join(promises._projects_root(), book, '大纲')
    volumes = {}
    order = []
    planned = None
    src = None
    if not os.path.isdir(d):
        return {'dir': d, 'volumes': volumes, 'order': order, 'planned': None, 'source': None}

    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.md'):
            continue
        path = os.path.join(d, fn)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()
        except OSError:
            continue
        for line in text.split('\n'):
            m = VOL_RE.search(line)
            if m:
                name = m.group(1)
                lo, hi = int(m.group(2)), int(m.group(3))
                if name not in volumes:
                    volumes[name] = (lo, hi)
                    order.append(name)
        if planned is None:
            m = PLAN_RE.search(text)
            if m:
                planned = int(m.group(1))
                src = '大纲/%s「共约 %d 章」' % (fn, planned)
    if volumes:
        last_end = max(v[1] for v in volumes.values())
        if planned is None:
            planned = last_end
            src = '大纲卷末章（%d）' % last_end
        elif last_end > planned:
            planned = last_end
            src = (src or '') + ' + 卷末章 %d' % last_end
    return {'dir': d, 'volumes': volumes, 'order': order, 'planned': planned, 'source': src}


def deadline_of(p, outline, planned_hint=None):
    """承诺的兑付截止章 —— 兑付期限写死了就用它，否则用「可推进卷」的最后卷末章

    → (章号 or None, 来源, 认不出的卷名列表, 是否兜底)
    """
    d = str(p.get('兑付期限') or '').strip()
    if PURE_NUM_RE.match(d):
        return int(d), '兑付期限', [], False
    vols = _as_list(p.get('可推进卷'))
    ends, missing = [], []
    for v in vols:
        if v in outline['volumes']:
            ends.append(outline['volumes'][v][1])
        else:
            missing.append(v)
    if ends:
        return max(ends), '可推进卷', missing, False
    if planned_hint:
        return planned_hint, '大纲末章（兜底）', missing, True
    return None, '未知', missing, True


def analyze(book, planned=None, factor=None):
    """算一次完结可行性。返回纯数据，报告文字在 CLI 里组织。"""
    factor = COST_FACTOR if factor is None else float(factor)
    root = promises._projects_root()
    bookdir = os.path.join(root, book)
    out = {
        'book': book,
        'projects_root': root,
        'book_dir': bookdir,
        'exists': os.path.isdir(bookdir),
        'factor': factor,
        'warnings': [],
        'notes': [],
    }
    if not out['exists']:
        out['error'] = '找不到项目目录：%s' % bookdir
        return out

    ps = promises.load_all(book)
    ch = chapters_info(book)
    ol = outline_info(book)
    out['chapters'] = ch
    out['outline'] = ol

    rows = []
    for p in ps:
        st = str(p.get('状态') or '').strip() or '未知'
        name, pts, est = strength_of(p)
        w = weight_of(p)
        # 点数口径：front matter 写了 权重 就直接用（1-10），没写才回退 高3/中2/低1
        pts_source, pts_est = '强度映射', est
        if w is not None:
            pts, pts_source, pts_est = w, '权重', False
        last, front, hist = last_touch_of(p)
        dl, dl_src, missing_vols, dl_est = deadline_of(p, ol, ol['planned'])
        rows.append({
            'id': str(p.get('编号') or p.get('_file') or '?').strip(),
            'title': str(p.get('标题') or '').strip(),
            'type': str(p.get('类型') or '').strip(),
            'state': st,
            'strength': name,
            'weight': w,
            'points': pts,
            'points_source': pts_source,
            'points_estimated': pts_est,
            'strength_estimated': est,
            'last_touch': last,
            'last_front': front,
            'last_history': hist,
            'open_chapter': promises.to_int(p.get('开启章')),
            'vols': _as_list(p.get('可推进卷')),
            'deadline': dl,
            'deadline_source': dl_src,
            'deadline_estimated': dl_est,
            'deadline_missing_vols': missing_vols,
            'file': p.get('_file'),
        })
    out['promises'] = rows
    weighted = [r for r in rows if r['points_source'] == '权重']
    out['points_mode'] = '权重' if weighted else '强度映射'
    out['weighted_count'] = len(weighted)

    known_states = ('进行', '已兑付', '已弃置')
    unpaid = [r for r in rows if r['state'] == '进行']
    paid = [r for r in rows if r['state'] == '已兑付']
    voided = [r for r in rows if r['state'] == '已弃置']
    weird = [r for r in rows if r['state'] not in known_states]

    written = ch['count']
    M = sum(r['points'] for r in unpaid)
    paid_points = sum(r['points'] for r in paid)
    k_count = (len(paid) / written) if written else None
    k_points = (paid_points / written) if written else None

    # 除零边界：k = 0（或没有章节）→ 不能算 M/k
    if written == 0:
        boundary = 'no_chapters'
    elif k_points is not None and k_points > 0:
        boundary = 'history'
    else:
        boundary = 'k_zero'

    if boundary == 'history':
        cpp = 1.0 / k_points
        cpp_src = '历史速率 1/k = 1/%.4f' % k_points
    else:
        cpp = factor
        cpp_src = '成本模型 点数 × %.2f 章（无历史速率可用）' % factor

    need = M * cpp
    need_min = (max([r['points'] for r in unpaid]) * cpp) if unpaid else 0.0

    if planned is None and ol['planned']:
        planned = ol['planned']
        planned_src = ol['source'] or '大纲'
        planned_estimated = True
    elif planned is None:
        planned_src = None
        planned_estimated = False
    else:
        planned_src = '命令行 --planned'
        planned_estimated = False

    out.update({
        'written': written,
        'planned': planned,
        'planned_source': planned_src,
        'planned_estimated': planned_estimated,
        'remaining': (planned - written) if planned else None,
        'remaining_by_number': (planned - ch['max']) if planned and ch['max'] else None,
        'unpaid': unpaid,
        'paid': paid,
        'voided': voided,
        'weird': weird,
        'M': M,
        'M_by_strength': {s: sum(1 for r in unpaid if r['strength'] == s) for s in ('高', '中', '低')},
        'M_points_by_strength': {
            s: sum(r['points'] for r in unpaid if r['strength'] == s) for s in ('高', '中', '低')
        },
        'paid_points': paid_points,
        'k_count': k_count,
        'k_points': k_points,
        'boundary': boundary,
        'cpp': cpp,
        'cpp_source': cpp_src,
        'need': need,
        'need_min': need_min,
        'estimated': (boundary != 'history'),
    })

    # 预算与砍单
    cuts, M_after, allowed = [], M, None
    if out['remaining'] is not None and out['remaining'] >= 0 and cpp > 0:
        allowed = out['remaining'] / cpp
        # 砍单顺序：先砍「兑付窗口最远」的，同窗口下强度低的先砍。
        # 理由：窗口近的必须优先推进（砍了就是烂尾），窗口远的还有大把章可以还，最不急。
        order = sorted(unpaid, key=lambda r: (
            -(r['deadline'] if r['deadline'] is not None else 99999),
            r['points'],
            r['last_touch'],
            r['id']))
        for r in order:
            if M <= allowed:
                break
            cuts.append(r)
            M -= r['points']
        M_after = M
    out['allowed_points'] = allowed
    out['cuts'] = cuts
    out['M_after_cut'] = M_after
    out['need_after_cut'] = M_after * cpp

    # 判定
    if out['remaining'] is None:
        verdict = 'no_plan'
    elif out['remaining'] < 0:
        verdict = 'invalid'
    elif not unpaid:
        verdict = 'clean'
    elif need_min > out['remaining']:
        verdict = 'red_hard'
    elif need > out['remaining']:
        verdict = 'red'
    elif need > out['remaining'] * 0.8:
        verdict = 'warn'
    else:
        verdict = 'ok'
    out['verdict'] = verdict

    # 数据质量告警（不算结论，但影响可信度）
    # 口径：这次的点数是用「权重」还是「强度映射」算的，必须说出来（两种口径的数字不可直接比）
    if weighted:
        out['warnings'].append(
            '口径: 权重 —— %d/%d 条承诺写了 front matter「权重」（1-10），直接当点数；'
            '其余 %d 条回退「强度」映射（高3/中2/低1）'
            % (len(weighted), len(rows), len(rows) - len(weighted)))
    else:
        out['warnings'].append('口径: 强度映射 —— 没有承诺写「权重」字段，按 高3/中2/低1 折算')
    if boundary == 'k_zero':
        out['warnings'].append(
            'k = 0：已写 %d 章、已兑付 0 条 → 历史速率不可用，改用成本模型（结果标 [估算]）' % written)
    if boundary == 'no_chapters':
        out['warnings'].append('还没有章节（已写 0 章）→ 历史速率无从谈起，整份报告为 [估算]')
    if ch['missing']:
        out['warnings'].append(
            '章号不连续：已写 %d 章但最大章号 %03d，缺 %s'
            % (written, ch['max'], '、'.join('%03d' % n for n in ch['missing'])))
    for r in rows:
        if r['last_front'] != r['last_history'] and r['last_history']:
            out['warnings'].append(
                '%s %s：front matter 最后推进章 = %03d，履历已到 %03d（本报告按 %03d 算）'
                % (r['id'], r['title'], r['last_front'], r['last_history'], r['last_touch']))
        if r['strength_estimated']:
            out['warnings'].append('%s %s：强度字段缺失或不是 高/中/低，按「%s」估算'
                                   % (r['id'], r['title'], DEFAULT_STRENGTH))
        if r['deadline_missing_vols']:
            out['warnings'].append(
                '%s %s：可推进卷里的 %s 在大纲中找不到（大纲只有 %s）'
                % (r['id'], r['title'], '、'.join(r['deadline_missing_vols']),
                   '、'.join(ol['order']) or '无'))
    overdue = [r for r in unpaid
               if r['deadline'] is not None and r['deadline'] <= (ch['max'] or 0)]
    out['overdue'] = overdue
    for r in overdue:
        out['warnings'].append('%s %s：兑付窗口到 ch%03d，当前已到 ch%03d —— 已过期'
                               % (r['id'], r['title'], r['deadline'], ch['max']))
    return out


def report(r):
    """人看的报告文本（CLI 与自检共用）"""
    L = []

    def pad(s, width):
        s = str(s)
        w = sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)
        return s + ' ' * max(0, width - w)

    if not r.get('exists'):
        return (r.get('error') or '项目不存在') + '\n'

    tag = '  [估算]' if r['estimated'] else ''
    L.append('=== 完结可行性 ·《%s》===' % r['book'])
    L.append('项目目录  %s' % r['book_dir'])
    ch = r['chapters']
    if ch['count']:
        L.append('已写      %d 章（章号 001-%03d%s）' % (
            ch['count'], ch['max'],
            '，缺 ' + '、'.join('%03d' % n for n in ch['missing']) if ch['missing'] else ''))
    else:
        L.append('已写      0 章（章节目录为空或不存在）')
    if r['planned']:
        L.append('计划      %d 章%s' % (r['planned'], '  [来自 %s]' % r['planned_source']))
        L.append('剩余 N    %d 章  = %d - %d%s' % (
            r['remaining'], r['planned'], r['written'],
            '' if r['remaining_by_number'] in (None, r['remaining'])
            else '（按章号口径 %d）' % r['remaining_by_number']))
    else:
        L.append('计划      未指定（大纲里也没找到「共约 N 章」）→ 只算存量，不做 N\' vs N')
    L.append('')

    # 1 债务
    weight_mode = r.get('points_mode') == '权重'
    unit_word = '权重点' if weight_mode else '强度点'
    L.append('-- 1. 当前债务 --')
    L.append('  点数口径  %s' % ('权重（front matter 1-10）' if weight_mode
                                 else '强度映射（高3/中2/低1）'))
    L.append('  未偿（进行）  %d 条 = %d %s' % (len(r['unpaid']), r['M'], unit_word))
    for s in ('高', '中', '低'):
        n, pts = r['M_by_strength'][s], r['M_points_by_strength'][s]
        if weight_mode:
            L.append('    %s %d 条 = %d 点（按各自权重）' % (s, n, pts))
        else:
            L.append('    %s %d 点/条 × %d 条 = %d 点' % (s, STRENGTH_POINTS[s], n, pts))
    L.append('  已兑付 %d 条（%d 点）   已弃置 %d 条   状态异常 %d 条'
             % (len(r['paid']), r['paid_points'], len(r['voided']), len(r['weird'])))
    L.append('  明细：')
    for p in sorted(r['unpaid'], key=lambda x: x['id']):
        dl = ('ch%03d' % p['deadline']) if p['deadline'] else '未知'
        extra = ''
        if p['deadline_missing_vols']:
            extra = '（%s 不在大纲）' % '、'.join(p['deadline_missing_vols'])
        elif p['deadline_estimated']:
            extra = '（兜底）'
        wt = '（权重）' if p.get('points_source') == '权重' else ''
        L.append('    %s %s %s %d点%s 最后推进 ch%03d 兑付窗口 → %s%s'
                 % (pad(p['id'], 7), pad(p['title'], 16), p['strength'], p['points'], wt,
                    p['last_touch'], dl + extra, tag if p['strength_estimated'] else ''))
    L.append('')

    # 2 速率
    L.append('-- 2. 历史偿还速率 --')
    kc = 'n/a' if r['k_count'] is None else '%.3f' % r['k_count']
    kp = 'n/a' if r['k_points'] is None else '%.3f' % r['k_points']
    L.append('  已兑付 %d 条 / 已写 %d 章 → k = %s 条/章（%s口径 %s 点/章）'
             % (len(r['paid']), r['written'], kc, unit_word, kp))
    if r['boundary'] == 'k_zero':
        L.append('  ⚠ 除零边界：k = 0 是「一章都还没兑付」，不是「还款速度无穷慢」。')
        L.append('    处理：不算 M / k，改用成本模型（每条承诺兑付成本 = %s × %.2f 章），'
                 % (unit_word, r['factor']))
        L.append('    结果标 [估算]；作者兑付第一条之后重跑，这一节会自动切回历史速率。')
    elif r['boundary'] == 'no_chapters':
        L.append('  ⚠ 已写 0 章 → 没有可用的历史速率，本节整份为 [估算]。')
    else:
        L.append('  换算  cpp = 1 / k = %.3f 章/%s（%s）'
                 % (r['cpp'], unit_word, r['cpp_source']))
    L.append('')

    # 3 N' vs N
    L.append('-- 3. 需要章数 vs 剩余章数 --')
    L.append('  保守 N\'  = %d 点 × %.3f 章/点 = %.1f 章%s' % (r['M'], r['cpp'], r['need'], tag))
    if r['unpaid']:
        L.append('  乐观下界  = %d 章（最贵一条 %d 点，假定可并行兑付）'
                 % (round(r['need_min']), max(p['points'] for p in r['unpaid'])))
    if r['remaining'] is not None:
        L.append('  剩余 N    = %d 章' % r['remaining'])
        L.append('  余量      = %d 章（N - N\'）%s'
                 % (r['remaining'] - round(r['need']),
                    '' if r['remaining'] - r['need'] >= 0 else '（负数=还不完）'))
    else:
        L.append('  剩余 N    = 未知（缺计划章数）')
    L.append('')

    # 4 重组
    L.append('-- 4. 重组建议 --')
    if r['remaining'] is None:
        L.append('  缺计划章数 → 没有预算，判断不了要不要砍。用 --planned N 指定后再跑。')
        L.append('')
    elif r['remaining'] < 0:
        L.append('  计划章数小于已写章数（%d < %d），先修输入，本节不做重组。'
                 % (r['planned'], r['written']))
        L.append('')
    elif not r['cuts']:
        L.append('  不需要砍：存量 %d 点，预算 %.2f 点（= 剩余 %d 章 ÷ %.3f 章/点），余 %.2f 点 = %.0f 章'
                 % (r['M'], r['allowed_points'], r['remaining'], r['cpp'],
                    r['allowed_points'] - r['M'],
                    (r['allowed_points'] - r['M']) * r['cpp']))
        L.append('')
    else:
        L.append('  预算：剩余 %d 章 ÷ %.3f 章/点 = 最多留 %.2f %s，现有 %d 点，超 %.2f 点'
                 % (r['remaining'], r['cpp'], r['allowed_points'], unit_word, r['M'],
                    r['M'] - r['allowed_points']))
        L.append('  按「兑付窗口最远 → 强度低 → 推进章早」排序，砍到够为止（先保近期到期的）：')
        acc = r['M']
        for i, p in enumerate(r['cuts'], 1):
            L.append('    %d. %s %s %s %d点 最后推进 ch%03d  → 砍（剩 %d 点）'
                     % (i, pad(p['id'], 7), pad(p['title'], 16), p['strength'],
                        p['points'], p['last_touch'], acc - p['points']))
            acc -= p['points']
        L.append('  砍 %d 条后：剩 %d 条 = %d %s → 需要 %.1f 章 vs 剩余 %d 章 %s'
                 % (len(r['cuts']), len(r['unpaid']) - len(r['cuts']), r['M_after_cut'],
                    unit_word, r['need_after_cut'], r['remaining'],
                    '✓ 够' if r['need_after_cut'] <= r['remaining']
                    else '✗ 仍不够，只能加计划章数'))
        L.append('')
    # 5 结论
    L.append('-- 5. 结论 --')
    v = r['verdict']
    if v == 'ok':
        L.append('  ✅ 宽裕：还完现有存量需要 %.0f 章，剩 %d 章，量级安全。'
                 % (r['need'], r['remaining']))
    elif v == 'warn':
        L.append('  ⚠ 偏紧：需要 %.0f 章 / 剩 %d 章（占用 > 80%%），再加三条新伏笔就会翻红。'
                 % (r['need'], r['remaining']))
    elif v == 'red':
        L.append('  ❌ 红灯：需要 %.0f 章 > 剩 %d 章，必须砍 %d 条。'
                 % (r['need'], r['remaining'], len(r['cuts'])))
    elif v == 'red_hard':
        L.append('  ❌ 硬红灯：连最贵的一条都要 %.0f 章 > 剩 %d 章 —— 不是重组问题，是计划章数不够。'
                 % (r['need_min'], r['remaining']))
    elif v == 'clean':
        L.append('  ✅ 没有未偿承诺，不欠账。')
    elif v == 'no_plan':
        L.append('  ○ 缺计划章数：只能给出存量 %.0f 章的成本估算，无法判断够不够。'
                 % r['need'])
    else:
        L.append('  ❌ 输入有误：计划 %s 章 < 已写 %d 章。' % (r['planned'], r['written']))
    if r['overdue']:
        L.append('  ⏰ 已过期 %d 条：%s' % (len(r['overdue']),
                                        '、'.join(p['id'] for p in r['overdue'])))
    if r['warnings']:
        L.append('')
        L.append('-- 数据质量 --')
        for w in r['warnings']:
            L.append('  · ' + w)
    return '\n'.join(L) + '\n'
