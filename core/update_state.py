# -*- coding: utf-8 -*-
"""写完一章后，用一个小模型把「角色状态表」更新到最新。

用法:
    python core/update_state.py <章节文件> --book <书名> [--dry-run] [--model deepseek-flash]
    python core/update_state.py <章节目录> --book <书名> --all      # 按文件名顺序处理整个目录

只做三件事：
  1. 把「本章正文 + 当前角色状态表」交给模型，让它只输出有变化的角色段落
  2. 原地替换状态表里对应的 ## 角色名 段（其它角色、说明节不动）
  3. 写前备份 .bak-时间戳；正文没交代的一律写「未说明」，禁止模型编
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

STATE_REL = os.path.join('设定库', '角色状态.md')
BT = chr(96)

PROMPT = """你是小说项目的状态维护员。下面给你「当前角色状态表」和「本章正文」。
请**只输出需要修改的角色段落**，格式严格照抄状态表里的 Markdown（每个角色以两个井号加角色名开头，
下面是「- **字段**：值」的列表）。

规则：
1. 只输出有变化的角色；没变化的不要输出。
2. 只改这几类字段：当前位置、怎么到的、最后更新、身上物品、身体状况、钱、今天去过哪。
3. 「怎么到的」必须从正文里读出来：走/挑担/骑马/被带走/传送…；正文没交代就写「未说明」，
   **绝对不要自己编**。
4. 「最后更新」写成本章文件名（不含 .md）。
5. 「今天去过哪」按正文顺序用 → 连接；跨天的不要合并。
6. 如果一个角色都没变化，只输出一行：NO_CHANGES
7. 不要输出解释、不要输出代码块围栏。

当前角色状态表：
---
%s
---

本章文件名：%s
本章正文：
---
%s
---
"""


def _projects_root():
    """客户数据目录（与 coordinator.projects_root 同一套优先级）。
    原来用 CO.ROOT（程序目录），客户数据在 %APPDATA% 时永远找不到状态表。"""
    try:
        return CO.projects_root()
    except Exception:
        return os.path.join(CO.ROOT, 'projects')


def state_file(book):
    p = os.path.join(_projects_root(), book, STATE_REL)
    return p if os.path.exists(p) else None


def split_sections(text):
    lines = text.split('\n')
    head, blocks, cur_title, buf = [], [], None, []
    for ln in lines:
        if ln.startswith('## '):
            if cur_title is None:
                head = buf[:]
            else:
                blocks.append((cur_title, '\n'.join(buf).rstrip()))
            cur_title = ln[3:].strip()
            buf = [ln]
        else:
            buf.append(ln)
    if cur_title is not None:
        blocks.append((cur_title, '\n'.join(buf).rstrip()))
    else:
        head = buf[:]
    return head, blocks


def norm_name(title):
    t = title
    for a, b in (('（', '）'), ('(', ')')):
        while a in t and b in t:
            i1, i2 = t.find(a), t.find(b, t.find(a))
            if i1 < 0 or i2 < 0:
                break
            t = (t[:i1] + t[i2 + 1:]).strip()
    return t


def parse_model_output(text):
    s = CO.sanitize_worker_text(text or '')
    if 'NO_CHANGES' in s:
        return {}
    s = re.sub('^' + BT + '{3,}[a-zA-Z]*\\s*', '', s.strip())
    s = re.sub(BT + '{3,}\\s*$', '', s).strip()
    out, cur, buf = {}, None, []
    for ln in s.split('\n'):
        if ln.startswith('## '):
            if cur:
                out[cur] = '\n'.join(buf).rstrip()
            cur, buf = ln[3:].strip(), [ln]
        elif cur:
            buf.append(ln)
    if cur:
        out[cur] = '\n'.join(buf).rstrip()
    return out


def update_one(chapter_path, book, dry_run=False, model='deepseek-flash'):
    sf = state_file(book)
    if not sf:
        return {'ok': False, 'error': '状态表不存在: %s' % os.path.join('projects', book, STATE_REL)}
    with open(sf, encoding='utf-8-sig') as f:
        current = f.read()
    with open(chapter_path, encoding='utf-8-sig') as f:
        chapter = f.read()
    stem = os.path.splitext(os.path.basename(chapter_path))[0]

    messages = [{'role': 'user',
                 'content': PROMPT % (current, os.path.basename(chapter_path), chapter)}]
    t0 = time.time()
    try:
        resp = CO.chat({'model': model, 'temperature': 0.1, 'max_tokens': 3000,
                        'extra_body': {'thinking': {'type': 'disabled'}}}, messages)
    except Exception as e:
        return {'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}
    text = CO._extract_content(resp)
    billing = resp.get('_billing') or {}
    updates = parse_model_output(text)
    if not updates:
        return {'ok': True, 'changed': [], 'note': 'NO_CHANGES',
                'tokens': billing.get('total_tokens', 0), 'ms': int((time.time() - t0) * 1000)}

    head, blocks = split_sections(current)
    known = {}
    for i, (t, _) in enumerate(blocks):
        known[norm_name(t)] = i
    applied, unknown = [], []
    for name, seg in updates.items():
        key = norm_name(name)
        if key in known:
            idx = known[key]
            blocks[idx] = (blocks[idx][0], seg.rstrip())
            applied.append(key)
        else:
            unknown.append(name)

    new_text = '\n'.join(head).rstrip() + '\n\n'
    for title, seg in blocks:
        new_text += seg.rstrip() + '\n\n'
    new_text = new_text.rstrip() + '\n'

    result = {'ok': True, 'changed': applied, 'unknown': unknown,
              'tokens': billing.get('total_tokens', 0), 'ms': int((time.time() - t0) * 1000),
              'chapter': stem, 'dry_run': dry_run}
    if dry_run:
        result['preview'] = new_text[:1500]
        return result
    if not applied:
        result['note'] = '模型给的角色都不在状态表里，未写入'
        return result
    backup = sf + '.bak-' + time.strftime('%Y%m%d-%H%M')
    with open(backup, 'w', encoding='utf-8') as f:
        f.write(current)
    with open(sf, 'w', encoding='utf-8') as f:
        f.write(new_text)
    result['written'] = sf
    result['backup'] = backup
    return result


def main():
    ap = argparse.ArgumentParser(description='写完一章后更新角色状态表')
    ap.add_argument('chapter')
    ap.add_argument('--book', required=True)
    ap.add_argument('--model', default='deepseek-flash')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--all', action='store_true', help='chapter 传目录时按文件名顺序处理所有 .md')
    ap.add_argument('--json', nargs='?', const='', default=None)
    args = ap.parse_args()

    targets = []
    if args.all and os.path.isdir(args.chapter):
        for f in sorted(os.listdir(args.chapter)):
            if f.endswith('.md'):
                targets.append(os.path.join(args.chapter, f))
    else:
        targets = [args.chapter]

    results = []
    for t in targets:
        r = update_one(t, args.book, dry_run=args.dry_run, model=args.model)
        results.append(r)
        if not r.get('ok'):
            print('[失败] %s: %s' % (os.path.basename(t), r.get('error')), file=sys.stderr)
            continue
        print('%s -> 变更 %s%s（%s tok, %dms）' % (
            os.path.basename(t), r.get('changed') or '无',
            '，忽略未知角色 %s' % r['unknown'] if r.get('unknown') else '',
            r.get('tokens'), r.get('ms')))
        if r.get('written'):
            print('   已写入 %s（备份 %s）' % (r['written'], r['backup']))
        elif r.get('note'):
            print('   %s' % r['note'])
    if args.json is not None:
        out = json.dumps(results, ensure_ascii=False, indent=2)
        if args.json:
            with open(args.json, 'w', encoding='utf-8') as f:
                f.write(out)
        else:
            print(out)
    return 0 if all(r.get('ok') for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
