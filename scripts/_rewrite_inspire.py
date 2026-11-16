# -*- coding: utf-8 -*-
"""删掉被转义破坏的 inspire 块，改用 Python 重写（避免 JS 模板的 \\n 地狱）。"""
import io, re, sys
p = r"D:\NovelApp\core\server.py"
s = io.open(p, encoding="utf-8").read()

start = s.find("# ---------------- \u7075\u611f\u5c55\u5f00")
end = s.find("    def _polish(self, data):")
if start < 0 or end < 0 or end < start:
    print("block not found", start, end)
    sys.exit(1)
print("removing", len(s[start:end]), "chars")
s = s[:start] + s[end:]

BLOCK = r'''# ---------------- 灵感展开（照 Laper /v1/script/assist 的契约与预算抄的） ----------------
# 预算直接沿用它的数字：前 12 行 3000 字 / 后 6 行 1200 字 / 人物 12x600 / 账本 20x600
INSPIRE_BUDGET = {
    'seed': 2000,
    'before_lines': 12, 'before_chars': 3000,
    'after_lines': 6, 'after_chars': 1200,
    'cast_count': 12, 'cast_field': 600,
    'ledger_items': 20, 'ledger_value': 600,
    'max_variants': 3,
}


def _clip(text, limit):
    t = str(text or '')
    return t if len(t) <= limit else t[:limit]


def inspire_context(book, chapter):
    """按预算装配上下文：上一章末尾 / 人物卡 / 伏笔账本。缺什么就少给什么。"""
    out = {}
    try:
        import write_context as WC
        prev = WC._prev_chapters(book, str(chapter).zfill(3))
        if prev:
            tail = prev[-1][1]
            lines = tail.split(chr(10))[-INSPIRE_BUDGET['before_lines']:]
            out['before'] = _clip(chr(10).join(lines), INSPIRE_BUDGET['before_chars'])
    except Exception:
        pass
    base = os.path.join(PROJECTS, book, '设定库')
    for key, fname, budget in (
            ('cast', '角色卡.md', INSPIRE_BUDGET['cast_count'] * INSPIRE_BUDGET['cast_field']),
            ('ledger', '伏笔.md', INSPIRE_BUDGET['ledger_items'] * INSPIRE_BUDGET['ledger_value'])):
        try:
            with open(os.path.join(base, fname), encoding='utf-8-sig') as f:
                out[key] = _clip(f.read(), budget)
        except OSError:
            continue
    return out


INSPIRE_RULES = [
    '- 只写这一段（200-400 字），不写章节标题，不写任何说明',
    '- 动作要客观可见，不写心理总结和评价（不要「他心里一沉」这类）',
    '- 对白只写人物真说出口的话，不带括号里的表演指导',
    '- 不新增设定库里没有的人物、地名、物件',
    '- 不写「我记下了」「这句话稳」「比之前的都重」这类评价式短句',
]


def inspire_prompt(book, seed, hint, ctx, idx, total):
    """照 Laper 的硬约束思路：规则写死，让模型没得发挥。"""
    head = ('你是《%s》的作者。下面是你刚想到的一句话，请把它展开成一段正文。'
            % (book or '这本书'))
    body = ['【想法】' + str(seed)]
    if hint:
        body.append('【方向】' + str(hint))
    if total > 1:
        body.append('【第 %d 个方案】换一种写法，不要和其他方案重复' % idx)
    if ctx.get('before'):
        body.append('【前情（上一章末尾）】' + chr(10) + ctx['before'])
    if ctx.get('cast'):
        body.append('【人物】' + chr(10) + ctx['cast'])
    if ctx.get('ledger'):
        body.append('【伏笔账本】' + chr(10) + ctx['ledger'])
    return head + chr(10) + chr(10) + chr(10).join(INSPIRE_RULES) + chr(10) + chr(10) + (chr(10) + chr(10)).join(body)


'''
s = s[:start] + BLOCK + s[start:]
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("rewritten, new len", len(s))
