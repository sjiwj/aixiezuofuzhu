# -*- coding: utf-8 -*-
"""写前粗筛（precheck_input）：把注定写不好的输入挡在贵模型之前。

和 `precheck.py` 是两个阶段，别混：
  precheck.py        写完之后机检正文（字数/禁词/专名/穿越/重复/对话占比）
  precheck_input.py  写之前查输入（章号/大纲/占位残留/覆盖定稿）

模板「四保险」的第 ② 件「便宜粗筛」对应的是后者：脏活不进贵模型。
全部是本地字符串/文件判断，零模型调用、零网络。

检查项：
  P1 章号格式      必须 3 位数字（'003' / '003-第3章.md' 都认）
  P2 大纲存在      大纲/<ch>*.md 或 大纲/全书大纲.md 里出现该章
  P3 大纲分场      有 <details> 分场块；没有 → warn（一句话章纲会自编 1200 字环境）
  P4 必填块        场次/必须做到/不许做 缺任一 → warn
  P5 占位残留      {topic} / TODO / 待补 / xxx / 空括号 → block
  P6 覆盖已定稿    mode=replace 且该章已 done → warn

用法：
  import precheck_input as PI
  r = PI.screen_write(book, chapter, prompt, mode, root=PROJECTS, force=False, stage='')
  # r = {'ok': bool, 'blocked': [...], 'warn': [...], 'checked': [...], 'forced': bool}
"""
import os
import re

PLACEHOLDER_PATTERNS = [
    (re.compile(r'\{[a-zA-Z_][a-zA-Z0-9_]{1,20}\}'), '模板占位符如 {topic}'),
    (re.compile(r'\bTODO\b'), 'TODO 标记'),
    (re.compile(r'\bFIXME\b'), 'FIXME 标记'),
    (re.compile(r'(?i)\bxxx\b'), 'xxx 占位'),
    (re.compile(r'待补|待填|待写|占位'), '待补/占位字样'),
    (re.compile(r'（\s*）|\(\s*\)'), '空括号'),
]

OUTLINE_BLOCKS = ('场次', '必须做到', '不许做')


def _chapter_no(chapter):
    m = re.match(r'^(\d{3})', str(chapter or '').strip())
    return m.group(1) if m else ''


def _read(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def _find_outline(root, book, ch):
    """先找 大纲/<ch>*.md，再在 大纲/全书大纲.md 里找该章的表格行。返回 (text, source)。"""
    odir = os.path.join(root, book, '大纲')
    if not os.path.isdir(odir):
        return '', ''
    try:
        names = sorted(os.listdir(odir))
    except OSError:
        return '', ''
    for name in names:
        if not name.lower().endswith('.md'):
            continue
        if name.startswith(ch):
            txt = _read(os.path.join(odir, name))
            if txt.strip():
                return txt, '大纲/' + name
    whole = os.path.join(odir, '全书大纲.md')
    if os.path.isfile(whole):
        txt = _read(whole)
        for line in txt.splitlines():
            if line.strip().startswith('|') and ch in line:
                return txt, '大纲/全书大纲.md（第 %s 章行）' % ch
    return '', ''


def _outline_blocks(text):
    blocks, cur, buf = {}, None, []
    for line in (text or '').splitlines():
        m = re.match(r'^\*\*(.+?)\*\*\s*$', line.strip())
        name = ''
        if m:
            raw = m.group(1).strip()
            for known in ('场次', '必须做到', '本章推进', '不许做', '文风锚点'):
                if raw.startswith(known):
                    name = known
                    break
        if name:
            if cur:
                blocks[cur] = '\n'.join(buf).strip()
            cur, buf = name, []
            continue
        if cur is not None:
            buf.append(line)
    if cur:
        blocks[cur] = '\n'.join(buf).strip()
    return blocks


def screen_write(book, chapter, prompt='', mode='replace', root='', force=False,
                 stage=''):
    """写章前的本地粗筛。root 是书所在目录（即 PROJECTS，书在其下一级）。"""
    blocked, warn, checked = [], [], []

    def block(code, reason):
        blocked.append({'code': code, 'reason': reason})

    def soft(code, reason):
        warn.append({'code': code, 'reason': reason})

    ch = _chapter_no(chapter)
    if not ch:
        block('precheck.chapter_no',
              '章号必须是 3 位数字（如 003），收到的是「%s」' % (chapter or '空'))
    else:
        checked.append('章号 %s' % ch)

    otext = ''
    if ch:
        otext, source = _find_outline(root, book, ch)
        if not otext:
            block('precheck.no_outline',
                  '找不到第 %s 章的大纲（大纲/%s*.md 或 全书大纲.md 里的 %s 行）' % (ch, ch, ch))
        else:
            checked.append('大纲：%s' % source)
            if '<details' not in otext.lower():
                soft('precheck.outline_one_line',
                     '「%s」没有分场块（<details>）：一句话章纲会让模型自己铺 1200 字环境' % source)
            else:
                blocks = _outline_blocks(otext)
                lack = [b for b in OUTLINE_BLOCKS if b not in blocks]
                if lack:
                    soft('precheck.outline_blocks', '分场块缺：%s' % '、'.join(lack))
                else:
                    checked.append('分场块齐全（%s）' % '／'.join(OUTLINE_BLOCKS))

    hay = (prompt or '') + '\n' + otext
    for pat, label in PLACEHOLDER_PATTERNS:
        m = pat.search(hay)
        if m:
            block('precheck.placeholder', '输入里有%s：%s' % (label, m.group(0)[:20]))

    if mode == 'replace' and stage == 'done':
        soft('precheck.overwrite_done',
             '第 %s 章已是定稿状态，replace 会覆盖它（写盘前会备份）' % ch)

    if force:
        return {'ok': True, 'blocked': [],
                'warn': warn + [{'code': 'precheck.forced',
                                 'reason': '已用 force 跳过阻断项：%d 条' % len(blocked)}],
                'checked': checked, 'forced': True}
    return {'ok': not blocked, 'blocked': blocked, 'warn': warn,
            'checked': checked, 'forced': False}
