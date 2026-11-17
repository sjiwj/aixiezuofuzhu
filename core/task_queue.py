# -*- coding: utf-8 -*-
"""任务循环：给「先写哪章」一个可判的答案（模板三循环里的第一环）。

模板 §2 的任务循环职责：捞待办、排优先级、取任务；可判信号是「条目标识、状态、
输入是否齐备」。这里不新建数据源，只做三件事：

  1 把 stages.py 的状态机、章节文件、大纲、错题本合成一张待办表
  2 用可解释的分数排序（每条都写理由，不做黑箱）
  3 给出「下一个该处理哪章」，写不写仍由人决定（不自动调模型）

排序分数（可累加）：
  +100  错题本里有未处置条目（返工优先）
  +40   有本章章纲（大纲/<ch>*.md 或 全书大纲.md 的表格行）
  +20   有正文且状态是 draft/reviewing（可续写或润色）
  +10   有章纲但还没有正文（可直接开写）
  -50   已定稿
  缺章纲不加分，并在 reasons 里点明「会被写前粗筛挡」

用法：
  import queue as Q
  Q.build_queue('书名', root=PROJECTS)      # 全表
  Q.next_item('书名', root=PROJECTS)        # 下一个
"""
import os
import re

import loop_log as LL
import stages as ST

CHAPTERS = '章节'
OUTLINE = '大纲'
DONE = 'done'


def _outline_chapters(odir):
    """大纲目录里能对上的章号：文件名 <ch>*.md，或 全书大纲.md 里的 | 003 | 行。"""
    found = set()
    if not os.path.isdir(odir):
        return found
    try:
        names = os.listdir(odir)
    except OSError:
        return found
    for name in names:
        if not name.lower().endswith('.md'):
            continue
        ch = ST.chapter_no(name)
        if ch:
            found.add(ch)
    whole = os.path.join(odir, '全书大纲.md')
    if os.path.isfile(whole):
        try:
            with open(whole, encoding='utf-8', errors='replace') as f:
                for line in f:
                    if line.strip().startswith('|'):
                        m = re.match(r'\s*\|\s*(\d{3})\s*\|', line)
                        if m:
                            found.add(m.group(1))
        except OSError:
            pass
    return found


def _rework_chapters():
    """错题本里还没处置的章号（subject 里可能写「第2章 第1拍」，取前 3 位数字）。"""
    out = set()
    try:
        for it in LL.rework_queue():
            m = re.search(r'(\d{3})', str(it.get('subject') or ''))
            if m:
                out.add(m.group(1))
    except Exception:
        pass
    return out


def build_queue(book, root=None):
    stages = ST.get_stages(book, root)
    bdir = ST.book_dir(book, root)
    cdir = os.path.join(bdir, CHAPTERS)

    files = {}
    if os.path.isdir(cdir):
        try:
            for name in sorted(os.listdir(cdir)):
                if name.startswith('.') or not name.lower().endswith('.md'):
                    continue
                ch = ST.chapter_no(name)
                if ch:
                    files[ch] = name
        except OSError:
            pass

    outlines = _outline_chapters(os.path.join(bdir, OUTLINE))
    rework = _rework_chapters()

    items = []
    for ch in sorted(set(stages) | set(files) | outlines):
        state = stages.get(ch)
        if not state:
            state = 'draft' if ch in files else 'missing'
        has_outline = ch in outlines
        has_body = ch in files
        score, reasons = 0, []

        if ch in rework:
            score += 100
            reasons.append('错题本有未处置条目（返工优先）')
        if state == DONE:
            score -= 50
            reasons.append('已定稿')
        if has_outline:
            score += 40
            reasons.append('有章纲')
        else:
            reasons.append('缺章纲（写前粗筛会挡）')
        if has_body and state in ('draft', 'reviewing'):
            score += 20
            reasons.append('有正文，可续写/润色')
        if has_outline and not has_body:
            score += 10
            reasons.append('有章纲、无正文，可直接开写')

        items.append({
            'chapter': ch,
            'file': files.get(ch, ''),
            'state': state,
            'has_outline': has_outline,
            'has_body': has_body,
            'rework': ch in rework,
            'score': score,
            'reasons': reasons,
        })

    items.sort(key=lambda x: (-x['score'], x['chapter']))
    counts = {}
    for it in items:
        counts[it['state']] = counts.get(it['state'], 0) + 1
    return {'ok': True, 'book': book, 'count': len(items),
            'counts': counts, 'items': items}


def next_item(book, root=None, include_done=False):
    """下一个该处理的：分数最高、且不是定稿。没有可做的返回 None。"""
    q = build_queue(book, root)
    for it in q['items']:
        if it['state'] == DONE and not include_done:
            continue
        if it['score'] <= 0:
            continue
        return it
    return None
