# -*- coding: utf-8 -*-
"""伏笔 DAG 校验 —— 无环 / 有向 / 可达

照 OpenWrite skills/foreshadowing-system 的三条硬规则实现（只学设计，不抄代码）：

    1 无环   伏笔之间不能循环依赖
    2 有向   边必须从伏笔指向回收点（arc_NNN / sec_NNN / ch_NNN），或指向表内另一个伏笔
    3 可达   每个「待收」伏笔必须能追到一个明确的回收章（ch_NNN，或经依赖链追到）

边的来源（不用另建图文件，全部来自伏笔表本身）：
    回收目标列里写另一个伏笔编号（如 F02）  -> 依赖边 F01 → F02（F01 要等 F02 先收）
    回收目标列里写 ch_015 / arc_002 / sec_003 -> 回收点边（叶子）
    写「待定」「卷七」这类 -> 非法边（不是回收点，也接不上任何节点）

用法：
    python scripts/foreshadow_dag.py --book <书名>
    python scripts/foreshadow_dag.py --book <书名> --json
    python scripts/foreshadow_dag.py --book-dir "C:\\...\\projects\\_foreshadowtest"   # 测试副本

退出码：
    0  三条规则全过（无环 + 无非法边 + 待收都可达）
    1  有环 / 有非法边或悬空依赖 / 有待收不可达
    2  输入有误（书不存在 / 没有 设定库/伏笔.md）

只读：本脚本不写任何文件。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import l3_l4_check as fs   # noqa: E402  伏笔表解析只留一份，避免两个口径各走各的

# 孤立节点阈值：权重 >= 7 的伏笔没人依赖、也不依赖别人 —— 可能是漏收的主线
ISOLATED_WEIGHT = 7


def projects_root():
    """与 core/promises._projects_root 同一套优先级（NOVELAPP_PROJECTS > NOVELAPP_DATA > APPDATA）。"""
    p = os.environ.get('NOVELAPP_PROJECTS')
    if p:
        return os.path.abspath(p)
    d = os.environ.get('NOVELAPP_DATA')
    if d:
        return os.path.join(os.path.abspath(d), 'projects')
    appdata = os.environ.get('APPDATA')
    if appdata:
        return os.path.join(appdata, 'novelapp-desktop', 'data', 'projects')
    return os.path.join(os.path.dirname(HERE), 'projects')


def _norm_cycle(cyc):
    """环的规范形（从最小元素开始，便于去重）：[F01,F02,F01] -> (F01,F02,F01)"""
    body = list(cyc[:-1])
    if not body:
        return tuple(cyc)
    k = min(range(len(body)), key=lambda i: body[i])
    return tuple(body[k:] + body[:k] + [body[k]])


def find_cycles(ids, out):
    """DFS 找回边，返回去重后的环路径列表（每条闭环：首尾同节点）。

    同一强连通分量里若有多个环，只报 DFS 走到的那些 —— 够用（报一个就能改），
    不追求枚举全部初等环。
    """
    color = {i: 0 for i in ids}          # 0 未访问 / 1 在栈上 / 2 已结束
    cycles, seen = [], set()
    for root in ids:
        if color.get(root):
            continue
        color[root] = 1
        path = [root]
        stack = [(root, iter(out.get(root, [])))]
        while stack:
            u, it = stack[-1]
            pushed = False
            for v in it:
                if v not in color:
                    continue                 # 悬空编号不参与环判定（另有「有向」报）
                if color[v] == 0:
                    color[v] = 1
                    path.append(v)
                    stack.append((v, iter(out.get(v, []))))
                    pushed = True
                    break
                if color[v] == 1:            # 回边 = 环
                    cyc = path[path.index(v):] + [v]
                    key = _norm_cycle(cyc)
                    if key not in seen:
                        seen.add(key)
                        cycles.append(list(cyc))
            if pushed:
                continue
            color[u] = 2
            stack.pop()
            path.pop()
    return cycles


def topo_order(ids, out):
    """依赖在前（先收被依赖的）。有环返回 None。"""
    dep = {i: len([r for r in out.get(i, []) if r in out]) for i in ids}
    users = {i: [] for i in ids}
    for i in ids:
        for r in out.get(i, []):
            if r in users:
                users[r].append(i)
    ready = sorted([i for i in ids if dep[i] == 0])
    order = []
    while ready:
        u = ready.pop(0)
        order.append(u)
        for w in users[u]:
            dep[w] -= 1
            if dep[w] == 0:
                ready.append(w)
        ready.sort()
    return order if len(order) == len(ids) else None


def reachable_chapters(node_id, by_id):
    """沿依赖边走，能追到的 ch 目标章 + 走过的节点。"""
    seen, stack, chs = set(), [node_id], []
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        n = by_id.get(cur)
        if not n:
            continue
        chs.extend(n['chapters'])
        stack.extend(n['refs'])
    return sorted(set(chs)), seen


def analyze(book, book_dir):
    nodes, meta = fs.load_foreshadow(book_dir)
    ids = [n['id'] for n in nodes]
    by_id = {n['id']: n for n in nodes}
    out = {i: [r for r in by_id[i]['refs'] if r in by_id] for i in ids}

    cycles = find_cycles(ids, out)
    topo = topo_order(ids, out) if not cycles else None

    edge_count = sum(len(v) for v in out.values())
    residue_count = sum(len(n['residue']) for n in nodes)

    # 有向：非法回收点 + 悬空编号
    illegal = []
    for n in nodes:
        for tok in n['unknown_targets']:
            illegal.append({'from': n['id'], 'to': tok, 'kind': 'not_a_target',
                            'why': '不是 arc_NNN/sec_NNN/ch_NNN，也不是表内伏笔编号'})
        for tok in n['dangling']:
            illegal.append({'from': n['id'], 'to': tok, 'kind': 'dangling',
                            'why': '长得像伏笔编号，但伏笔表里没有这个编号'})

    # 可达：只看「待收」
    unreachable, partial_reach = [], []
    for n in nodes:
        if n['status'] != '待收':
            continue
        chs, seen = reachable_chapters(n['id'], by_id)
        if chs:
            continue
        if n['residue']:
            partial_reach.append({'id': n['id'], 'targets': n['residue'],
                                  'why': '只有卷/节级回收目标，没有 ch_NNN'})
        else:
            unreachable.append({'id': n['id'], 'why': '回收目标为空或不是回收点',
                                'target_raw': n['target_raw']})

    # 孤立节点：没人依赖它（入度 0）、它也不依赖别人（出度 0）、权重 >= 7
    isolated = []
    for n in nodes:
        if n['status'] in fs.FS_STATUS_CLOSED or n['status'] in fs.FS_STATUS_VOID:
            continue
        if out.get(n['id']):
            continue
        if any(n['id'] in out.get(o, []) for o in ids):
            continue
        if n['weight'] >= ISOLATED_WEIGHT:
            isolated.append({'id': n['id'], 'weight': n['weight'], 'layer': n['layer'],
                             'buried': n['buried'], 'content': n['content'],
                             'target_raw': n['target_raw']})

    notes = []
    if not meta['exists']:
        notes.append('没有 设定库/伏笔.md')
    elif meta['legacy']:
        notes.append('本表是旧格式（无 权重/层级/回收目标 列）：'
                     '层级按「支线」、权重按 5，DAG 只有 0 条边 —— 补上「回收目标」列才有意义')
    if not nodes:
        notes.append('伏笔表没有数据行')

    return {
        'book': book,
        'book_dir': book_dir,
        'foreshadow_path': meta['path'],
        'columns': meta['columns'],
        'legacy': meta['legacy'],
        'nodes': [{
            'id': n['id'], 'status': n['status'], 'weight': n['weight'],
            'weight_default': n['weight_default'], 'layer': n['layer'],
            'layer_default': n['layer_default'], 'buried': n['buried'],
            'content': n['content'], 'target_raw': n['target_raw'],
            'refs': n['refs'], 'residue': n['residue'],
            'dangling': n['dangling'], 'unknown_targets': n['unknown_targets'],
            'chapters': n['chapters'],
        } for n in nodes],
        'node_count': len(nodes),
        'edge_count': edge_count,
        'residue_count': residue_count,
        'cycles': cycles,
        'topo': topo,
        'illegal_edges': illegal,
        'unreachable': unreachable,
        'partial_reach': partial_reach,
        'isolated': isolated,
        'notes': notes,
        'ok': not cycles and not illegal and not unreachable and not partial_reach,
    }


def _fmt_target(n):
    parts = []
    for lvl, no in n['residue']:
        parts.append('%s_%03d' % (lvl, no))
    for r in n['refs']:
        parts.append(r)
    for tok in n['dangling']:
        parts.append(tok + '(悬空)')
    for tok in n['unknown_targets']:
        parts.append(tok)
    return '/'.join(parts)


def report(r):
    L = []
    L.append('=== 伏笔 DAG ·《%s》===' % r['book'])
    L.append('表      %s' % r['foreshadow_path'])
    if r['columns']:
        if r['legacy']:
            note = '旧格式，缺列取默认值'
        elif len(r['columns']) < 8:
            note = '新格式 %d 列，缺的列取默认值' % len(r['columns'])
        else:
            note = '新格式 8 列'
        L.append('列      %s（%s）' % ('|'.join(r['columns']), note))
    L.append('节点 %d   依赖边 %d   回收点 %d'
             % (r['node_count'], r['edge_count'], r['residue_count']))
    L.append('')

    # 1 无环
    L.append('-- 1. 无环 --')
    if not r['cycles']:
        L.append('  通过：%d 个节点没有循环依赖' % r['node_count'])
    else:
        L.append('  失败：找到 %d 个环' % len(r['cycles']))
        for i, cyc in enumerate(r['cycles'], 1):
            L.append('    环 %d  %s' % (i, ' → '.join(cyc)))
    L.append('')

    # 2 有向
    L.append('-- 2. 有向 --')
    if not r['illegal_edges']:
        if r['edge_count'] == 0 and r['residue_count'] == 0:
            L.append('  通过：没有写任何回收目标（没有边，也就没有非法边）')
        else:
            L.append('  通过：%d 条依赖边都指向表内伏笔，%d 个回收点都是 arc/sec/ch'
                     % (r['edge_count'], r['residue_count']))
    else:
        L.append('  失败：%d 条边接不上回收点' % len(r['illegal_edges']))
        for e in r['illegal_edges']:
            L.append('    %s → 「%s」  %s' % (e['from'], e['to'], e['why']))
    L.append('')

    # 3 可达
    L.append('-- 3. 可达 --')
    waiting = [n for n in r['nodes'] if n['status'] == '待收']
    if not waiting:
        L.append('  通过：没有「待收」伏笔（这一条没有可判对象）')
    elif not r['unreachable'] and not r['partial_reach']:
        L.append('  通过：%d 条「待收」都能追到明确回收章' % len(waiting))
    else:
        for u in r['unreachable']:
            L.append('  失败：%s 标了「待收」，但没有回收目标（原文「%s」）'
                     % (u['id'], u.get('target_raw') or ''))
        for u in r['partial_reach']:
            L.append('  失败：%s 标了「待收」，只有卷/节级目标，没有 ch_NNN' % u['id'])
    L.append('')

    # 孤立节点
    L.append('-- 孤立节点（权重 >= %d，没人依赖、也不依赖别人）--' % ISOLATED_WEIGHT)
    if not r['isolated']:
        L.append('  无')
    else:
        L.append('  可能是漏收的主线，逐个确认：')
        for n in r['isolated']:
            L.append('    · %s  %s/%d  埋 %03d「%s」  回收目标 %s'
                     % (n['id'], n['layer'], n['weight'], n['buried'],
                        n['content'][:18], n['target_raw'] or '（空）'))
    L.append('')

    # 拓扑序
    L.append('-- 拓扑序（依赖在前 = 建议先收）--')
    if r['topo'] is None:
        L.append('  有环，排不出拓扑序（先拆环）')
    elif not r['topo']:
        L.append('  （没有节点）')
    else:
        seq = []
        for pid in r['topo']:
            n = next(x for x in r['nodes'] if x['id'] == pid)
            tgt = _fmt_target(n)
            seq.append('%s（%s）' % (pid, tgt) if tgt else pid)
        L.append('  ' + ' → '.join(seq))
        # 按最早回收章给一个可执行顺序（有 ch 目标的排前面，同章按权重降序）
        def key(pid):
            n = next(x for x in r['nodes'] if x['id'] == pid)
            return (min(n['chapters']) if n['chapters'] else 10 ** 6, -n['weight'], pid)
        ordered = sorted(r['topo'], key=key)
        L.append('  按回收章排序：' + ' → '.join(ordered))
    L.append('')

    if r['notes']:
        L.append('-- 备注 --')
        for n in r['notes']:
            L.append('  · ' + n)
        L.append('')

    L.append('结论  %s' % ('通过（无环 / 有向 / 可达）' if r['ok'] else '不通过，看上面标「失败」的行'))
    return '\n'.join(L) + '\n'


def main():
    ap = argparse.ArgumentParser(description='伏笔 DAG 校验：无环 / 有向 / 可达')
    ap.add_argument('--book', default=None, help='书名（projects 下的目录名）')
    ap.add_argument('--book-dir', default=None, help='直接给书目录（测试副本用）')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    if a.book_dir:
        book_dir = os.path.abspath(a.book_dir)
        book = os.path.basename(book_dir.rstrip('\\/'))
    elif a.book:
        book = a.book
        book_dir = os.path.join(projects_root(), book)
    else:
        ap.error('要给 --book 或 --book-dir')

    if not os.path.isdir(book_dir):
        print('找不到书目录：%s' % book_dir)
        return 2
    fv = os.path.join(book_dir, '设定库', '伏笔.md')
    if not os.path.exists(fv):
        print('没有伏笔表：%s' % fv)
        return 2

    r = analyze(book, book_dir)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        sys.stdout.write(report(r))
    return 0 if r['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
