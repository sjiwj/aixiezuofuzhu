# -*- coding: utf-8 -*-
"""上下文预算：每个数据源自带「输出契约」（照 OpenWrite models/context_package.py 抄）

思路（来自 docs/product/竞品解包报告.md · 可抄实现 ②）：
    预算不是一个全局配置表，是每个数据源的输出契约——
    每个账本自己知道「我最多给几条、最多几字」，拼装层不用管。
    所以这里只提供 clip_text / clip_items 两个工具 + 一张默认值表，
    真正的截断发生在 write_context 装配每一段的时候（分散契约，不是集中配置）。

用法（与 OpenWrite 的 to_context_text(max_chars) 同构）：
    body = clip_items(items, BUDGET['cast_items'], lambda c: '- %s：%s' % (c[0], c[1]))
    body = clip_text(body, BUDGET['cast_chars'])

──────────── BUDGET 里每个数字的依据（不许拍脑袋，逐条给出处）────────────
cast 12×600       ← Laper 2.0.2 的契约数字「人物 12×600」（已逆向确认；
                     ★ 是「最多 12 人，每人 600 字」= 总量 7200，不是总量 600。
                       2026-11-08 修：初版把 cast_chars 写成 600，导致大书上每张卡
                       只剩约 50 字，角色卡被切得只剩名字。
                     出处 work/cases/laper/REPORT.md，另见竞品解包报告 三、Laper 上下文预算）
before 12行/3000  ← 同上（Laper 契约「前12行/3000字」）
promise 6×600     ← 我们实际一次最多推 3 条承诺（write_context._pick_promises 自动挑
                     时是 [:2]，章纲指定时按章纲写），6 = 3 × 2，留一倍余量；
                     600 字 = 3 条 × 每条 200 字绰绰有余（承诺正文本身很短）
其余 5 组         ← 按「一章正文 3000 字」的比例分配，约束是
                     「预算段合计 ≤ 正文 2 倍（6000 字）」这个量级（与 Laper 同量级），
                     再按改造前实测占用往下压。
                     实测（《<书名>》008，改造前）：角色卡 665 字 / 角色状态 783 字 /
                     力量体系 762 字（已被 _ledger 截到 1200）/ 时间线 617 字 /
                     承诺 8 条 210 字 / 信息差 6 条 134 字 / 上一章全文 3390 字。
                     其中角色卡、角色状态是「条数随书增长」的两段，所以给固定条数 +
                     每次一章量级的字数；力量体系 / 时间线 / 地图是整篇 markdown，
                     按「够本章核对用」给 400 / 400 / 500。

注意：这份表是「上限」，不是「每次必须给满」。实测一段没超上限时 clip_* 原样返回，
输出与改造前逐字节相同（见 write_context 的 NOVELAPP_NO_BUDGET 开关）。
"""

# 段名 -> 上限。_items 是条数上限，_chars 是字数上限（渲染后的正文字符数，不含小标题）。
BUDGET = {
    'cast_items': 12,      'cast_chars': 7200,      # 角色卡  ← Laper 契约「人物 12×600」= 12 人每人 600 字
    'cast_card_chars': 600,                        # 单卡上限（12 × 600 = 7200 总量）
    'state_items': 8,      'state_chars': 500,      # 角色状态
    'map_items': 10,       'map_chars': 500,        # 地图
    'realm_items': 10,     'realm_chars': 400,      # 力量体系
    'timeline_items': 10,  'timeline_chars': 400,   # 时间线
    'promise_items': 6,    'promise_chars': 600,    # 承诺   ← 3 条 × 2 倍余量
    'foreshadow_items': 6, 'foreshadow_chars': 500, # 伏笔
    'infogap_items': 6,    'infogap_chars': 400,    # 信息差
    'before_lines': 12,    'before_chars': 3000,    # 上一章末尾 ← Laper 契约
}

# 段名 -> 中文名（budget_report / format_report 用；没登记的段名原样显示）
LABELS = {
    'sixq': '开写前六问',
    'outline': '本章章纲/任务',
    'summaries': '前情摘要',
    'before': '上一章全文',
    'cast': '角色卡',
    'state': '角色状态',
    'map': '世界地图',
    'realm': '力量体系',
    'timeline': '时间线',
    'promise': '承诺',
    'foreshadow': '伏笔',
    'infogap': '信息差',
    'no_do': '不许做',
    'style': '文风',
}


def clip_text(text, max_chars):
    """超长截断，末尾加「…」。

    规矩：
      - 空文本返回空串（**不返回 None**，否则调用方的 '%s' 拼接会变成 'None'）
      - max_chars 为 0 / None / 负数 → 不截断（= 不限）
      - 截断后总长不超过 max_chars（省略号算在额度里）
    """
    if not text:
        return ''
    if not max_chars or max_chars <= 0:
        return text
    if len(text) <= max_chars:
        return text
    if max_chars == 1:
        return '…'
    return text[:max_chars - 1].rstrip() + '…'


def clip_items(items, max_items, render, sep='\n', note=True):
    """列表截断 + 渲染。

    render 是「把单条渲染成字符串」的函数；sep 是条与条之间的分隔（
    write_context 里角色卡用 '\n\n'，承诺用 '\n'）。

    条数被截断时，末尾补一行标注（让模型知道自己拿到的不是全部）：
        （以上已截断，共 N 条中取前 M 条）
    note=False 可关掉这行标注（给不需要提示的调用方）。
    max_items 为 0 / None / 负数 → 不按条数截断。
    """
    items = list(items or [])
    if max_items and max_items > 0:
        kept = items[:max_items]
    else:
        kept = items
    text = sep.join(render(x) for x in kept)
    if note and len(kept) < len(items):
        text += '\n（以上已截断，共 %d 条中取前 %d 条）' % (len(items), len(kept))
    return text


def budget_report(used):
    """返回每个字段用了多少字 / 多少条，供调试和 UI 显示。

    used 形如：
        {'cast': {'chars': 600, 'items': 2, 'raw_chars': 665},
         'state': {'chars': 500, 'items': 4},
         'before': {'chars': 3000},
         'summaries': (312, 3)}          # 也接受元组
    'items' 记的是「总共几条」（截断前的 N），和上限比就知道是条数超了还是字数超了；
    'raw_chars' 可选，记截断前的字数；'budget' 可选，指向 BUDGET 里另一个前缀。

    返回 {'rows': [...], 'total_chars': n, 'total_items': n}，每行含
    key / label / chars / items / limit_chars / limit_items / chars_over / items_over。
    """
    rows = []
    total_chars = 0
    total_items = 0
    for key, val in (used or {}).items():
        raw_chars = None
        if isinstance(val, dict):
            chars = int(val.get('chars') or 0)
            items = val.get('items')
            raw_chars = val.get('raw_chars')
            bkey = val.get('budget') or key
        elif isinstance(val, (tuple, list)):
            chars = int(val[0] or 0) if val else 0
            items = val[1] if len(val) > 1 else None
            bkey = key
        else:
            chars = int(val or 0)
            items = None
            bkey = key
        limit_chars = BUDGET.get(bkey + '_chars')
        limit_items = BUDGET.get(bkey + '_items')
        row = {'key': key, 'label': LABELS.get(key, key),
               'chars': chars, 'items': items,
               'limit_chars': limit_chars, 'limit_items': limit_items,
               'chars_over': bool(limit_chars and chars > limit_chars),
               'items_over': bool(limit_items and items is not None and int(items) > limit_items)}
        if raw_chars is not None:
            row['raw_chars'] = int(raw_chars)
        rows.append(row)
        total_chars += chars
        if items:
            total_items += int(items)
    return {'rows': rows, 'total_chars': total_chars, 'total_items': total_items}


def _pad(text, width):
    """按显示宽度补空格（中文算 2 列），让预算报告在等宽字体里对齐。"""
    w = sum(2 if ord(ch) > 127 else 1 for ch in text)
    return text + ' ' * max(0, width - w)


def format_report(report):
    """把 budget_report 的结果排成可打印的几行（CLI / 日志 / UI 预览用）。"""
    rows = report.get('rows') or []
    head = '预算报告：%d 段，段内合计 %d 字' % (len(rows), report.get('total_chars') or 0)
    if report.get('prompt_chars'):
        head += '（prompt 总计 %d 字 / 上限 %d）' % (report['prompt_chars'],
                                                   report.get('prompt_budget') or 0)
    lines = [head]
    for r in rows:
        seg = '  %s%5d 字' % (_pad(r['label'], 18), r['chars'])
        if r.get('limit_chars'):
            seg += ' / %d' % r['limit_chars']
        if r.get('items') is not None:
            seg += '，%d 条' % r['items']
            if r.get('limit_items'):
                seg += ' / %d' % r['limit_items']
        if r.get('chars_over') or r.get('items_over'):
            seg += '  ← 已截断'
            if r.get('raw_chars'):
                seg += '（原 %d 字）' % r['raw_chars']
        lines.append(seg)
    return lines
