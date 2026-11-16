# -*- coding: utf-8 -*-
"""L3 空间一致性 / L4 时间-距离-物候一致性

用法:
    python l3_l4_check.py <章节文件> [--map config/map.json]
                          [--rules config/qc_rules.json] [--json [输出路径]] [--strict]

检查项:
    L3  - 两地距离 vs 地图坐标（原有逻辑，行为不变）
        - 路线表 routes：文中「往X走N里」是否与 map.json 的 from/to/direction/distance 一致
    L4  - 速度表：天数 + 距离 推每日行程，超出配置区间报错
        - 物候：同一段落内出现互斥季节词（默认 夏:蝉 / 冬:雪）报错
所有阈值来自 config/qc_rules.json，脚本内不写死。

退出码:
    0  正常（未加 --strict 时恒为 0，兼容旧调用）
    1  --strict 且存在 error 级问题
"""
import re, sys, json, os, hashlib, time

def _candidate_roots():
    """配置根候选，按优先级：NOVELAPP_ROOT > frozen 时 sys.executable 目录 > 源码 __file__ 上两级。"""
    roots = []
    env = os.environ.get('NOVELAPP_ROOT')
    if env:
        roots.append(os.path.abspath(env))
    if getattr(sys, 'frozen', False):
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        roots.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return roots


def _base_dir():
    """第一个含 config/ 的候选根；都不含则退回候选首位（保持旧行为不崩）。"""
    roots = _candidate_roots()
    for r in roots:
        if os.path.isdir(os.path.join(r, 'config')):
            return r
    return roots[0]


BASE = _base_dir()
DEFAULT_MAP = os.path.join('config', 'map.json')
DEFAULT_RULES = os.path.join('config', 'qc_rules.json')

CN = {'零': 0, '一': 1, '二': 2, '两': 2, '半': 0.5, '三': 3, '四': 4, '五': 5,
      '六': 6, '七': 7, '八': 8, '九': 9}
UNIT = {'十': 10, '百': 100, '千': 1000, '万': 10000}
OPPOSITE = {'东': '西', '西': '东', '南': '北', '北': '南'}
NUM_CHARS = '0-9零一二两三四五六七八九十百千万'

# 配置缺失时的兜底（与 config/qc_rules.json 默认值一致）
DEFAULT_RULES_DATA = {
    "l3": {"unit": "里", "distance_tolerance_ratio": 0.2, "distance_tolerance_min": 2,
           "route_tolerance_ratio": 0.15, "route_tolerance_min": 2, "route_context_chars": 36},
    "l4": {"day_tolerance_ratio": 0.2, "min_days_for_check": 1, "default_mode": "步行",
           "speeds": {"步行": {"min_per_day": 40, "max_per_day": 60, "keywords": ["步行", "走"]},
                      "骑马": {"min_per_day": 100, "max_per_day": 150, "keywords": ["骑马", "马"]}}},
    "season": {"window": "paragraph", "window_lines": 6,
               "groups": {"夏": ["蝉", "蛙", "荷", "暑"], "冬": ["雪", "冰", "霜", "冻"]},
               "conflicts": [["夏", "冬"]]},
}


# ---------------------------------------------------------------- 基础工具
def cn2num(s):
    """中文数字转阿拉伯，支持 三百 / 十五 / 两千 / 一万二千 / 半"""
    if not s:
        return None
    if str(s).isdigit():
        return int(s)
    total, section, num = 0, 0, 0
    for ch in s:
        if ch in CN:
            num = CN[ch]
        elif ch in UNIT:
            u = UNIT[ch]
            if u == 10000:
                section = (section + (num or 1)) * u
                total += section
                section, num = 0, 0
            else:
                section += (num if num else 1) * u
                num = 0
        else:
            return None
    return total + section + num


def load_rules(path):
    rules = json.loads(json.dumps(DEFAULT_RULES_DATA))  # 深拷贝兜底
    if path and not os.path.exists(path):
        sys.stderr.write('[warn] 配置不存在，使用内置兜底: %s\n' % path)
    if path and os.path.exists(path):
        # utf-8-sig：兼容带/不带 BOM（记事本、PowerShell 5.1 另存都会加 BOM）
        try:
            with open(path, encoding='utf-8-sig') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            sys.stderr.write('[warn] 配置解析失败（%s），使用内置兜底: %s\n' % (e, path))
            return rules
        for section, val in data.items():
            if isinstance(val, dict) and isinstance(rules.get(section), dict):
                rules[section].update(val)
            else:
                rules[section] = val
    return rules


def load_map(path):
    """返回 (unit, places, routes)。routes 可缺省（旧地图无 routes 时为空列表）。"""
    with open(path, encoding='utf-8-sig') as f:
        d = json.load(f)
    places = {p['name']: p for p in d['places']}
    routes = []
    for r in d.get('routes', []):
        if not all(k in r for k in ('from', 'to', 'direction', 'distance')):
            continue
        routes.append({'from': r['from'], 'to': r['to'], 'direction': r['direction'],
                       'distance': r['distance'], 'mode': r.get('mode', ''),
                       'note': r.get('note', '')})
    return d.get('unit', '里'), places, routes


def dist(a, b):
    return ((a['x'] - b['x']) ** 2 + (a['y'] - b['y']) ** 2) ** 0.5


def direction(a, b):
    dx, dy = b['x'] - a['x'], b['y'] - a['y']
    if abs(dx) >= abs(dy):
        return '东' if dx > 0 else ('西' if dx < 0 else '-')
    return '北' if dy > 0 else '南'


def _line_of(text, pos):
    return text.count('\n', 0, pos) + 1


def iter_paragraphs(text):
    """按空行分段，产出 (起始行号, 段落文本)"""
    start, buf, line = 1, [], 1
    for ln in text.split('\n'):
        if ln.strip() == '':
            if buf:
                yield start, '\n'.join(buf)
            buf, start = [], line + 1
        else:
            if not buf:
                start = line
            buf.append(ln)
        line += 1
    if buf:
        yield start, '\n'.join(buf)


def iter_sentences(text):
    """按 。！？；换行 切句，产出 (起始行号, 句子)"""
    start = 0
    for m in re.finditer(r'[。！？；\n]', text):
        seg = text[start:m.start()]
        if seg.strip():
            yield _line_of(text, start), seg
        start = m.end()
    tail = text[start:]
    if tail.strip():
        yield _line_of(text, start), tail


# ---------------------------------------------------------------- L3 抽取
def extract_distance_mentions(text):
    """找出所有『数字+里』的表述，带上上下文"""
    out = []
    for m in re.finditer(r'([' + NUM_CHARS + r']{1,6})\s*里', text):
        raw = m.group(1)
        val = cn2num(raw)
        if val is None:
            continue
        line = _line_of(text, m.start())
        ctx = text[max(0, m.start() - 25): m.end() + 15].replace('\n', ' ')
        out.append({'raw': raw, 'value': val, 'line': line, 'context': ctx,
                    'start': m.start(), 'end': m.end()})
    return out


def extract_direction_mentions(text):
    out = []
    for m in re.finditer(r'(?:往|向|朝)?([东西南北])(?:边|面|方)?', text):
        line = _line_of(text, m.start())
        ctx = text[max(0, m.start() - 20): m.end() + 12].replace('\n', ' ')
        out.append({'dir': m.group(1), 'line': line, 'context': ctx})
    return out


# ---------------------------------------------------------------- L3 路线表
def check_routes(text, places, routes, mentions, unit, cfg):
    """路线表检查：文中距离/方向表述 vs map.json 的 routes。

    返回 (issues, claimed)；claimed 是已被路线表结论覆盖的 (行号, 距离值)，
    用于避免与通用距离检查对同一处重复报警。
    """
    issues, claimed = [], set()
    if not routes:
        return issues, claimed
    win = int(cfg.get('route_context_chars', 36))
    ratio = float(cfg.get('route_tolerance_ratio', 0.15))
    min_tol = float(cfg.get('route_tolerance_min', 2))

    for m in mentions:
        v = m['value']
        ctx = text[max(0, m['start'] - win): m['end'] + win]
        near = [n for n in places if n in ctx]
        if not near:
            continue
        # 文中同时出现两地时，必须有这对地点的路线才判定；只有一地时允许按单端路线判定
        if len(near) >= 2:
            pairs = set()
            for i, a in enumerate(near):
                for b in near[i + 1:]:
                    pairs.add(frozenset((a, b)))
            cands = [r for r in routes if frozenset((r['from'], r['to'])) in pairs]
        else:
            cands = [r for r in routes if r['from'] in near or r['to'] in near]
        if not cands:
            continue
        dm = re.search(r'(?:往|向|朝)([东西南北])', ctx)
        stated_dir = dm.group(1) if dm else None

        # 每条路线有两种走法；按「距离是否对 / 走向是否对 / 两端是否都在文中 / 相对误差」排序
        resolved = None
        best = None  # (rank, route, origin, dest, orient_dir)
        for r in cands:
            tol = max(r['distance'] * ratio, min_tol)
            dist_ok = abs(r['distance'] - v) <= tol
            rel_err = abs(r['distance'] - v) / max(r['distance'], 1e-9)
            for origin, dest, odir in ((r['from'], r['to'], r['direction']),
                                       (r['to'], r['from'], OPPOSITE.get(r['direction'], '-'))):
                dir_ok = stated_dir is None or stated_dir == odir
                ends = int(origin in near) + int(dest in near)
                rank = (0 if dist_ok else 1, 0 if dir_ok else 1,
                        0 if ends == 2 else 1, rel_err)
                if dist_ok and dir_ok:
                    resolved = (r, origin, dest, odir)
                    break
                if best is None or rank < best[0]:
                    best = (rank, r, origin, dest, odir)
            if resolved:
                break
        if resolved:
            continue

        _, route, origin, dest, odir = best
        tol = max(route['distance'] * ratio, min_tol)
        if abs(route['distance'] - v) > tol:
            issues.append({
                'rule': 'L3-route-distance', 'severity': 'error', 'line': m['line'],
                'message': '路线表 %s→%s 为 %s%s，文中说 %s%s（差 %s%s）' % (
                    origin, dest, route['distance'], unit, m['value'], unit,
                    round(abs(route['distance'] - v), 1), unit),
                'snippet': ctx.replace('\n', ' ')[:80]})
            claimed.add((m['line'], v))
        elif stated_dir and stated_dir != odir:
            issues.append({
                'rule': 'L3-route-direction', 'severity': 'error', 'line': m['line'],
                'message': '路线表 %s→%s 走向为%s，文中说往%s' % (origin, dest, odir, stated_dir),
                'snippet': ctx.replace('\n', ' ')[:80]})
            claimed.add((m['line'], v))
    return issues, claimed


# ---------------------------------------------------------------- L3 总检查
def check(text, map_path, rules=None):
    rules = rules or load_rules(None)
    unit, places, routes = load_map(map_path)
    l3cfg = rules.get('l3', {})
    ratio = float(l3cfg.get('distance_tolerance_ratio', 0.2))
    min_tol = float(l3cfg.get('distance_tolerance_min', 2))
    issues = []

    names = list(places)
    pair_dist = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = places[names[i]], places[names[j]]
            pair_dist[frozenset([names[i], names[j]])] = round(dist(a, b), 1)

    mentions = extract_distance_mentions(text)
    route_issues, claimed = check_routes(text, places, routes, mentions, unit, l3cfg)
    issues.extend(route_issues)

    for m in mentions:
        if (m['line'], m['value']) in claimed:
            continue
        v = m['value']
        near = [n for n in names if n in m['context']]
        if len(near) >= 2:
            key = frozenset(near[:2])
            if key in pair_dist:
                real = pair_dist[key]
                if abs(real - v) > max(real * ratio, min_tol):
                    issues.append({
                        'rule': 'L3-distance-mismatch', 'severity': 'error',
                        'line': m['line'],
                        'message': "文中说 %s 与 %s 相距 %s%s，地图上是 %s%s" % (
                            near[0], near[1], v, unit, real, unit),
                        'snippet': m['context']})
        elif len(near) == 1:
            known = [d for k, d in pair_dist.items() if near[0] in k]
            if known and not any(abs(d - v) <= max(d * ratio, min_tol) for d in known):
                issues.append({
                    'rule': 'L3-distance-unknown', 'severity': 'info',
                    'line': m['line'],
                    'message': "提到 %s%s，与「%s」相关的已知距离 %s 都不匹配" % (
                        v, unit, near[0], known),
                    'snippet': m['context']})

    dirs = extract_direction_mentions(text)
    route_dir_lines = {i['line'] for i in route_issues if i['rule'] == 'L3-route-direction'}
    for d in dirs:
        if d['line'] in route_dir_lines:
            continue
        ctx_places = [n for n in names if n in d['context']]
        if len(ctx_places) >= 2:
            a, b = places[ctx_places[0]], places[ctx_places[1]]
            real = direction(a, b)
            if real != '-' and real != d['dir']:
                issues.append({
                    'rule': 'L3-direction-mismatch', 'severity': 'error',
                    'line': d['line'],
                    'message': "文中说往%s，地图上 %s→%s 是往%s" % (
                        d['dir'], ctx_places[0], ctx_places[1], real),
                    'snippet': d['context']})

    return issues, {'distances_found': len(mentions), 'directions_found': len(dirs),
                    'place_pairs': len(pair_dist), 'places': places,
                    'routes': routes, 'route_claims': len(route_issues), 'unit': unit}


# ---------------------------------------------------------------- L4 速度
def pick_mode(sentence, l4cfg):
    speeds = l4cfg.get('speeds', {})
    default_mode = l4cfg.get('default_mode', '步行')
    for mode, cfg in speeds.items():
        if mode == default_mode:
            continue
        for kw in cfg.get('keywords', []):
            if kw and kw in sentence:
                return mode
    return default_mode


def extract_day_mentions(sentence):
    out = []
    for m in re.finditer(r'([' + NUM_CHARS + r']{1,6})\s*(?:天|日)(?:的)?(?:路程|路|行程|工夫|功夫)?', sentence):
        val = cn2num(m.group(1))
        if val is None or val <= 0:
            continue
        out.append({'raw': m.group(1), 'value': val, 'span': m.span()})
    return out


def extract_distance_in(sentence):
    out = []
    for m in re.finditer(r'([' + NUM_CHARS + r']{1,6})\s*里', sentence):
        val = cn2num(m.group(1))
        if val is None or val <= 0:
            continue
        out.append({'raw': m.group(1), 'value': val, 'span': m.span()})
    return out


def check_speed(text, unit, l4cfg):
    """句内「X天 + Y里」推每日行程，超出速度表区间报错。"""
    issues, found = [], 0
    ratio = float(l4cfg.get('day_tolerance_ratio', 0.2))
    min_days = float(l4cfg.get('min_days_for_check', 1))
    speeds = l4cfg.get('speeds', {})

    for line, sentence in iter_sentences(text):
        days = extract_day_mentions(sentence)
        dists = extract_distance_in(sentence)
        if not days or not dists:
            continue
        found += 1
        d = days[0]
        s = dists[0]
        if d['value'] < min_days:
            continue
        mode = pick_mode(sentence, l4cfg)
        cfg = speeds.get(mode, {})
        lo = float(cfg.get('min_per_day', 0))
        hi = float(cfg.get('max_per_day', 10 ** 9))
        per_day = s['value'] / d['value']
        if per_day < lo * (1 - ratio) or per_day > hi * (1 + ratio):
            need_lo = s['value'] / hi if hi else 0
            need_hi = s['value'] / lo if lo else 0
            issues.append({
                'rule': 'L4-speed-mismatch', 'severity': 'error', 'line': line,
                'message': "%s天走%s%s = %.1f%s/天，%s合理 %s-%s%s/天；按 %s%s 应走 %.1f-%.1f 天" % (
                    d['raw'], s['raw'], unit, per_day, unit, mode,
                    int(lo), int(hi), unit, s['raw'], unit, need_lo, need_hi),
                'snippet': sentence[:80]})
    return issues, found


# ---------------------------------------------------------------- L4 物候
WINDOW_LABEL = {'paragraph': '同一段落内', 'adjacent': '相邻段落内', 'lines': '行窗口内'}


def iter_season_windows(text, mode, window_lines):
    """产出 [(段落起始行, 段落文本), ...] 组成的判定窗口。

    paragraph: 每段一个窗口（同段才比较，最严格，跨段矛盾查不到）
    adjacent : 段落 i 与 i+1 组成一个窗口，步长 1 段（默认，覆盖跨段矛盾）
    lines    : 每 window_lines 行组成一个窗口，步长 1 行（兜底/兜不住时用）
    """
    paras = list(iter_paragraphs(text))
    if mode == 'lines':
        lines = text.split('\n')
        for i in range(len(lines)):
            chunk = lines[i:i + window_lines]
            if any(x.strip() for x in chunk):
                yield [(i + 1, '\n'.join(chunk))]
        return
    if mode == 'adjacent':
        for i, para in enumerate(paras):
            group = [para]
            if i + 1 < len(paras):
                group.append(paras[i + 1])
            yield group
        return
    for para in paras:
        yield [para]


def check_season(text, scfg):
    groups = scfg.get('groups', {})
    conflicts = scfg.get('conflicts', [])
    window = scfg.get('window', 'adjacent')
    if window not in WINDOW_LABEL:
        window = 'adjacent'
    wl = int(scfg.get('window_lines', 3))
    issues, windows = [], 0
    seen = set()

    # 统计用：全文命中的季节词（去重，不受滑动窗口重复计数影响）
    hit_words = {g: [w for w in words if w in text] for g, words in groups.items()}
    hits_total = sum(len(v) for v in hit_words.values())

    for group in iter_season_windows(text, window, wl):
        windows += 1
        found = {}
        for pline, ptext in group:
            for g, words in groups.items():
                for w in words:
                    idx = ptext.find(w)
                    if idx >= 0:
                        ln = pline + ptext[:idx].count('\n')
                        found.setdefault(g, []).append((ln, w))
        for a, b in conflicts:
            if a not in found or b not in found:
                continue
            la, lb = found[a][0][0], found[b][0][0]
            key = (la, lb, a, b)
            if key in seen:          # 滑动窗口会对同一对矛盾重复命中，只报一次
                continue
            seen.add(key)
            snippet = ' / '.join(ptext for _, ptext in group if a in ptext or b in ptext)
            issues.append({
                'rule': 'L4-season-conflict', 'severity': 'error',
                'line': max(la, lb),
                'message': "%s物候矛盾：%s（%s，行 %s）与 %s（%s，行 %s）" % (
                    WINDOW_LABEL[window], a, '、'.join(w for _, w in found[a][:3]), la,
                    b, '、'.join(w for _, w in found[b][:3]), lb),
                'snippet': snippet.replace('\n', ' ')[:80]})
    return issues, {'season_windows': windows, 'season_hits': hits_total,
                    'season_window_mode': window}


# ---------------------------------------------------------------- 输出
# ---------------------------------------------------------------- 闸 3 三维（物品 / 能力 / 伏笔）
def _book_dir_of(chapter_path):
    """章节文件所在书的根目录：<书>/章节/x.md -> <书>"""
    d = os.path.dirname(os.path.abspath(chapter_path))
    return os.path.dirname(d) if os.path.basename(d) == "章节" else d


def _read_text(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return ""


def _table_rows(text):
    """markdown 表格 -> 表头映射的行字典列表（跳过 --- 分隔行）。"""
    rows, head = [], None
    for ln in text.split("\n"):
        st = ln.strip()
        if not st.startswith("|"):
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells if c):
            continue
        if head is None:
            head = cells
            continue
        rows.append({head[i]: cells[i] for i in range(min(len(head), len(cells)))})
    return rows


def check_items(text, book_dir):
    """物品一致性：状态表记在身上的东西，正文说丢了/没了/留在某处 -> 要人工确认。"""
    st = _read_text(os.path.join(book_dir, "设定库", "角色状态.md"))
    if not st:
        return [], {"items_checked": 0}
    items = set()
    for ln in st.split("\n"):
        if "身上物品" not in ln:
            continue
        val = ln.split("：", 1)[-1] if "：" in ln else ln.split(":", 1)[-1]
        for tok in re.split(r"[、，,；;（）()]", val):
            tok = tok.strip().strip("*").strip()
            if 2 <= len(tok) <= 10 and not re.search(r"[0-9A-Za-z]", tok):
                items.add(tok)
    if not items:
        return [], {"items_checked": 0}
    lost = re.compile(r"(丢了|没了|不见了|找不到|只剩|落在|留在|忘在)")
    issues = []
    seen = set()
    for line_no, para in iter_paragraphs(text):
        m = lost.search(para)
        if not m:
            continue
        for it in items:
            if it in para and it not in seen:
                seen.add(it)
                issues.append({"rule": "item_vs_state", "severity": "warn", "line": line_no,
                               "message": "「%s」与状态表可能不一致：正文出现「%s」" % (it, m.group(1)),
                               "snippet": para[:80]})
    return issues, {"items_checked": len(items)}


def check_power(text, book_dir):
    """能力/境界：正文出现的境界词必须在 力量体系.md 的清单里。"""
    pw = _read_text(os.path.join(book_dir, "设定库", "力量体系.md"))
    if not pw:
        return [], {"realms": 0}
    known, order = [], []
    for r in _table_rows(pw):
        name = (r.get("境界") or "").strip()
        if name and not name.startswith("（"):
            known.append(name)
            order.append(name)
    if not known:
        return [], {"realms": 0}
    issues = []
    pat = re.compile(r"(练气[一二三四五六七八九十]+层|筑基[一二三四五六七八九十]*|金丹|元婴|化神|渡劫)")
    seen = set()
    for m in pat.finditer(text):
        w = m.group(1)
        if w in seen:
            continue
        if w not in known:
            seen.add(w)
            issues.append({"rule": "realm_unknown", "severity": "info", "line": _line_of(text, m.start()),
                           "message": "境界「%s」不在 力量体系.md 里（已有：%s）" % (w, "、".join(known[:8]))})
    return issues, {"realms": len(known), "realm_words": len(seen)}


# ---------------------------------------------------------------- 伏笔表（8 列 · 兼容旧 5 列）
# 列：编号 | 埋在哪章 | 内容 | 状态 | 权重 | 层级 | 回收目标 | 建议
#   权重      1-10 的整数：主线 7-9 / 支线 4-6 / 彩蛋 1-3
#   层级      主线 / 支线 / 彩蛋
#   回收目标  三级任意组合：arc_002 / sec_003 / ch_015；
#             写表内另一个伏笔编号（如 F02）= 依赖边（F01 要等 F02 先收）
#   状态      悬着 / 待收 / 已收 / 作废（待收 = 即将回收，区别于「悬着」）
#
# 向后兼容（老表必须还能跑）：老表只有「编号|埋在哪章|内容|状态|建议」。
#   读不到 权重/层级/回收目标 时用默认值（5 / 支线 / 空），不报错、不收紧旧口径——
#   陈旧阈值仍只由 config/qc_rules.json 的 gate3.foreshadow_stale_after 决定。
#   新列只做加法：彩蛋不催陈旧、待收要查回收章、回收目标要查悬空引用。
FORESHADOW_DEFAULT_WEIGHT = 5
FORESHADOW_DEFAULT_LAYER = "支线"
FORESHADOW_LAYERS = ("主线", "支线", "彩蛋")
FS_STATUS_OPEN = ("悬着", "未收", "待收")
FS_STATUS_CLOSED = ("已收", "已回收", "已兑付")
FS_STATUS_VOID = ("作废", "已作废", "放弃", "丢弃", "drop", "abandoned")
FS_TARGET_RE = re.compile(r"^(arc|sec|ch)_(\d{1,4})$", re.I)
FS_TARGET_SPLIT_RE = re.compile(r"[/／,，、;；\s]+")
FS_ID_LIKE_RE = re.compile(r"^[A-Za-z]{1,4}-?\d{1,4}$")


def _norm_target_token(tok):
    """回收目标里的一个片段：去括号注释、去 # 注释、去 markdown 装饰。"""
    t = str(tok or "").strip().strip("*")
    t = re.sub(r"[（(][^）)]*[）)]", "", t)
    t = re.sub(r"[#＃].*$", "", t)
    return t.strip()


def parse_foreshadow_target(raw, ids):
    """回收目标单元格 -> (refs 依赖, residue 回收点, dangling 悬空编号, unknown 认不出的片段)

    refs     指向表里另一个伏笔编号（依赖边）
    residue  [(级别, 序号)]，级别 = ch / arc / sec
    dangling 长得像伏笔编号、但表里没有（悬空依赖）
    unknown  其余（「待定」「卷七」这类，不是合法回收点）
    """
    refs, residue, dangling, unknown = [], [], [], []
    by_upper = {str(i).strip().upper(): str(i).strip() for i in ids}
    for tok in FS_TARGET_SPLIT_RE.split(str(raw or "")):
        t = _norm_target_token(tok)
        if not t:
            continue
        if t.upper() in by_upper:
            refs.append(by_upper[t.upper()])
            continue
        m = FS_TARGET_RE.match(t)
        if m:
            residue.append((m.group(1).lower(), int(m.group(2))))
            continue
        if FS_ID_LIKE_RE.match(t):
            dangling.append(t)
        else:
            unknown.append(t)
    return refs, residue, dangling, unknown


def load_foreshadow(book_dir):
    """读 设定库/伏笔.md -> (nodes, meta)。

    每张表单独取表头（旧实现对全书只取第一张表的表头，会把「已收」表和它的表头行
    错并进未收表，统计虚高）。只保留表头含「编号」且含「状态」或「内容」的表。
    """
    path = os.path.join(book_dir, "设定库", "伏笔.md")
    text = _read_text(path)
    meta = {"path": path, "exists": bool(text), "columns": [], "legacy": True,
            "has_weight": False, "has_layer": False, "has_target": False}
    if not text:
        return [], meta

    raw, header, is_fs, line_no = [], None, False, 0
    for ln in text.split("\n"):
        line_no += 1
        st = ln.strip()
        if not st.startswith("|"):
            header, is_fs = None, False
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells if c):
            continue
        if header is None:
            header = cells
            is_fs = ("编号" in header) and ("状态" in header or "内容" in header)
            if is_fs:
                meta["columns"] = list(header)
                meta["has_weight"] = "权重" in header
                meta["has_layer"] = "层级" in header
                meta["has_target"] = "回收目标" in header
                meta["legacy"] = not (meta["has_weight"] or meta["has_layer"] or meta["has_target"])
            continue
        if not is_fs:
            continue
        row = {header[i]: cells[i] for i in range(min(len(header), len(cells)))}
        # 老 5 列行落在 8 列表头下：它的第 5 格是「建议」，不是「权重」。
        # （core/update_ledgers.py 自动登记新伏笔时还在写 5 列行，这里兜一层，别把建议当权重读）
        if len(cells) == 5 and len(header) > 5 and not re.search(r"\d", str(row.get("权重") or "")):
            row["建议"] = row.pop("权重", "")
            row["权重"] = ""
        pid = str(row.get("编号") or "").strip()
        if not pid or pid == "编号" or pid.startswith("（") or pid.startswith("("):
            continue
        raw.append((pid, row, line_no))

    nodes = []
    for pid, row, ln in raw:
        wraw = str(row.get("权重") or "").strip()
        weight, weight_default, weight_invalid = FORESHADOW_DEFAULT_WEIGHT, True, False
        if wraw:
            wm = re.search(r"\d{1,2}", wraw)
            if wm and 1 <= int(wm.group(0)) <= 10:
                weight, weight_default = int(wm.group(0)), False
            else:
                weight_invalid = True
        lraw = str(row.get("层级") or "").strip()
        layer, layer_default, layer_invalid = FORESHADOW_DEFAULT_LAYER, True, False
        if lraw:
            if lraw in FORESHADOW_LAYERS:
                layer, layer_default = lraw, False
            else:
                layer_invalid = True
        bm = re.search(r"(\d{1,4})", str(row.get("埋在哪章") or ""))
        nodes.append({
            "id": pid,
            "buried": int(bm.group(1)) if bm else 0,
            "content": str(row.get("内容") or "").strip(),
            "status": str(row.get("状态") or "").strip(),
            "weight": weight, "weight_raw": wraw,
            "weight_default": weight_default, "weight_invalid": weight_invalid,
            "layer": layer, "layer_raw": lraw,
            "layer_default": layer_default, "layer_invalid": layer_invalid,
            "target_raw": str(row.get("回收目标") or "").strip(),
            "advice": str(row.get("建议") or "").strip(),
            "line": ln,
        })

    ids = [n["id"] for n in nodes]
    for n in nodes:
        n["refs"], n["residue"], n["dangling"], n["unknown_targets"] = \
            parse_foreshadow_target(n["target_raw"], ids)
        n["chapters"] = [no for lvl, no in n["residue"] if lvl == "ch"]
    return nodes, meta


def check_foreshadow(text, chapter_path, stale_after=5):
    """伏笔：本章触及哪些、哪些埋太久没动、哪些「待收」已经到期。

    老 5 列表没有 权重/层级/回收目标 -> 全部取默认值，判定与改造前逐条一致
    （陈旧判定还是 (本章 - 埋在哪章) >= stale_after，不分层级）。
    新表才有这些加判：彩蛋不催陈旧、待收查 ch_NNN、回收目标查悬空引用。
    """
    book_dir = _book_dir_of(chapter_path)
    nodes, meta = load_foreshadow(book_dir)
    if not nodes:
        return [], {"foreshadow": 0, "foreshadow_legacy": True}
    m = re.search(r"(\d{1,4})", os.path.basename(chapter_path))
    ch_no = int(m.group(1)) if m else 0

    touched, stale = [], []
    overdue, due_now, unreachable, dangling, bad_fields = [], [], [], [], []
    abandoned = waiting = debt = 0
    by_layer = {k: 0 for k in FORESHADOW_LAYERS}

    for n in nodes:
        status = n["status"]
        if status in FS_STATUS_VOID:
            abandoned += 1
            continue
        if status in FS_STATUS_CLOSED:
            continue
        if status and status not in FS_STATUS_OPEN:
            continue                      # 认不出的状态：与改造前一致，静默跳过
        by_layer[n["layer"]] = by_layer.get(n["layer"], 0) + 1
        if n["layer"] != "彩蛋":
            debt += n["weight"]           # 彩蛋不进债务：可以不收
        if n["weight_invalid"]:
            bad_fields.append("%s 权重「%s」不是 1-10 的整数，按 %d 算"
                              % (n["id"], n["weight_raw"], FORESHADOW_DEFAULT_WEIGHT))
        if n["layer_invalid"]:
            bad_fields.append("%s 层级「%s」不是 %s 之一，按「%s」算"
                              % (n["id"], n["layer_raw"], "/".join(FORESHADOW_LAYERS),
                                 FORESHADOW_DEFAULT_LAYER))
        for tok in n["dangling"]:
            dangling.append((n["id"], tok))

        if status == "待收":
            waiting += 1
            if n["chapters"]:
                tgt = min(n["chapters"])
                if ch_no > tgt:
                    overdue.append((n["id"], tgt))
                elif ch_no == tgt:
                    due_now.append(n["id"])
            else:
                unreachable.append(n["id"])

        keys = [w for w in re.findall(r"[\u4e00-\u9fa5]{2,4}", n["content"])][:8]
        if any(w in text for w in keys):
            touched.append(n)
            continue
        if n["layer"] == "彩蛋":
            continue                      # 彩蛋埋着不催（新列才有的放宽）
        if n["buried"] and ch_no and (ch_no - n["buried"]) >= stale_after:
            stale.append((n["id"], n["buried"]))

    issues = []
    if touched:
        if meta["legacy"]:
            msg = "本章触及伏笔：%s" % "、".join(n["id"] for n in touched)
        else:
            msg = "本章触及伏笔：%s" % "、".join(
                "%s（%s/%d）" % (n["id"], n["layer"], n["weight"]) for n in touched)
        issues.append({"rule": "foreshadow_touched", "severity": "info", "message": msg})
    for pid, buried in stale:
        issues.append({"rule": "foreshadow_stale", "severity": "warn",
                       "message": "伏笔 %s 埋在第 %d 章，已 %d 章没动" % (pid, buried, ch_no - buried)})
    for pid, tgt in overdue:
        issues.append({"rule": "foreshadow_overdue", "severity": "warn",
                       "message": "伏笔 %s 标了「待收」，回收目标 ch%03d 已过（当前第 %d 章）"
                                  % (pid, tgt, ch_no)})
    for pid in due_now:
        issues.append({"rule": "foreshadow_due_now", "severity": "info",
                       "message": "伏笔 %s 的回收目标就是本章（ch%03d），这一章该收"
                                  % (pid, ch_no)})
    for pid in unreachable:
        issues.append({"rule": "foreshadow_unreachable", "severity": "info",
                       "message": "伏笔 %s 标了「待收」但没有 ch_NNN 回收目标（DAG 会判不可达）" % pid})
    for pid, tok in dangling:
        issues.append({"rule": "foreshadow_dangling", "severity": "warn",
                       "message": "伏笔 %s 的回收目标「%s」在伏笔表里找不到（悬空依赖）" % (pid, tok)})
    for msg in bad_fields:
        issues.append({"rule": "foreshadow_field", "severity": "info", "message": msg})

    return issues, {
        "foreshadow": len(nodes),
        "foreshadow_touched": len(touched),
        "foreshadow_stale": len(stale),
        "foreshadow_abandoned": abandoned,
        "foreshadow_waiting": waiting,
        "foreshadow_by_layer": by_layer,
        "foreshadow_debt": debt,
        "foreshadow_legacy": bool(meta["legacy"]),
        "foreshadow_columns": meta["columns"],
    }


def check_gate3(text, chapter_path, cfg=None):
    """闸 3 三维统一入口：物品 / 能力 / 伏笔。数据来自本书 设定库/。"""
    book_dir = _book_dir_of(chapter_path)
    i1, s1 = check_items(text, book_dir)
    i2, s2 = check_power(text, book_dir)
    g3cfg = (cfg or {}).get("gate3") or {}
    i3, s3 = check_foreshadow(text, chapter_path, int(g3cfg.get("foreshadow_stale_after", 5) or 5))
    stats = {}
    stats.update(s1)
    stats.update(s2)
    stats.update(s3)
    return i1 + i2 + i3, stats

def resolve_path(p, default_rel):
    p = p or default_rel
    if os.path.isabs(p) or os.path.exists(p):
        return p
    alt = os.path.join(BASE, p)
    return alt if os.path.exists(alt) else p


# ---------------------------------------------------------------- 判定 / 覆盖 / 缓存
# OpenWrite P0 两条：
#   ① 没检查的规则不能算 pass —— 覆盖不全时 verdict=inconclusive
#   ② 正文 sha256 变了，旧质检结果作废 —— stale=true，并保留上一版 revision 供比对
VERDICT_PASS, VERDICT_FAIL, VERDICT_INCONCLUSIVE = 'pass', 'fail', 'inconclusive'
CACHE_VERSION = 1


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def coverage_of(checks):
    checked = [r for r, s, _ in checks if s == 'checked']
    skipped = [{'rule': r, 'reason': why} for r, s, why in checks if s == 'skipped']
    return {'checked': len(checked), 'skipped': len(skipped), 'total': len(checks),
            'checked_rules': checked, 'skipped_rules': skipped}


def decide_verdict(issues, coverage):
    if any((i.get('severity') or '').lower() == 'error' for i in issues):
        return VERDICT_FAIL
    if coverage['skipped'] > 0:
        return VERDICT_INCONCLUSIVE
    return VERDICT_PASS


def resolve_cache_path(chapter_path, explicit=None, disabled=False):
    if disabled:
        return None
    if explicit:
        return os.path.abspath(explicit)
    return os.path.abspath(os.path.join(os.path.dirname(chapter_path), '..', 'reports', '.qc-cache.json'))


def cache_read(path):
    if not path:
        return {}
    try:
        with open(path, encoding='utf-8-sig') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def cache_lookup(cache, key, revision):
    ent = (cache.get('entries') or {}).get(key)
    if not isinstance(ent, dict):
        return None
    ent = dict(ent)
    stored = str(ent.get('source_revision') or '').replace('sha256:', '')
    ent['stale'] = stored != revision
    return ent


def cache_write(path, key, entry):
    if not path:
        return
    data = cache_read(path)
    data['version'] = data.get('version') or CACHE_VERSION
    entries = data.get('entries')
    if not isinstance(entries, dict):
        entries = {}
    entries[key] = entry
    data['entries'] = entries
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        tmp = path + '.tmp~'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        sys.stderr.write('[warn] 质检缓存写入失败: %s\n' % e)


def verdict_line(verdict, coverage):
    if verdict == VERDICT_PASS:
        return '判定: pass（%d 项全查）' % coverage['total']
    if verdict == VERDICT_FAIL:
        return '判定: fail（存在 error 级问题）'
    names = '、'.join(x['rule'] for x in coverage['skipped_rules'][:5])
    tail = '' if coverage['skipped'] <= 5 else ' 等 %d 项' % coverage['skipped']
    return '判定: inconclusive（%d/%d 项未覆盖：%s%s）' % (
        coverage['skipped'], coverage['total'], names, tail)


def coverage_l3_l4(l3_stats, days_found, season_stats, rules, g3_stats=None):
    """L3/L4 七条规则的「能不能判」：缺地图/缺表述/缺配置 -> skipped。"""
    places = l3_stats.get('places') or {}
    routes = l3_stats.get('routes') or []
    dists = l3_stats.get('distances_found', 0)
    dirs = l3_stats.get('directions_found', 0)
    l4 = rules.get('l4', {}) or {}
    speeds = l4.get('speeds') or {}
    season = rules.get('season', {}) or {}
    groups = season.get('groups') or {}
    conflicts = season.get('conflicts') or []
    windows = season_stats.get('season_windows', 0)
    checks = []

    if len(places) < 2:
        checks.append(('L3-distance-mismatch', 'skipped', '地图少于 2 个地点，距离无从比对'))
        checks.append(('L3-distance-unknown', 'skipped', '地图少于 2 个地点'))
    elif dists == 0:
        checks.append(('L3-distance-mismatch', 'skipped', '正文没有「N里」距离表述'))
        checks.append(('L3-distance-unknown', 'skipped', '正文没有「N里」距离表述'))
    else:
        checks.append(('L3-distance-mismatch', 'checked', ''))
        checks.append(('L3-distance-unknown', 'checked', ''))

    if len(places) < 2 or dirs == 0:
        checks.append(('L3-direction-mismatch', 'skipped', '地图不足 2 地点或正文无方向表述'))
    else:
        checks.append(('L3-direction-mismatch', 'checked', ''))

    if not routes:
        checks.append(('L3-route-distance', 'skipped', '地图没有 routes 路线表'))
        checks.append(('L3-route-direction', 'skipped', '地图没有 routes 路线表'))
    else:
        checks.append(('L3-route-distance', 'checked', ''))
        checks.append(('L3-route-direction', 'checked', ''))

    if not speeds:
        checks.append(('L4-speed-mismatch', 'skipped', '未配置速度表 l4.speeds'))
    elif days_found == 0:
        checks.append(('L4-speed-mismatch', 'skipped', '正文没有「X天 + Y里」组合'))
    else:
        checks.append(('L4-speed-mismatch', 'checked', ''))

    if not groups or not conflicts:
        checks.append(('L4-season-conflict', 'skipped', '未配置物候词表或冲突组'))
    elif windows == 0:
        checks.append(('L4-season-conflict', 'skipped', '正文为空，无物候窗口'))
    else:
        checks.append(('L4-season-conflict', 'checked', ''))
    g3 = g3_stats or {}
    if not g3.get("items_checked"):
        checks.append(("L3-items", "skipped", "书里没有 设定库/角色状态.md 或没写「身上物品」"))
    else:
        checks.append(("L3-items", "checked", ""))
    if not g3.get("realms"):
        checks.append(("L3-power", "skipped", "书里没有 设定库/力量体系.md 或表格为空"))
    else:
        checks.append(("L3-power", "checked", ""))
    if not g3.get("foreshadow"):
        checks.append(("L3-foreshadow", "skipped", "书里没有 设定库/伏笔.md 或表格为空"))
    else:
        checks.append(("L3-foreshadow", "checked", ""))
    return coverage_of(checks)

def print_block(title, issues, stats_fn, unit):
    print('=' * 66)
    print(title)
    print('=' * 66)
    stats_fn()
    print('-' * 66)
    if not issues:
        print('✅ 未发现矛盾')
    else:
        for i in issues:
            icon = '❌' if i['severity'] == 'error' else 'ℹ️ '
            print("%s %-22s [行 %s]  %s" % (icon, i['rule'], i['line'], i['message']))
            if i.get('snippet'):
                print("        → %s" % i['snippet'][:70])
        print('-' * 66)


def normalize_issues(issues):
    """统一 issues 结构（与 l1_l2_check.py 完全一致）。"""
    return [{"rule": i.get("rule"), "severity": i.get("severity"), "line": i.get("line"),
             "message": i.get("message"), "snippet": i.get("snippet")} for i in issues]


def human_report(path, rules_path, map_path, rules, l3_stats, unit,
                 l3_issues, l4_issues, season_issues, days_found, season_stats):
    print('LLM 质检 L3/L4  %s' % os.path.basename(path))
    print('规则: %s' % os.path.abspath(rules_path))
    print('地图: %s' % os.path.abspath(map_path))
    print()

    def l3_head():
        print("地点 %s 个   路线 %s 条   文中距离表述 %s 处   方向表述 %s 处" % (
            len(l3_stats['places']), len(l3_stats['routes']),
            l3_stats['distances_found'], l3_stats['directions_found']))

    def l4_head():
        speeds = rules.get('l4', {}).get('speeds', {})
        table = ' · '.join('%s %s-%s%s/天' % (m, int(c.get('min_per_day', 0)),
                                              int(c.get('max_per_day', 0)), unit)
                           for m, c in speeds.items())
        print('速度表 %s' % (table or '未配置'))
        print("时间-距离表述 %s 处   物候窗口 %s 个（%s）   季节词命中 %s 处" % (
            days_found, season_stats['season_windows'],
            season_stats.get('season_window_mode', '?'), season_stats['season_hits']))

    print_block('L3 空间检查', l3_issues, l3_head, unit)
    print()
    print_block('L4 时间/物候检查', l4_issues + season_issues, l4_head, unit)
    print()

    print('地图上的已知地点：')
    for n, p in l3_stats['places'].items():
        print("  %-6s (%5s, %4s)  %s" % (n, p['x'], p['y'], p.get('note', '')))
    if l3_stats['routes']:
        print()
        print('路线表：')
        for r in l3_stats['routes']:
            print("  %-6s → %-6s  %s  %s%s  %s" % (
                r['from'], r['to'], r['direction'], r['distance'], unit, r.get('note', '')))
    else:
        print()
        print('路线表：地图未定义 routes 字段（跳过路线检查）')


def main():
    args = sys.argv[1:]
    if not args:
        print('用法: python l3_l4_check.py <章节文件> [--map config/map.json] '
              '[--rules config/qc_rules.json] [--json [路径]] [--strict]')
        return 0
    path = args[0]
    map_path = resolve_path(args[args.index('--map') + 1] if '--map' in args else None, DEFAULT_MAP)
    rules_path = resolve_path(args[args.index('--rules') + 1] if '--rules' in args else None, DEFAULT_RULES)
    want_json = '--json' in args
    strict = '--strict' in args
    use_cache = '--use-cache' in args
    no_cache = '--no-cache' in args
    cache_arg = (args[args.index('--cache') + 1]
                 if '--cache' in args and args.index('--cache') + 1 < len(args) else None)
    json_path = None
    if want_json:
        idx = args.index('--json')
        if idx + 1 < len(args) and not args[idx + 1].startswith('--'):
            json_path = args[idx + 1]

    rules = load_rules(rules_path)
    text = open(path, encoding='utf-8-sig').read()

    revision = sha256_file(path)
    cache_path = resolve_cache_path(path, cache_arg, no_cache)
    cache_key = 'l3_l4:' + os.path.abspath(path)
    prev = cache_lookup(cache_read(cache_path), cache_key, revision)
    stale = bool(prev and prev.get('stale'))

    if use_cache and prev and not stale and isinstance(prev.get('issues'), list):
        coverage = prev.get('coverage') or coverage_of([])
        payload = {
            'file': path, 'stats': prev.get('stats') or {}, 'issues': prev['issues'],
            'verdict': prev.get('verdict') or VERDICT_INCONCLUSIVE,
            'source_revision': 'sha256:' + revision, 'coverage': coverage,
            'stale': False, 'reused': True,
            'cache': {'path': cache_path,
                      'previous_revision': prev.get('source_revision'),
                      'previous_verdict': prev.get('verdict'),
                      'checked_at': prev.get('checked_at')},
        }
        if want_json and json_path:
            reuse_out = os.path.abspath(json_path)
            os.makedirs(os.path.dirname(reuse_out) or '.', exist_ok=True)
            with open(reuse_out, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        if want_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(verdict_line(payload['verdict'], coverage) + '（缓存复用，正文未变）')
        return 0

    l3_issues, l3_stats = check(text, map_path, rules)
    unit = l3_stats['unit']

    l4_issues, days_found = check_speed(text, unit, rules.get('l4', {}))
    season_issues, season_stats = check_season(text, rules.get('season', {}))
    g3_issues, g3_stats = check_gate3(text, path, rules)
    all_issues = l3_issues + l4_issues + season_issues + g3_issues
    coverage = coverage_l3_l4(l3_stats, days_found, season_stats, rules, g3_stats)
    verdict = decide_verdict(all_issues, coverage)

    payload = {
        'file': path,
        'stats': {
            'l3': {k: v for k, v in l3_stats.items() if k not in ('places', 'routes')},
            'l4': {'time_distance_mentions': days_found, **season_stats},
            'gate3': g3_stats,
            'map': map_path,
            'rules': rules_path,
            'root': BASE,
        },
        'issues': normalize_issues(all_issues),
        'verdict': verdict,
        'source_revision': 'sha256:' + revision,
        'coverage': coverage,
        'stale': stale,
        'reused': False,
        'cache': {'path': cache_path,
                  'previous_revision': (prev or {}).get('source_revision'),
                  'previous_verdict': (prev or {}).get('verdict')},
    }
    cache_write(cache_path, cache_key, {
        'source_revision': 'sha256:' + revision, 'verdict': verdict,
        'coverage': {k: coverage[k] for k in ('checked', 'skipped', 'total')},
        'issues': payload['issues'], 'stats': payload['stats'],
        'checked_at': time.strftime('%Y-%m-%d %H:%M:%S')})

    if want_json:
        if json_path:
            out = os.path.abspath(json_path)
            os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(verdict_line(verdict, coverage))
        if stale:
            print('⚠️  正文已变更：上一版结果作废（%s -> %s）' % (
                (prev or {}).get('source_revision'), 'sha256:' + revision))
        human_report(path, rules_path, map_path, rules, l3_stats, unit,
                     l3_issues, l4_issues, season_issues, days_found, season_stats)

    errors = [i for i in all_issues if i['severity'] == 'error']
    return 1 if (strict and errors) else 0


if __name__ == '__main__':
    sys.exit(main())
