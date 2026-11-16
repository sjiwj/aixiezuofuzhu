# -*- coding: utf-8 -*-
"""L3 空间一致性（qc_space）：正文里的距离/方向/脚程，跟世界地图对账

《05-质检四关》L3 四条，落到代码是四个判定：
  1 距离 vs 相对位置表      差一倍以上 high，差五成到一倍 medium
  2 方向 vs 相对位置表      反了 high，差 90 度 medium，差 45 度 low
  3 行程可行性 vs 速度表    拿最快脚程也算不出来 high
  4 地图上没有的地点被写了距离 medium

三条硬规矩（照世界地图第三节「超自然移动的处理规则」）：
  · 距离/方位写「未明/未定/待定」的，一律不报 —— 数据不足不是错
  · 正文出现「飞/御剑/瞬移/传送/被带走/白光」，标 inconclusive，
    不拿步行速度去套。修仙世界可以飞，地图没登记就交客户确认
  · 读不到地图就出一条 space_skip 说清跳过了什么，不抛异常

这一层只出 warnings，不出 blocking：空间可疑也可能是作者故意，
交审稿团判。要拦正文，把 severity 改成 critical 即可（契约按 critical 分流）。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

SEV_RANK = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}

# 八方位角度。只用来算两条描写差多少，不做天文推算
DIR_DEG = {'北': 0, '东北': 45, '东': 90, '东南': 135,
           '南': 180, '西南': 225, '西': 270, '西北': 315}
# 长词在前：先把「东北」吃掉，别让「东」抢走
DIR_RE = r'(东北|西北|东南|西南|正[东南西北]|[东南西北])'

UNDECIDED = ('未明', '未定', '待定', '不详', '未知', '暂无')

# 超自然位移。单字「飞」误命中太多（第一章「山雀骂骂咧咧飞了」），
# 只收「飞」后面带位移补语的样子；其余按词收
SUPER_RE = re.compile(r'御剑|瞬移|传送|凌空|腾空|飞遁|被带走|白光|'
                      r'飞(?:过去|过来|到|走|上天|起来|出)')

# 「一天走四十里」是速度陈述，不是地点距离。先整段挖掉，免得被当成行程
SPEED_RE = re.compile(r'(?:一天|一日|每日|每天|日行)\s*(?:能)?\s*(?:走|行|赶)?\s*'
                      r'(?:[一二三四五六七八九十百两\d]+)?\s*里')

# 正文里的距离：五里、二十里、三百里
DIST_RE = re.compile(r'([一二三四五六七八九十百千两\d]+)\s*里')
# 正文里的步数：十几步、五十步
STEP_RE = re.compile(r'([一二三四五六七八九十百两几\d]+)\s*步')

# 「往东」「朝西」：方位前面得有介词，不然「东边天上」也会被算成方向。
# 介词和方位之间可以夹一个地名尾字：「雷公地在镇东南」
DIR_AFTER = re.compile(r'(?:往|向|朝|从|在|去)\s*(?:[镇城村滩山铺]\s*)?' + DIR_RE)
# 「镇西五里」这种：镇/滩 + 方位，参照的是镇本身，不是被描述的地点
DIR_LEAD = re.compile(r'^\s*([镇城村滩山铺])\s*' + DIR_RE)

# 地名不能吃数字：「李家坳还有八十里」被贪婪切成「李家坳还有八」+「十」，
# 所以每个字都排除掉数字，让量词前面那段一定落在名字上
NAME_CH = r'(?:(?![零一二三四五六七八九十百千两\d])[\u4e00-\u9fa5])'

# 「离 X 五里」「X 五里外」「X 往东五里」——这几个句式里的 X 该是地名
UNKNOWN_PLACE_RES = (
    re.compile(r'(?:离|距|到)\s*(' + NAME_CH + r'{2,6}?)\s*(?:还有|有|只|不过)?\s*'
               r'([一二三四五六七八九十百千两\d]+)\s*里'),
    re.compile(r'(' + NAME_CH + r'{2,6}?)\s*(?:还)?(?:有|走)?\s*'
               r'([一二三四五六七八九十百千两\d]+)\s*里(?:外|之外|远)'),
    re.compile(r'(' + NAME_CH + r'{2,6}?)\s*(?:往|向|朝)' + DIR_RE +
               r'\s*(?:走|去|行)?\s*([一二三四五六七八九十百千两\d]+)\s*里'),
)

# 判断「不存在的地点」时排除的虚词/代词，跟 precheck 第 5 条同一套思路
STOP = set('的了是在和与就都也还被把没不我你他她它们这那有要会能上下中前后里外么吧呢啊着过地得')

CN_DIGIT = {'零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
            '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
CN_UNIT = {'十': 10, '百': 100, '千': 1000}

# 能当简称尾字的地名后缀：示例镇 -> 镇，示例滩 -> 滩
TAIL_OK = set('镇城村滩山铺寺庙观')

# 屋里写「十几步」时，靠这几个词认出说的是哪间铺子
SHOP_HINT = ('当铺', '铺子', '柜台', '招牌', '掌柜', '铺面')


def _read(p):
    try:
        with open(p, encoding='utf-8-sig') as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ''


def _plain(s):
    """去掉 markdown 的加粗和反引号，表格单元格里常见。"""
    return re.sub('[*\x60]', '', s or '').strip()


def _num(s):
    """中文/阿拉伯数字 -> int。「十几」按 15 估，够做量级比对。"""
    s = (s or '').strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s.startswith('十几'):
        return 15
    if s.startswith('几十'):
        return 25
    s = s.replace('两', '二')
    if s.startswith('十'):
        s = '一' + s
    tot, cur = 0, 0
    for ch in s:
        if ch in CN_DIGIT:
            cur = CN_DIGIT[ch]
        elif ch in CN_UNIT:
            tot += (cur or 1) * CN_UNIT[ch]
            cur = 0
        else:
            return None
    return tot + cur


def _cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def _tables(text):
    """把 markdown 里连续的 | 行切成表格块，返回 [(表头, [数据行])]。"""
    blocks, cur = [], []
    for line in text.split('\n'):
        s = line.strip()
        if s.startswith('|') and s.count('|') >= 2:
            cur.append(s)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    out = []
    for blk in blocks:
        rows = [_cells(x) for x in blk]
        # 分隔行 |---|---| 整行只剩 - 和 :，剔掉
        rows = [r for r in rows if not re.fullmatch(r'[\s:\-]+', ''.join(r))]
        if len(rows) >= 2:
            out.append((rows[0], rows[1:]))
    return out


def _span(raw):
    """「半日 / 一日 / 两个时辰」-> 天数。未定返回 None。"""
    s = SPEED_RE.sub('　', _plain(raw))
    if not s or any(k in s for k in UNDECIDED) or s in ('—', '-', '－'):
        return None
    for m in re.finditer(r'(半|[一二三四五六七八九十百两\d]+)?\s*个?\s*(时辰|日|天|夜|刻)', s):
        q = m.group(1)
        v = 0.5 if q == '半' else (_num(q) if q else 1)
        if v is None:
            continue
        return v * {'时辰': 1 / 12.0, '刻': 1 / 96.0}.get(m.group(2), 1.0)
    return None


def _dist(raw, extra=''):
    """解析「距离」列 -> (kind, value)。kind: li 里 / step 步 / near 镇内 / None 未定。"""
    s = _plain(raw)
    t = s + ' ' + _plain(extra)
    if not s or s in ('—', '-', '－') or any(k in s for k in UNDECIDED):
        # 距离格写「未明」，但方位格可能写着「走十几步」，那是个能用的近距
        m = re.search(r'([一二三四五六七八九十百两几\d]+)\s*步', t)
        if m:
            v = _num(m.group(1))
            if v:
                return ('step', float(v))
        return (None, None)
    if '镇内' in s or '城里' in s:
        return ('near', 0.0)
    m = re.search(r'([一二三四五六七八九十百千两\d]+)\s*里', s)
    if m:
        v = _num(m.group(1))
        if v is not None:
            return ('li', float(v))
    m = re.search(r'([一二三四五六七八九十百两几\d]+)\s*步', s)
    if m:
        v = _num(m.group(1))
        if v is not None:
            return ('step', float(v))
    return (None, None)


def _dir(raw, names):
    """解析方位列 -> 八方位之一。先抠掉地名，「镇东柴房」的「东」不算方位。"""
    s = _plain(raw)
    for n in sorted(names, key=len, reverse=True):
        s = s.replace(n, '　')
    if any(k in s for k in UNDECIDED):
        return None
    m = re.search(DIR_RE, s)
    return m.group(1).lstrip('正') if m else None


def _load_places(map_text):
    """相对位置表：地点 / 相对方位 / 距离 / 地形 / 备注。"""
    places = {}
    for head, rows in _tables(map_text):
        h = [_plain(c) for c in head]
        if '地点' not in h or not any('方位' in c for c in h):
            continue
        i_name = h.index('地点')
        i_dir = next(i for i, c in enumerate(h) if '方位' in c)
        i_dist = next((i for i, c in enumerate(h) if '距离' in c), None)
        for r in rows:
            if len(r) <= max(i_name, i_dir):
                continue
            nm = _plain(r[i_name])
            if not nm or nm == '地点':
                continue
            places[nm] = {
                'name': nm,
                'raw_dir': _plain(r[i_dir]),
                'raw_dist': _plain(r[i_dist]) if i_dist is not None and i_dist < len(r) else '',
            }
        break
    names = set(places)
    for p in places.values():
        p['dir'] = _dir(p['raw_dir'], names)
        p['dist'] = _dist(p['raw_dist'], p['raw_dir'])
    return places


def _load_speeds(map_text):
    """交通方式表：方式 / 速度（X里/日）/ 条件 / 备注。解析不出速度的（待定）留 None。"""
    speeds = {}
    for head, rows in _tables(map_text):
        h = [_plain(c) for c in head]
        if '方式' not in h or not any('速度' in c for c in h):
            continue
        i_n = h.index('方式')
        i_v = next(i for i, c in enumerate(h) if '速度' in c)
        for r in rows:
            if len(r) <= max(i_n, i_v):
                continue
            nm = _plain(r[i_n])
            v = _plain(r[i_v])
            if not nm or nm == '方式':
                continue
            m = re.search(r'([一二三四五六七八九十百千两\d]+)\s*里\s*/\s*日', v)
            sp = float(_num(m.group(1))) if m else None
            # 「只能坚持半日」的，日里程要打折，不然拿满勤速度去判人
            if sp and '半日' in ' '.join(r):
                sp = sp / 2.0
            speeds[nm] = sp
        break
    return speeds


def _aliases(places):
    """正文里的简称：镇 -> 示例镇，滩 -> 示例滩，当铺/铺子 -> <书名>。"""
    out = {}
    for name in places:
        if len(name) < 2:
            continue
        # 单字简称只收镇/滩这类独占的；「铺」太泛（苏家药铺也是铺），
        # 只认两字「当铺」和「铺子」
        if name[-1] in TAIL_OK and name[-1] != '铺':
            out.setdefault(name[-1], name)
        out.setdefault(name[-2:], name)
        if name[-1] == '铺':
            out.setdefault('铺子', name)
    return out


def _mentions(win, places, aliases):
    """窗口里出现的地名 -> [(位置, 全名)]，按位置排序。简称不认全名内部的字。"""
    hits = []
    for name in places:
        for m in re.finditer(re.escape(name), win):
            hits.append((m.start(), name))
    for alias, full in aliases.items():
        for m in re.finditer(re.escape(alias), win):
            # 「示例镇」里的那个「镇」不算简称，否则满篇都是示例镇
            if any(h[0] <= m.start() < h[0] + len(h[1]) for h in hits):
                continue
            hits.append((m.start(), full))
    hits.sort()
    return hits


def _sentences(text):
    """粗切句：句末标点或换行都断。返回 [(起点, 句子)]。"""
    out = []
    for m in re.finditer(r'[^。！？…\n]+[。！？…]?', text):
        if m.group(0).strip():
            out.append((m.start(), m.group(0)))
    return out


def _window(sents, i, limit=260):
    """第 i 句连同前面两句，拼成回看窗口。距离从句尾往前找主体用。"""
    return '　'.join(sents[j][1] for j in range(max(0, i - 2), i + 1))[-limit:]


def _lead_ref(sent):
    """句首「镇西」这种：返回 (参照的简称, 方位)。参照不是被描述的地点。"""
    m = DIR_LEAD.match(sent)
    if not m:
        return (None, None)
    return (m.group(1), m.group(2).lstrip('正'))


# 地名后面紧跟方位，说明它是参照物：「镇东南」「示例镇西北」
DIR_TAIL = re.compile(r'\s*' + DIR_RE)


def _ref_names(sent, places, aliases):
    """句子里当参照物的地名。

    「镇西五里」「雷公地在镇东南」里的那个镇是坐标系原点，不是被描述的对象；
    不剔掉就会被当成主体，而镇本身没有距离/方位，整条检查就哑了。
    """
    out = set()
    for m in re.finditer(r'[镇城村滩山铺]', sent):
        if DIR_TAIL.match(sent, m.end()):
            full = aliases.get(m.group(0))
            if full:
                out.add(full)
    for name in places:
        for m in re.finditer(re.escape(name), sent):
            if DIR_TAIL.match(sent, m.end()):
                out.add(name)
    return out


def _subject(win, sent, places, aliases, drops=None):
    """这句距离/方向说的是哪个地方：先看本句，本句没有就往回找最近提到的。"""
    hits = _mentions(sent, places, aliases)
    if drops:
        hits = [h for h in hits if h[1] not in drops]
    if not hits:
        hits = _mentions(win, places, aliases)
        if drops:
            hits = [h for h in hits if h[1] not in drops]
    return hits[-1][1] if hits else None


def _dir_in(sent, names):
    """本句里带介词的方位。"""
    s = sent
    for n in sorted(names, key=len, reverse=True):
        s = s.replace(n, '　')
    m = DIR_AFTER.search(s)
    return m.group(1).lstrip('正') if m else None


def _dist_sev(kind, val, doc, is_step):
    """距离比对 -> severity 或 None（对得上 / 数据不足）。"""
    if kind is None or val is None:
        return None
    if kind == 'near':                      # 地图写「镇内」
        return 'medium' if doc > 3 else None
    if kind == 'step':
        if is_step:
            return None if val * 0.5 <= doc <= val * 2 else ('medium' if doc < val * 5 else 'high')
        return None if doc <= 1 else 'medium'
    if is_step:                             # 地图按里、正文按步：尺度不同，不硬套
        return None
    if not val:
        return None
    r = doc / val
    if 0.67 <= r <= 1.5:                    # 取整/四舍五入的余量
        return None
    if 0.5 <= r < 0.67 or 1.5 < r <= 2:
        return 'medium'
    return 'high'


def _dir_sev(mine, theirs):
    if not mine or not theirs:
        return None
    d = abs(DIR_DEG[mine] - DIR_DEG[theirs]) % 360
    d = min(d, 360 - d)
    if d == 0:
        return None
    if d <= 45:
        return 'low'                        # 相邻方位，可能是口语习惯
    if d <= 90:
        return 'medium'
    return 'high'


def _in_speed(m, sent):
    """这个「X里」落在速度短语里吗？落在就不是地点距离。"""
    for s in SPEED_RE.finditer(sent):
        if s.start() <= m.start() < s.end():
            return True
    return False


def _supernatural(win):
    return SUPER_RE.search(win) is not None


def _add(bucket, typ, sev, subj, detail, win):
    """超自然位移一律降成 inconclusive；同一地点同一类只留最重的一条。"""
    if _supernatural(win):
        typ, sev = 'space_inconclusive', 'low'
        detail += '；附近有未登记的移动方式，不按脚程判，需客户确认'
    key = (typ, subj)
    old = bucket.get(key)
    if old is None or SEV_RANK.get(sev, 1) > SEV_RANK.get(old['severity'], 1):
        bucket[key] = {'type': typ, 'severity': sev, 'detail': detail}


def _clip(s, n=42):
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s if len(s) <= n else s[:n] + '…'


def check(book, chapter, text=None):
    '''book: 书名 str；chapter: 章号 str（'001'）；text: 正文，None 则自己从
       项目根/章节/ 下按前缀找文件。
       返回 {'blocking': [...], 'warnings': [...]}
       每条 issue = {'type': str, 'severity': ..., 'detail': str}
    '''
    ch = str(chapter).zfill(3)
    bucket = {}

    map_text = _read(os.path.join(CO.projects_root(), book, '设定库', '世界地图.md'))
    if not map_text:
        return {'blocking': [], 'warnings': [
            {'type': 'space_skip', 'severity': 'low',
             'detail': '没有 设定库/世界地图.md，L3 空间检查整章跳过'}]}

    places = _load_places(map_text)
    if not places:
        return {'blocking': [], 'warnings': [
            {'type': 'space_skip', 'severity': 'low',
             'detail': '世界地图.md 里找不到「地点/相对方位/距离」表，L3 空间检查跳过'}]}

    speeds = _load_speeds(map_text)
    fastest = max([v for v in speeds.values() if v] or [0])
    aliases = _aliases(places)
    names = set(places)

    if text is None:
        d = os.path.join(CO.projects_root(), book, '章节')
        for f in (sorted(os.listdir(d)) if os.path.isdir(d) else []):
            if f.startswith(ch) and f.endswith('.md'):
                text = _read(os.path.join(d, f))
                break
    text = text or ''

    sents = _sentences(text)
    for i, (pos, sent) in enumerate(sents):
        win = _window(sents, i)
        ref, lead_dir = _lead_ref(sent)
        drops = _ref_names(sent, places, aliases)
        if ref and aliases.get(ref):
            drops.add(aliases[ref])
        subj = _subject(win, sent, places, aliases, drops)

        # 1 距离 vs 地图表
        for m in DIST_RE.finditer(sent):
            if _in_speed(m, sent):
                continue
            doc = _num(m.group(1))
            if doc is None:
                continue
            info = places.get(subj or '')
            sev = _dist_sev(*(info['dist'] if info else (None, None)), doc, False)
            if sev:
                kind, val = info['dist']
                _add(bucket, 'space_distance', sev, subj,
                     '「%s」正文写 %d 里（%s），地图是 %g 里（%s %s）' % (
                         subj, doc, _clip(sent), val, info['raw_dir'], info['raw_dist']),
                     win)
            # 3 行程可行性：同一句/下一句给了时长，就拿速度表算
            span = _span(sent)
            if span is None and i + 1 < len(sents):
                span = _span(sents[i + 1][1])
            if fastest and span:
                need = doc / span
                if need > fastest * 1.5:
                    _add(bucket, 'space_infeasible', 'high', subj,
                         '%d 里要在 %.2g 天走完，得 %.0f 里/日，全书最快只有 %.0f 里/日（%s）'
                         % (doc, span, need, fastest, _clip(sent)), win)

        # 1b 步数：屋前院后那种短距离
        for m in STEP_RE.finditer(sent):
            doc = _num(m.group(1))
            if doc is None:
                continue
            who = subj
            if who is None and '几' in m.group(1):
                # 只有「十几步」这种模糊量才当成距离描写。
                # 「走了两步」是动作不是里程，不能拿它去对地图上的步数。
                # 回看要够长：进门那段铺垫可能隔了七八句
                back = text[max(0, pos - 240):pos]
                if any(h in back for h in SHOP_HINT):
                    who = next((n for n in places if '铺' in n), None)
            info = places.get(who or '')
            if not info:
                continue
            sev = _dist_sev(info['dist'][0], info['dist'][1], doc, True)
            if sev:
                _add(bucket, 'space_distance', sev, who,
                     '「%s」正文写 %d 步（%s），地图是 %s' % (
                         who, doc, _clip(sent), info['raw_dist']), win)

        # 2 方向 vs 坐标表
        doc_dir = lead_dir or _dir_in(sent, names)
        info = places.get(subj or '')
        if doc_dir and info and info['dir']:
            sev = _dir_sev(doc_dir, info['dir'])
            if sev:
                _add(bucket, 'space_direction', sev, subj,
                     '「%s」正文往%s（%s），地图是%s %s' % (
                         subj, doc_dir, _clip(sent), info['raw_dir'], info['dir']), win)

        # 4 地图上没有的地点被写了距离
        for rx in UNKNOWN_PLACE_RES:
            for m in rx.finditer(sent):
                cand = _plain(m.group(1))
                if len(cand) < 2 or cand in places or cand in aliases:
                    continue
                if any(c in STOP for c in cand):
                    continue
                if any(cand in n or n in cand for n in names):
                    continue
                _add(bucket, 'space_unknown_place', 'medium', cand,
                     '「%s」写了 %s 里，但地图上没有这个地点（%s）' % (
                         cand, m.group(m.lastindex), _clip(sent)), win)

    issues = sorted(bucket.values(), key=lambda x: -SEV_RANK.get(x['severity'], 1))
    return {'blocking': [x for x in issues if x['severity'] == 'critical'],
            'warnings': [x for x in issues if x['severity'] != 'critical']}
