# -*- coding: utf-8 -*-
"""L2 跨章对账（qc_l2）：单章看不出来的问题，得把前两章一起摆出来

为什么单独一个模块：precheck 那八条全是「本章内」能数清的事。
人称、称呼、时间词这三类，只在一章里看是看不出来的：
这一章全叫「苏姑娘」，上一章全叫「乙」，单章各自都自洽。
所以 check() 自己往前读 2 章，凑成 3 章窗口，和规范「最近 3 章」对齐。

四条：
  1 person_mix    人称混用    同一句里全名点两次 / 同一段叙事的「我」与「他」并用
  2 address_drift 称呼不统一  同一人物在叙述里出现两种叫法
  3 time_vague    模糊时间词  一章超过 TIME_VAGUE_MAX 次
  4 foreshadow_untracked  正文写了「伏笔」，但台账里没有对应条目（保守版，其余不报）

severity 全部落在 medium/low：这四条都够不上「退回重写」。
blocking 只收 critical，所以本模块正常情况 blocking 是空的——
真正的拦截留给 precheck 的硬条，这里只给审稿团递线索。

数据缺失（没角色卡、没伏笔台账）不抛异常，也不报假警：
一条 issue 都没产出时，才附一条 low 的 qc_l2_skip 说明跳过了什么。
有命中就不啰嗦——detail 里已经是真问题了。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

PREV_CHAPTERS = 2          # 本章 + 前 2 章 = 3 章窗口，对齐规范「最近 3 章」
NAME_REPEAT_LIMIT = 1      # 同一句里全名出现 >1 次算重复点全名
# 通称不算「全名」：这些词重复出现是正常指代（「他问老头，老头只说」「老头没动」），
# 不是人称混乱。真实 008 章就是被「老头」误报的，所以先排掉。
COMMON_NOUN = {'老头', '老汉', '姑娘', '掌柜', '掌柜的', '大娘', '妇人', '汉子',
               '老人', '摊主', '少年', '孩子', '伙计', '店家', '客人', '众人'}
TIME_VAGUE_MAX = 3         # 一章超过 3 次模糊时间词才报
# 真实 3 章实测：窄词表下 0 次，宽词表下 001 也不过「后半晌 5 / 一会儿 2 / 上个月 2」。
# 阈值 3 落在「正常波动之外」；样本只有 3 章，按规范只能当参考，不当硬门禁。

# 称谓表：只用来拼「姓+称谓」（苏姑娘、周掌柜），不做语义判断。
TITLES = ('掌柜', '掌柜的', '老板', '姑娘', '先生', '公子', '师傅', '老汉',
          '老头', '大娘', '婶子', '嫂子', '叔', '爷')

# 模糊时间词：只收「跳过一段时间」的标记，不收时长词（看了一会儿、后半晌）。
# 规范原例就是这三个：三个月后 / 没几日 / 过了些时候。
TIME_VAGUE = (
    r'(?:两|三|四|五|六|七|八|九|十|几|数|半|多|好)(?:个)?(?:月|日|天|年|载)\s*(?:之后|以后|后)',
    r'过了(?:些|几|好|一)?(?:段)?(?:天|日|月|年|时候|日子|阵子|会儿|些时候|很久|许久|半天)',
    r'(?:没|不)(?:过)?(?:几|多|两|三)(?:天|日|月|年)',
    r'不多时',
    r'不(?:知|晓)(?:道)?过了多久',
    r'隔了(?:些|几|好)?(?:天|日|月|年|阵子)?',
    r'好些(?:日子|天|年)',
    r'过了一会儿?',
    r'许久',
    r'良久',
    r'(?<![后前上])半晌',      # 「后半晌」是下午，不是模糊跳跃，必须放过
)
TIME_VAGUE_RE = re.compile('|'.join('(?:%s)' % p for p in TIME_VAGUE))

# 引号：001/003 用中文弯引号，002 通篇用 ASCII 直引号，两套都要认。
QUOTE_RE = re.compile(r'[\u201c"\u300c\u300e][^\u201d"\u300d\u300f]{0,400}?[\u201d"\u300d\u300f]')
PLACEHOLDER = ('没改过名字', '没有', '无', '暂无', '（未记录）', '(未记录)', '—', '-', '略')


def _read(p):
    try:
        with open(p, encoding='utf-8-sig') as f:
            return f.read()
    except OSError:
        return ''


def _body(text):
    """去掉章标题和 --- 分隔线：它们不是正文，混进来会把句子切碎。"""
    body = re.sub(r'^\s*#.*$', '', text or '', count=1, flags=re.M)
    return re.sub(r'^\s*-{3,}\s*$', '', body, flags=re.M)


def _paras(body):
    return [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]


def _sentences(para):
    return [s for s in re.split(r'[。！？；]', para) if s]


def _narr(body):
    """去掉引号里的内容，只留叙述。

    台词里怎么叫人是人物自己在说话（「老丈」「掌柜的」），
    那是口吻不是漏洞；只有叙述层摇摆才是作者的锅。
    """
    return QUOTE_RE.sub('', body)


def _ok_name(nm):
    return bool(nm) and 2 <= len(nm) <= 4 and re.fullmatch(r'[\u4e00-\u9fa5]+', nm)


# ---------------- 读章节 ----------------

def _chapter_dir(book):
    return os.path.join(CO.projects_root(), book, '章节')


def _chapter_files(book):
    """[(章号, 文件名)]，按章号升序。.bak / .draft 自然被 endswith('.md') 挡掉。"""
    d = _chapter_dir(book)
    out = []
    for f in (os.listdir(d) if os.path.isdir(d) else []):
        if not f.endswith('.md'):
            continue
        m = re.match(r'^(\d{3})', f)
        if m:
            out.append((m.group(1), f))
    return sorted(out)


def _find_chapter(book, ch):
    for num, f in _chapter_files(book):
        if num == ch:
            return os.path.join(_chapter_dir(book), f)
    return ''


def _window(book, ch, cur_body):
    """前 PREV_CHAPTERS 章 + 本章。缺章就少读几章，不补空章节凑数。"""
    nums = [n for n, _ in _chapter_files(book) if n < ch][-PREV_CHAPTERS:]
    out = [(n, _body(_read(_find_chapter(book, n)))) for n in nums]
    out.append((ch, cur_body))
    return out


# ---------------- 名册 ----------------

def _roster(book):
    """书名 -> {'names': [...], 'alias': {人物: set}, 'avoid': {人物: set}}

    三个来源，谁有算谁：
      A 设定库/角色卡/*.md   一人一卡，文件名就是正名，卡片里有别称
      B 设定库/角色卡.md     索引，[[双链]] 就是名单
      C 设定库/角色状态.md   ## 名字（配角·说明），但要求该节里有「当前位置」
                            —— 只靠 ## 判断会把「## 更新规则」收成人名
    """
    base = os.path.join(CO.projects_root(), book, '设定库')
    names, alias, avoid = [], {}, {}

    card_dir = os.path.join(base, '角色卡')
    for f in (os.listdir(card_dir) if os.path.isdir(card_dir) else []):
        if not f.endswith('.md'):
            continue
        nm = re.sub(r'[（(].*?[)）]', '', f[:-3]).strip()
        if not _ok_name(nm):
            continue
        if nm not in names:
            names.append(nm)
        text = _read(os.path.join(card_dir, f))
        # 卡片里「姓名 / 别称 / 称呼 / 又称」才算正式别名；其余行（外貌、行为逻辑）不碰
        for m in re.finditer(r'\*\*(姓名|别称|又称|又名|称呼)\*\*\s*[:：]\s*(.+)', text):
            val = m.group(2).strip()
            got = set()
            for q in re.findall(r'[\u201c"\u300c\u300e]([^\u201d"\u300d\u300f]{1,6})[\u201d"\u300d\u300f]', val):
                got.add(q)
            if not got:
                for part in re.split(r'[、,，\s/／]+', val):
                    got.add(part.strip())
            for g in got:
                if not _ok_name(g) or g in PLACEHOLDER:
                    continue
                alias.setdefault(nm, set()).add(g)
        # 「与 002 的"老汉"是两个人，不要混」——这类句子是作者亲手划的界线，必须尊重
        for line in text.split('\n'):
            if not re.search(r'是两个人|不是一个人|不要混|别混|别弄混', line):
                continue
            for q in re.findall(r'[\u201c"\u300c\u300e]([^\u201d"\u300d\u300f]{1,6})[\u201d"\u300d\u300f]', line):
                if _ok_name(q) and q != nm:
                    avoid.setdefault(nm, set()).add(q)

    for q in re.findall(r'\[\[([^\]|]{1,8})', _read(os.path.join(base, '角色卡.md'))):
        nm = q.strip()
        if _ok_name(nm) and nm not in names:
            names.append(nm)

    state = _read(os.path.join(base, '角色状态.md'))
    for block in re.split(r'^## ', state, flags=re.M)[1:]:
        head, _, rest = block.partition('\n')
        if '当前位置' not in rest:
            continue
        nm = re.sub(r'[（(].*?[)）]', '', head).strip()
        if _ok_name(nm) and nm not in names:
            names.append(nm)

    # 名字本身就是称谓的（老头、老汉），别让「姓+称谓」把它自己推成别名
    for nm in names:
        alias.setdefault(nm, set()).discard(nm)
        alias[nm] -= avoid.get(nm, set())
    return {'names': names, 'alias': alias, 'avoid': avoid}


def _surname_owners(roster):
    """姓 -> [人物]。用来判断「苏姑娘」这种推断是不是只有一个候选。"""
    out = {}
    for nm in roster['names']:
        out.setdefault(nm[0], []).append(nm)
    return out


# ---------------- 1 人称混用 ----------------

def _person_mix(ch, body, roster):
    """人称混用只看本章。

    它本来就是「段内/句内」的事，拉前两章进来只会让同一个毛病在窗口里
    连着报三遍。跨章那部分交给称呼对账，那边才真需要窗口。
    """
    issues = []
    names = roster['names']
    if not names:
        return issues, '角色卡是空的，不知道谁是谁，人称混用没查'
    for para in _paras(body):
        # 全名重复：按句判，不按段判。
        # 按段会诬告「段首点一次全名、段尾再点一次」这种正常收尾
        # （真实 001「没见老头醒透过。全示例镇，数这老头……」是强调，不是混乱）。
        for s in _sentences(para):
            for nm in names:
                if nm in COMMON_NOUN:
                    continue
                c = s.count(nm)
                if c > NAME_REPEAT_LIMIT:
                    issues.append({'type': 'person_mix', 'severity': 'medium',
                                   'detail': '%s 章同一句里「%s」点了 %d 次，没落代词：%s'
                                             % (ch, nm, c, s[:40])})
        # 我 / 他 混用：只在叙述层判，且要求同一段里两者都在
        nar = _narr(para)
        me, ta = nar.count('我'), nar.count('他') + nar.count('她')
        if me and ta:
            issues.append({'type': 'person_mix', 'severity': 'medium',
                           'detail': '%s 章同一段叙述里「我」%d 次、「他」%d 次，人称没统一：%s'
                                     % (ch, me, ta, nar[:40])})
    return issues, None


# ---------------- 2 称呼不统一 ----------------

def _address_drift(window, roster, ch_cur):
    """同一人物在叙述里出现两种叫法。

    三条来源，从严到松：
      a 角色卡明确写了别称  -> 两种叫法就是硬冲突          medium
      b 姓+称谓 能推出来，且同姓没别人在这几章露面         medium
      c 姓+称谓 能推出来，但同姓的另一个人也在场（歧义）    low
        —— 真实数据就是这种：「苏姑娘」可能是乙，也可能是苏掌柜，
           不硬判，报出来让作者认。
    """
    issues = []
    by_sur = _surname_owners(roster)
    if not roster['names']:
        return issues, '角色卡是空的，称呼不统一没查'

    narr_all = {}
    for ch, body in window:
        narr_all[ch] = _narr(body)

    for canon in roster['names']:
        forms = {}       # 形态 -> [章]
        for ch, nar in narr_all.items():
            for form in [canon] + sorted(roster['alias'].get(canon) or []):
                if form != canon and form in (roster['avoid'].get(canon) or set()):
                    continue
                if nar.count(form):
                    forms.setdefault(form, [])
                    if ch not in forms[form]:
                        forms[form].append(ch)
            # 推断：这个人的姓 + 称谓表里的词，真的出现在叙述里才算
            sur = canon[0]
            for t in TITLES:
                cand = sur + t
                if cand == canon or len(cand) < 2:
                    continue
                if cand in roster['names'] or cand in (roster['avoid'].get(canon) or set()):
                    continue        # 那是别人的正名，别抢
                if nar.count(cand):
                    forms.setdefault(cand, [])
                    if ch not in forms[cand]:
                        forms[cand].append(ch)

        if len(forms) < 2:
            continue
        # 只报牵涉本章的：001 的摇摆不该在审 002/003 时再报两遍。
        # 纯跨章的那种（002 全叫甲、003 全叫乙）本章必然占一边，照样会报。
        if not any(ch_cur in forms[f] for f in forms):
            continue

        declared = set(roster['alias'].get(canon) or [])
        inferred = [f for f in forms if f != canon and f not in declared]
        detail = '「%s」在叙述里有 %d 种叫法：%s' % (
            canon, len(forms), ' / '.join('%s(%s)' % (f, '、'.join(sorted(forms[f]))) for f in forms))
        # 同姓的另一个人只是登记在册、这 3 章里根本没出场，就不算歧义。
        # （苏掌柜登记了，但 001-003 一次没露面，所以「苏姑娘」基本只可能指乙）
        rivals = [n for n in by_sur.get(canon[0], [])
                  if n != canon and any(nar.count(n) for nar in narr_all.values())]
        if not inferred:
            sev, note = 'medium', '角色卡里记了别名，正文没统一'
        elif rivals:
            sev = 'low'
            note = '姓「%s」下 %s 也在这几章里，推断可能指错人，请作者认一下' % (
                canon[0], '、'.join(rivals))
        else:
            sev, note = 'medium', '按「姓+称谓」推断，同姓只有这一人'
        issues.append({'type': 'address_drift', 'severity': sev,
                       'detail': detail + '；' + note})
    return issues, None


# ---------------- 3 模糊时间词 ----------------

def _time_vague(ch, body):
    hits = TIME_VAGUE_RE.findall(body)
    # findall 带分组时会返回元组，统一压成字符串
    hits = [h if isinstance(h, str) else ''.join(h) for h in hits]
    if len(hits) <= TIME_VAGUE_MAX:
        return [], None
    uniq = []
    for h in hits:
        if h and h not in uniq:
            uniq.append(h)
    return [{'type': 'time_vague', 'severity': 'medium',
             'detail': '%s 章模糊时间词 %d 次（上限 %d）：%s'
                       % (ch, len(hits), TIME_VAGUE_MAX, '、'.join(uniq[:6]))}], None


# ---------------- 4 伏笔台账 ----------------

def _foreshadow_entries(book):
    """伏笔.md -> [{'id','ch','text'}]；文件不在返回 None（不报，只记跳过）。"""
    p = os.path.join(CO.projects_root(), book, '设定库', '伏笔.md')
    if not os.path.isfile(p):
        return None
    out = []
    for line in _read(p).split('\n'):
        s = line.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if len(cells) < 3 or set(cells[0]) <= set('-: '):
            continue
        if cells[0] in ('编号', '）暂无（', '（暂无）'):
            continue
        chs = re.findall(r'\d{3}', cells[1])
        out.append({'id': cells[0], 'ch': chs[0] if chs else '', 'text': cells[2]})
    return out


def _overlap(a, b, n=4):
    """a 里有没有 n 字连续片段出现在 b 里。用来判断「这句正文是不是在说那条伏笔」。"""
    a = re.sub(r'[\s，。、；：,.;:！？]', '', a or '')
    b = re.sub(r'[\s，。、；：,.;:！？]', '', b or '')
    return any(a[i:i + n] in b for i in range(0, max(0, len(a) - n + 1)))


def _foreshadow(book, ch, body):
    """保守版：只在正文真的写了「伏笔」两个字时才查。

    正常小说不会写「这是一个伏笔」，所以这条基本不响；
    一旦响了，多半是作者在正文里漏了元叙述，或者忘了登记。
    """
    if '伏笔' not in body:
        return [], None
    entries = _foreshadow_entries(book)
    if entries is None:
        return [], '没有 设定库/伏笔.md，正文里的「伏笔」没处对账'
    if any(e['ch'] == ch for e in entries):
        return [], None
    for m in re.finditer('伏笔', body):
        near = body[max(0, m.start() - 30):m.end() + 30]
        if any(_overlap(e['text'], near) for e in entries):
            return [], None
    return [{'type': 'foreshadow_untracked', 'severity': 'low',
             'detail': '%s 章正文出现「伏笔」，但台账里没有对应条目（共 %d 条，没有埋在本章的）'
                       % (ch, len(entries))}], None


# ---------------- 入口 ----------------

def check(book, chapter, text=None):
    """L2 跨章对账。book 书名；chapter 章号 '001'；text 正文，None 则自己按前缀找文件。

    返回 {'blocking': [...], 'warnings': [...]}，issue = {type, severity, detail}。
    blocking 只放 critical；本模块只有 medium/low，所以 blocking 恒为空，
    真正的拦截交给 precheck 的硬条。
    """
    ch = str(chapter).zfill(3)
    if text is None:
        p = _find_chapter(book, ch)
        text = _read(p)
        if not p:
            return {'blocking': [], 'warnings': [
                {'type': 'qc_l2_skip', 'severity': 'low',
                 'detail': '章节/ 下找不到 %s 开头的正文，L2 没跑' % ch}]}
    body = _body(text)

    roster = _roster(book)
    window = _window(book, ch, body)

    issues, skips = [], []
    for fn, args in ((_person_mix, (ch, body, roster)),
                     (_address_drift, (window, roster, ch))):
        got, skip = fn(*args)
        issues += got
        if skip:
            skips.append(skip)
    got, skip = _time_vague(ch, body)
    issues += got
    if skip:
        skips.append(skip)
    got, skip = _foreshadow(book, ch, body)
    issues += got
    if skip:
        skips.append(skip)

    blocking = [i for i in issues if i['severity'] == 'critical']
    warnings = [i for i in issues if i['severity'] != 'critical']
    # 一条都没查出来、又确实有跳过 -> 说明「干净」可能是没数据，得说清楚
    if not issues and skips:
        warnings.append({'type': 'qc_l2_skip', 'severity': 'low',
                         'detail': 'L2 跳过了：' + '；'.join(skips)})
    return {'blocking': blocking, 'warnings': warnings}


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser(description='L2 跨章对账（前 2 章 + 本章）')
    ap.add_argument('--book', required=True)
    ap.add_argument('--chapter', required=True)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    r = check(args.book, args.chapter)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    print('L2 %s 章：blocking %d 条，warnings %d 条'
          % (args.chapter, len(r['blocking']), len(r['warnings'])))
    for it in r['blocking'] + r['warnings']:
        print('  [%s/%s] %s' % (it['type'], it['severity'], it['detail']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
