# -*- coding: utf-8 -*-
"""写完一章后，一次更新六个账本（角色状态 / 时间线 / 事件索引 / 章节摘要 / 伏笔 / 力量体系）。

用法:
    python core/update_ledgers.py projects/<书名>/章节/003-第三章-中间那个字.md --book <书名> --dry-run
    python core/update_ledgers.py <章> --book <书名>            # 真写（每个账本各留 .bak）

原则：模型只输出「要改的那一段」，脚本负责替换/追加；正文没交代的一律写「未说明」，不许编。
"""
import argparse
import difflib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO
import update_state as US

BT = chr(96)


def cfg_path(book, name):
    return os.path.join(CO.projects_root(), book, '设定库', name)


def read(p):
    try:
        with open(p, encoding='utf-8-sig') as f:
            return f.read()
    except OSError:
        return ''


def ask(prompt, model='deepseek-flash', max_tokens=1600):
    resp = CO.chat({'model': model, 'temperature': 0.1, 'max_tokens': max_tokens,
                    'extra_body': {'thinking': {'type': 'disabled'}}},
                   [{'role': 'user', 'content': prompt}])
    return CO.sanitize_worker_text(CO._extract_content(resp) or '')


def strip_fence(s):
    s = (s or '').strip()
    s = re.sub('^' + BT + r'{3,}[a-zA-Z]*s*', '', s)
    s = re.sub(BT + r'{3,}s*$', '', s).strip()
    return s


# ---------------- 逐账本 ----------------

def upd_state(chapter_path, book, chapter_text, stem, dry):
    return US.update_one(chapter_path, book, dry_run=True)


def upd_row(ledger_file, book, chapter_text, stem, no, kind, dry):
    """时间线 / 事件索引：替换或追加一行。"""
    p = cfg_path(book, ledger_file)
    cur = read(p)
    if not cur:
        return {'ledger': ledger_file, 'ok': False, 'error': '文件缺失'}
    if kind == 'timeline':
        spec = ('| 章 | 故事内时间 | 地点 | 关键事件 | 距上一章 |')
        hint = '列顺序：章 | 故事内时间 | 地点 | 关键事件 | 距上一章'
    else:
        spec = ('| 章 | 故事内时间 | 一句话事件 | 关键角色 | 关键地点 |')
        hint = '列顺序：章 | 故事内时间 | 一句话事件 | 关键角色 | 关键地点'
    prompt = ('你是小说项目的账本维护员。只输出**一行** Markdown 表格行，给第 %s 章用。\n'
              '表格格式：%s\n%s\n'
              '本章正文没写的时间/地点一律写「未说明」，不要编。不要输出解释。\n\n'
              '本章正文：\n%s' % (stem, spec, hint, chapter_text[:6000]))
    line = strip_fence(ask(prompt)).splitlines()[0].strip()
    if not line.startswith('|'):
        return {'ledger': ledger_file, 'ok': False, 'error': '模型没给表格行: %s' % line[:60]}
    # 章号列统一成 003，模型常写成「第003章」
    cells = [c.strip() for c in line.strip().strip('|').split('|')]
    cells[0] = stem[:3]
    line = '| ' + ' | '.join(cells) + ' |'
    lines = cur.split('\n')
    replaced = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith('| %s ' % stem[:3]) or ln.strip().startswith('| ' + str(no) + ' '):
            lines[i] = line
            replaced = True
            break
    if not replaced:
        # 插到最后一行表格后面
        last = max(i for i, ln in enumerate(lines) if ln.strip().startswith('|'))
        lines.insert(last + 1, line)
    new = '\n'.join(lines)
    return {'ledger': ledger_file, 'ok': True, 'old': cur, 'new': new,
            'replaced': replaced, 'row': line}


def upd_summary(book, chapter_text, stem, dry):
    p = cfg_path(book, '章节摘要.md')
    cur = read(p)
    if not cur:
        return {'ledger': '章节摘要.md', 'ok': False, 'error': '文件缺失'}
    prompt = ('给这一章写 100 字摘要：只写发生了什么，不评价、不抒情。\n'
              '输出格式严格两行：\n'
              '### %s <章标题>\n<100字摘要>\n'
              '不要输出别的。\n\n本章正文：\n%s' % (stem[:3], chapter_text[:8000]))
    block = strip_fence(ask(prompt, max_tokens=500))
    if not block.startswith('###'):
        return {'ledger': '章节摘要.md', 'ok': False, 'error': '模型没给摘要块'}
    lines = cur.split('\n')
    head_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith('### %s' % stem[:3]):
            head_idx = i
            break
    if head_idx is not None:
        end = head_idx + 1
        while end < len(lines) and not lines[end].startswith('###') and not lines[end].startswith('## '):
            end += 1
        new_lines = lines[:head_idx] + block.split('\n') + [''] + lines[end:]
    else:
        anchor = next((i for i, ln in enumerate(lines) if ln.startswith('## 卷摘要')), len(lines))
        new_lines = lines[:anchor] + block.split('\n') + [''] + lines[anchor:]
    return {'ledger': '章节摘要.md', 'ok': True, 'old': cur, 'new': '\n'.join(new_lines)}


def upd_foreshadow(book, chapter_text, stem, dry):
    p = cfg_path(book, '伏笔.md')
    cur = read(p)
    if not cur:
        return {'ledger': '伏笔.md', 'ok': False, 'error': '文件缺失'}
    prompt = ('看本章正文，列出伏笔变化。只输出指令行，每行一条，没有变化就输出 NO_CHANGES：\n'
              'ADD | 编号留空由人补 | 内容一句话 | 建议回收位置（可空）\n'
              'CLOSE | 要收的编号 | 收的方式一句话\n\n本章正文：\n%s' % chapter_text[:6000])
    out = strip_fence(ask(prompt, max_tokens=600))
    if 'NO_CHANGES' in out:
        return {'ledger': '伏笔.md', 'ok': True, 'ops': [], 'old': cur, 'new': cur}
    ops = [l.strip() for l in out.splitlines() if '|' in l and ('ADD' in l.upper() or 'CLOSE' in l.upper())]
    # 一章最多登记 3 条新伏笔：账本不能被灌爆
    adds = [o for o in ops if o.upper().startswith('ADD')]
    ops = [o for o in ops if not o.upper().startswith('ADD')] + adds[:3]
    if not ops:
        return {'ledger': '伏笔.md', 'ok': True, 'ops': [], 'old': cur, 'new': cur}
    lines = cur.split('\n')
    added = []
    for op in ops:
        kind = op.split('|')[0].strip().upper()
        parts = [x.strip() for x in op.split('|')]
        if kind == 'ADD':
            content = parts[2] if len(parts) > 2 else ''
            suggest = parts[3] if len(parts) > 3 else ''
            num = 'F%02d' % (len([l for l in lines if re.match(r'\| F\d+ \|', l.strip())]) + 1)
            # 2026-11-08：改成 8 列（权重/层级/回收目标），否则自动登记的伏笔拿不到权重，
            # 完结可行性就只能回退到「强度映射」口径。
            # 默认值：权重 5（中号）、层级 支线、回收目标留空（等作者填）。
            row = '| %s | %s | %s | 悬着 | 5 | 支线 |  | %s |' % (
                num, stem[:3], content or '（未说明）', suggest or '待定')
            idx = next((i for i, ln in enumerate(lines) if ln.strip().startswith('| F')), None)
            if idx is None:
                continue
            last = idx
            while last + 1 < len(lines) and lines[last + 1].strip().startswith('|'):
                last += 1
            lines.insert(last + 1, row)
            added.append(row)
        elif kind == 'CLOSE':
            num = parts[1] if len(parts) > 1 else ''
            how = parts[2] if len(parts) > 2 else ''
            for i, ln in enumerate(lines):
                if ln.strip().startswith('| %s |' % num):
                    cells = [c.strip() for c in ln.strip().strip('|').split('|')]
                    if len(cells) >= 4:
                        cells[3] = '已收（%s，%s）' % (stem[:3], how or '未说明')
                        lines[i] = '| ' + ' | '.join(cells) + ' |'
                    break
    return {'ledger': '伏笔.md', 'ok': True, 'ops': ops, 'added': added,
            'old': cur, 'new': '\n'.join(lines)}


def upd_power(book, chapter_text, stem, dry):
    p = cfg_path(book, '力量体系.md')
    cur = read(p)
    if not cur:
        return {'ledger': '力量体系.md', 'ok': False, 'error': '文件缺失'}
    prompt = ('本章主角境界有没有变化？只输出一行表格行（列：章 | 境界 | 怎么升的 | 距上次升级），'
              '没有变化就输出 NO_CHANGES。不要解释。\n\n本章正文：\n%s' % chapter_text[:6000])
    out = strip_fence(ask(prompt, max_tokens=300))
    if 'NO_CHANGES' in out:
        return {'ledger': '力量体系.md', 'ok': True, 'row': None, 'old': cur, 'new': cur}
    row = next((l.strip() for l in out.splitlines() if l.strip().startswith('|')), '')
    if not row:
        return {'ledger': '力量体系.md', 'ok': True, 'row': None, 'old': cur, 'new': cur}
    lines = cur.split('\n')
    idx = next((i for i, ln in enumerate(lines) if ln.strip().startswith('| 001 ')), None)
    if idx is None:
        return {'ledger': '力量体系.md', 'ok': True, 'row': None, 'old': cur, 'new': cur}
    last = idx
    while last + 1 < len(lines) and lines[last + 1].strip().startswith('|'):
        last += 1
    lines.insert(last + 1, row)
    return {'ledger': '力量体系.md', 'ok': True, 'row': row, 'old': cur, 'new': '\n'.join(lines)}


# ---------------- 主流程 ----------------

def apply_result(res, book, dry):
    if not res.get('ok') or res.get('new') is None or res.get('old') == res.get('new'):
        return res
    name = res['ledger']
    p = cfg_path(book, name)
    if dry:
        diff = list(difflib.unified_diff(res['old'].split('\n'), res['new'].split('\n'),
                                         fromfile=name, tofile=name, lineterm='', n=1))
        res['diff'] = diff[:40]
        return res
    backup = p + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
    with open(backup, 'w', encoding='utf-8') as f:
        f.write(res['old'])
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(res['new'])
    os.replace(tmp, p)
    res['written'] = p
    res['backup'] = backup
    return res


def run(chapter_path, book, dry=True, model='deepseek-flash'):
    chapter_text = read(chapter_path)
    stem = os.path.splitext(os.path.basename(chapter_path))[0]
    no = re.match(r'(\d+)', stem)
    no = int(no.group(1)) if no else 0

    results = []
    st = upd_state(chapter_path, book, chapter_text, stem, dry)
    results.append({'ledger': '角色状态.md', 'ok': st.get('ok'), 'changed': st.get('changed'),
                    'error': st.get('error'), 'note': st.get('note', ''),
                    'old': read(cfg_path(book, '角色状态.md')),
                    'new': None})
    if st.get('ok') and st.get('changed'):
        # 用 update_state 的替换逻辑重放一次拿 new（dry 模式只给 changed 列表）
        tmp = US.update_one(chapter_path, book, dry_run=True)
        if tmp.get('preview'):
            results[-1]['new'] = tmp['preview']
        results[-1]['note'] = '角色状态变更：' + '、'.join(st.get('changed') or [])

    for fn, arg in ((upd_row, ('时间线.md', book, chapter_text, stem, no, 'timeline', dry)),
                    (upd_row, ('事件索引.md', book, chapter_text, stem, no, 'event', dry)),
                    (upd_summary, (book, chapter_text, stem, dry)),
                    (upd_foreshadow, (book, chapter_text, stem, dry)),
                    (upd_power, (book, chapter_text, stem, dry))):
        try:
            res = fn(*arg)
        except Exception as e:
            res = {'ledger': arg[0] if isinstance(arg[0], str) else '?', 'ok': False,
                   'error': '%s: %s' % (type(e).__name__, e)}
        results.append(apply_result(res, book, dry))
    return results


def run_l1_dedup(book, chapter_no):
    """写完账本后做一次 L1 冲突检测（不调模型就跳过，绝不瞎合并）。"""
    try:
        import l1_dedup as L1
        res = L1.run(book, chapter_no, apply=True)
        if not res.get('ok'):
            return {'error': res.get('error')}
        rep = res.get('report') or {}
        return {'skipped_detection': res.get('skipped_detection'),
                'store': len(rep.get('store', [])), 'update': rep.get('update', []),
                'merge': rep.get('merge', []), 'skip': len(rep.get('skip', [])),
                'sidecar': res.get('sidecar')}
    except Exception as e:
        return {'error': '%s: %s' % (type(e).__name__, e)}


def refresh_index_after_write(book):
    """账本写完后刷新索引，保持 revision 一致。"""
    try:
        import memory_index as MI
        MI.drop_cache(book)
        idx = MI.open_index(book, refresh=True)
        return {'revision': idx.revision}
    except Exception as e:
        return {'error': '%s: %s' % (type(e).__name__, e)}


def main():
    ap = argparse.ArgumentParser(description='更新六个账本')
    ap.add_argument('chapter')
    ap.add_argument('--book', required=True)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--model', default='deepseek-flash')
    ap.add_argument('--no-dedup', action='store_true', help='跳过 L1 冲突检测')
    ap.add_argument('--json', nargs='?', const='', default=None)
    args = ap.parse_args()
    res = run(args.chapter, args.book, dry=args.dry_run, model=args.model)
    if not args.dry_run:
        idx_info = refresh_index_after_write(args.book)
        print('索引已刷新：%s' % idx_info)
        if not args.no_dedup:
            import re as _re
            m = _re.match(r'(\d{1,4})', os.path.basename(args.chapter))
            l1 = run_l1_dedup(args.book, m.group(1) if m else '000')
            print('L1 冲突检测：%s' % l1)
    if args.json is not None:
        out = json.dumps(res, ensure_ascii=False, indent=2)
        if args.json:
            with open(args.json, 'w', encoding='utf-8') as f:
                f.write(out)
        else:
            print(out)
        return 0
    for r in res:
        head = '%-10s' % r.get('ledger')
        if not r.get('ok'):
            print(head, '失败:', r.get('error'))
            continue
        if r.get('diff'):
            print(head, '将修改（diff）：')
            for d in r['diff'][:12]:
                print('   ', d)
        elif r.get('ops'):
            print(head, '伏笔指令:', r.get('ops'))
        elif r.get('row'):
            print(head, '新行:', r['row'][:100])
        else:
            print(head, r.get('note') or '无变化')
    return 0


if __name__ == '__main__':
    sys.exit(main())
