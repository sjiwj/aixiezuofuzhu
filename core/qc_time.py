# -*- coding: utf-8 -*-
"""L4 时间一致性（qc_time）：季节冲突 / 时长 vs 距离 / 时间跳跃 / 时间倒流

规范：docs/架构-通用版/05-质检四关.md「L4 · 时间一致性」。
数据全从项目里的 md 读，缺表就跳过并说明，不抛异常：
  设定库/世界地图.md   二、交通方式与速度（里/日）
  设定库/时间线.md     主线时间轴（章 | 故事内时间 | 地点 | 关键事件 | 距上一章）

四条：
  1 季节冲突   蝉叫（夏）与露水/霜（秋）落在同一场景   medium
  2 时长vs距离 三百里配半天，最快脚程也走不到          high
  3 时间跳跃   上一章夜里，本章开头早上且无过渡词       medium
  4 时间倒流   本章故事内时间早于上一章                high

本模块不产出 critical：时间线表常是作者还没更新，判死会误拦发布。
blocking 按契约只收 critical，所以恒为空，其余全进 warnings。

用法：
  python core/qc_time.py --book <书名> --chapter 003
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

# 同一个场景的窗口（字）。季节词必须挨得够近才算「同一天」。
# 第一章「蝉」在第 27 行、「下雪」在第 83 行，隔一千多字，那是泛说一年四季，不算冲突。
SCENE_WINDOW = 250

# 季节词。只收指向明确的写法：
# 「露」不能单收——第一章「日头还没露头」会被当成露水。
SEASON_WORDS = {
    '夏': ('蝉', '知了', '蛙鸣', '蛙叫', '荷花', '酷暑', '暑气', '夏'),
    '秋': ('露水', '露珠', '白露', '霜', '落叶', '秋风', '秋'),
    '冬': ('雪', '冰', '寒冬', '入冬', '冬'),
    '春': ('桃花', '柳芽', '柳絮', '燕子', '春'),
}

# 只判真正互斥的搭配。霜和雪可以同处冬天，春与冬可能是倒春寒，都不判。
SEASON_CLASH = (('夏', '秋'), ('夏', '冬'), ('春', '秋'))

NIGHT = ('半夜', '深夜', '三更', '夜半', '入夜', '天黑', '夜里', '夜色', '掌灯', '吹灯', '睡下')
MORNING = ('早上', '清早', '清晨', '一早', '晨', '天亮', '天明', '日出', '晨光', '天光', '鸡叫', '鸡鸣')
# 过渡词：规范允许「次日」「天亮」这类交代，出现就算过关。
TRANSITION = ('次日', '翌日', '第二天', '隔天', '隔日', '过了一夜', '一夜过去',
              '一夜没睡', '睡到', '醒来时', '天亮', '天明', '到了早上', '转天')

# 故事内时段排序。长的先匹配，否则「半夜」会被「夜」吃掉。
SLOT = (('半夜', 6), ('深夜', 6), ('子时', 6), ('后半晌', 3), ('下午', 3), ('晌午', 2),
        ('中午', 2), ('傍晚', 4), ('黄昏', 4), ('上午', 1), ('晨', 0), ('早', 0),
        ('午', 2), ('暮', 4), ('夜', 5), ('晚', 5))

CN_DIGIT = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9}
CN_UNIT = {'十': 10, '百': 100, '千': 1000, '万': 10000}

NUM = r'[0-9零一二两三四五六七八九十百千万半]'

# 速度写法先剔掉，否则「一天走四十里」的四十里会被当成一段行程。
SPEED_PHRASE = re.compile(
    r'(?:一天|一日|每天|每日)\s*[走了]?\s*' + NUM + r'+\s*里'
    r'|' + NUM + r'+\s*里\s*/\s*[日天]'
    r'|' + NUM + r'+\s*里\s*(?:一天|一日)')

DIST_RE = re.compile(r'(' + NUM + r'+)\s*(?:来)?里')

# 时长：天半要排在「天」前面，七天半 = 7.5，不是 7。
DUR_RES = (
    (re.compile(r'(' + NUM + r'+)\s*天半'), lambda n: n + 0.5),
    (re.compile(r'(' + NUM + r'+)\s*个?\s*时辰'), lambda n: n / 12.0),
    (re.compile(r'(' + NUM + r'+)\s*天'), lambda n: n),
    (re.compile(r'(' + NUM + r'+)\s*日'), lambda n: n),
    (re.compile(r'(' + NUM + r'+)\s*个月'), lambda n: n * 30),
    (re.compile(r'(' + NUM + r'+)\s*年'), lambda n: n * 365),
)

# 超自然位移。地图第四节写明：出现这些不按步行速度套，标 inconclusive。
SUPERNATURAL = re.compile(r'飞|御剑|传送|瞬移|白光|法术|仙师|被带走')
RECALL = re.compile(r'回忆|回想|梦里|做梦|那年|从前|多年前|前世')


def _num(s):
    """中文数字转数。「三百」->300，「四十」->40，「七」->7，「半」->0.5。"""
    s = str(s or '').strip()
    if not s:
        return None
    if re.fullmatch(r'\d+(\.\d+)?', s):
        return float(s)
    total, cur = 0, 0
    for ch in s:
        if ch in CN_DIGIT:
            cur = CN_DIGIT[ch]
        elif ch in CN_UNIT:
            u = CN_UNIT[ch]
            if u == 10000:
                total = (total + cur) * u
            else:
                total += (cur or 1) * u
            cur = 0
        elif ch == '半':
            cur = cur + 0.5 if cur else 0.5
        else:
            return None
    return float(total + cur)


def _read(p):
    try:
        with open(p, encoding='utf-8-sig') as f:
            return f.read()
    except OSError:
        return ''


def _projects(book):
    return os.path.join(CO.projects_root(), book)


def _lib(book):
    return os.path.join(_projects(book), '设定库')


def _chapter_text(book, ch):
    """按章号前缀找正文。找不到返回 None（调用方决定跳过还是报）。"""
    d = os.path.join(_projects(book), '章节')
    if not os.path.isdir(d):
        return None
    for f in sorted(os.listdir(d)):
        if f.startswith(ch) and f.endswith('.md'):
            return _read(os.path.join(d, f))
    return None


def _rows(path):
    """把 md 表格读成 [[cell, ...], ...]，非表格行丢掉。"""
    out = []
    for line in _read(path).split('\n'):
        s = line.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if len(cells) >= 2:
            out.append(cells)
    return out


def _speeds(book):
    """世界地图「二、交通方式与速度」里的 里/日，跳过待定/未定。"""
    out = []
    for cells in _rows(os.path.join(_lib(book), '世界地图.md')):
        # 速度列不一定是第 2 列，整行找「X里/日」，换个书也不会读空
        m = re.search(r'(' + NUM + r'+)\s*里\s*/\s*[日天]', ' | '.join(cells))
        if not m:
            continue
        v = _num(m.group(1))
        if v:
            out.append((re.sub(r'[*＊]', '', cells[0]), v))
    return out


def _story_time(cell):
    """「第 1 天 夜」-> (1, 5)。写「未说明」或没有「第N天」-> None。

    时段认不出来时返回 (天, None)：只比天，不比时段，宁可漏报不倒流误报。
    """
    if not cell or '未说明' in cell or '待定' in cell:
        return None
    m = re.search(r'第\s*(' + NUM + r'+)\s*天', cell)
    if not m:
        return None
    day = _num(m.group(1))
    if day is None:
        return None
    rest = cell[m.end():]
    for w, v in SLOT:
        if w in rest:
            return (int(day), v)
    return (int(day), None)


def _timeline(book):
    """主线时间轴 -> {章号: (原文字, 解析结果或 None)}。"""
    out = {}
    for cells in _rows(os.path.join(_lib(book), '时间线.md')):
        # 章号列写 001 或「第 3 章」都认，统一补成三位
        m = re.search(r'(\d{1,3})', cells[0])
        if not m:
            continue
        ch = m.group(1).zfill(3)
        out[ch] = (cells[1], _story_time(cells[1]))
    return out


def _earlier(cur, prev):
    """cur 是否早于 prev。天不同比天；天相同要两边都有时段才敢比。"""
    if cur[0] != prev[0]:
        return cur[0] < prev[0]
    if cur[1] is None or prev[1] is None:
        return False
    return cur[1] < prev[1]


def _opening(text, n=160):
    """正文开头 n 字（去掉 md 标题）。跳跃只看开头，后文补交代不算。"""
    body = re.sub(r'^\s*#.*$', '', text, count=1, flags=re.M)
    return body.lstrip()[:n]


def _in_quote(text, pos):
    """pos 是否落在中文引号里。对白说「夜里」不等于本章发生在夜里：
    第一章结尾老汉喊的是「滩里夜里潮」，那是提醒，不是时间。"""
    head = text[:pos]
    return (head.count('“') > head.count('”')) or (head.count('「') > head.count('」'))


def _last_marker(text, words, tail_ratio=0.6):
    """后 40% 里最后一次出现的时间词（跳过对白里的），返回 (位置, 词)。"""
    start = int(len(text) * tail_ratio)
    last = None
    for w in words:
        for m in re.finditer(re.escape(w), text):
            if m.start() < start or _in_quote(text, m.start()):
                continue
            if last is None or m.start() > last[0]:
                last = (m.start(), w)
    return last


def _season_issues(text):
    """1 季节冲突：只判落在一个场景窗口里的矛盾季节词。"""
    hits = []
    for season, words in SEASON_WORDS.items():
        for w in words:
            for m in re.finditer(re.escape(w), text):
                hits.append((m.start(), season, w))
    hits.sort()
    issues, seen = [], set()
    for i, (p1, s1, w1) in enumerate(hits):
        for p2, s2, w2 in hits[i + 1:]:
            if p2 - p1 > SCENE_WINDOW:
                break
            if s1 == s2:
                continue
            key = tuple(sorted((s1, s2)))
            if key not in SEASON_CLASH or key in seen:
                continue
            seen.add(key)
            issues.append({'type': 'season_clash', 'severity': 'medium',
                           'detail': '同一场景里「%s」（%s）与「%s」（%s）相隔 %d 字，'
                                     '不该同一天出现' % (w1, s1, w2, s2, p2 - p1)})
    return issues


def _sentences(text):
    """按句切。距离和时长只在同一句里配对，跨句不猜。"""
    for s in re.split(r'[。！？!?；;\n]+', text):
        s = s.strip()
        if 4 <= len(s) <= 200:
            yield s


def _trip_issues(text, speeds):
    """2 时长 vs 距离：同一句里同时有里程和时长，就按速度表算够不够。"""
    if not speeds:
        return [], '世界地图没有速度表（二、交通方式与速度），时长/距离核对跳过'
    fastest = max(v for _, v in speeds)
    walk = next((v for k, v in speeds if '步行' in k), min(v for _, v in speeds))
    issues = []
    for sent in _sentences(text):
        clean = SPEED_PHRASE.sub('　', sent)
        dists = [(m.start(), _num(m.group(1)), m.group(0)) for m in DIST_RE.finditer(clean)]
        durs = []
        for pat, fn in DUR_RES:
            for m in pat.finditer(clean):
                v = _num(m.group(1))
                if v is None:
                    continue
                durs.append((m.start(), fn(v), m.group(0)))
        for dpos, li, ltxt in dists:
            if not li or not durs:
                continue
            _, days, dtxt = min(durs, key=lambda x: abs(x[0] - dpos))
            if SUPERNATURAL.search(sent):
                issues.append({'type': 'time_inconclusive', 'severity': 'low',
                               'detail': '「%s」是地图未登记的移动方式，%s/%s 不判' % (sent[:24], ltxt, dtxt)})
                continue
            need = li / fastest
            if days >= need - 0.25:
                continue
            issues.append({'type': 'time_distance', 'severity': 'high',
                           'detail': '%s配「%s」：步行 %g 里/日要 %.1f 天，最快 %g 里/日也要 %.1f 天，'
                                     '正文只给 %.1f 天' % (ltxt, dtxt, walk, li / walk, fastest, need, days)})
    return issues, None


def _jump_issue(book, ch, text):
    """3 时间跳跃：上一章结尾夜里，本章开头早上，又没过渡词。"""
    if not ch.isdigit() or int(ch) <= 1:
        return None, None
    prev_ch = '%03d' % (int(ch) - 1)
    prev = _chapter_text(book, prev_ch)
    if prev is None:
        return None, '第 %s 章没有正文，时间跳跃跳过' % prev_ch
    last = _last_marker(prev, NIGHT + MORNING)
    if not last or last[1] not in NIGHT:
        return None, None
    head = _opening(text)
    morning = [w for w in MORNING if w in head]
    if not morning:
        return None, None
    if any(w in (_opening(text, 300)) for w in TRANSITION):
        return None, None
    return ({'type': 'time_jump', 'severity': 'medium',
             'detail': '上一章（%s）结尾是「%s」，本章开头是「%s」，中间没有过渡交代'
                       % (prev_ch, last[1], morning[0])}, None)


def _rewind_issue(book, ch, text, timeline):
    """4 时间倒流：本章故事内时间早于最近一个有时间的上一章。"""
    if not timeline:
        return None, '设定库/时间线.md 缺失或没有主线时间轴，倒流检查跳过'
    if not ch.isdigit():
        return None, '章号「%s」不是数字，倒流检查跳过' % ch
    cur = timeline.get(ch)
    if cur is None:
        return None, '时间线里没有第 %s 章，倒流检查跳过' % ch
    if cur[1] is None:
        return None, '第 %s 章时间线写「%s」，数据不足不判' % (ch, cur[0])
    prevs = [(int(k), k, v) for k, v in timeline.items() if k.isdigit() and int(k) < int(ch) and v[1]]
    if not prevs:
        return None, None
    _, pk, pv = max(prevs)
    if not _earlier(cur[1], pv[1]):
        return None, None
    if RECALL.search(_opening(text, 200)):
        return None, None      # 本章自己声明是回忆，不算倒流
    return ({'type': 'time_rewind', 'severity': 'high',
             'detail': '本章「%s」早于第 %s 章「%s」' % (cur[0], pk, pv[0])}, None)


def check(book, chapter, text=None):
    '''book: 书名 str；chapter: 章号 str（'001'）；text: 正文，None 则自己从
       项目根/章节/ 下按前缀找文件。
       返回 {'blocking': [...], 'warnings': [...]}
       每条 issue = {'type': str, 'severity': 'critical'|'high'|'medium'|'low', 'detail': str}
       blocking 只放 severity=='critical'，其余进 warnings。
       数据缺失（没有地图表/时间线）时返回空列表并在 detail 里说明跳过了什么，不要抛异常。'''
    ch = str(chapter).zfill(3)
    if text is None:
        text = _chapter_text(book, ch) or ''

    issues, notes = [], []
    if not text:
        notes.append('第 %s 章正文为空，时间检查跳过' % ch)
    else:
        issues += _season_issues(text)
        got, note = _trip_issues(text, _speeds(book))
        issues += got
        if note:
            notes.append(note)
        got, note = _jump_issue(book, ch, text)
        if got:
            issues.append(got)
        if note:
            notes.append(note)
        got, note = _rewind_issue(book, ch, text, _timeline(book))
        if got:
            issues.append(got)
        if note:
            notes.append(note)

    for n in notes:
        issues.append({'type': 'time_skipped', 'severity': 'low', 'detail': n})

    blocking = [it for it in issues if it['severity'] == 'critical']
    warnings = [it for it in issues if it['severity'] != 'critical']
    return {'blocking': blocking, 'warnings': warnings}


def main():
    ap = argparse.ArgumentParser(description='L4 时间一致性')
    ap.add_argument('--book', required=True)
    ap.add_argument('--chapter', required=True)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    r = check(args.book, args.chapter)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print('第 %s 章：L4 命中 %d 条' % (args.chapter, len(r['blocking']) + len(r['warnings'])))
        for it in r['warnings']:
            print('  [%s/%s] %s' % (it['type'], it['severity'], it['detail']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
