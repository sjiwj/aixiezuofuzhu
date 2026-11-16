# -*- coding: utf-8 -*-
"""完结可行性 —— 命令行入口

用法:
    python scripts/completion_feasibility.py --book <书名>
    python scripts/completion_feasibility.py --book <书名> --planned 120
    python scripts/completion_feasibility.py --book <书名> --json
    python scripts/completion_feasibility.py --explain          # 只看强度数值化方案

退出码:
    0  宽裕 / 偏紧 / 无债务 / 缺计划章数（有结论或明确说明缺什么）
    1  红灯（N' > N，需要砍承诺）
    2  输入有误（书不存在 / 计划章数小于已写章数 / 参数非法）

只读：本脚本不写任何文件，不改承诺表，不碰客户数据。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'core'))

import completion  # noqa: E402

EXPLAIN = """=== 强度数值化方案（把定性变成可算的东西）===

  强度    点数    兑付成本（系数 3.0）   依据
  高       3      9 章                  core/promises.py DEBT_THRESHOLD=10（节奏债阈值 10 章）
  中       2      6 章                  产品说明书「伏笔埋超 5 章会提醒」→ 6 章略过提醒线
  低       1      3 章                  黄金三章：最弱的一条最多占掉开篇三章的量

  存量  M  = Σ 点数（状态「进行」的承诺）
  速率  k  = Σ 点数（状态「已兑付」） / 已写章数        单位：点/章
  换算 cpp = 1 / k（有历史）；= 3.0 章/点（k = 0 时退化为成本模型，结果标 [估算]）
  需要 N'  = M × cpp
  剩余 N   = 计划章数 - 已写章数
  N' > N   → 红灯，按「强度低 → 最后推进章早」砍到够为止

  不需要作者重填任何字段：强度 / 状态 / 可推进卷 / 最后推进章 全在现有 front matter 里，
  计划章数与卷起止从 大纲/*.md 读（「共约 480 章」+ 卷五（361–480））。
"""


def main():
    ap = argparse.ArgumentParser(description='完结可行性：剩余章节够不够还完承诺账')
    ap.add_argument('--book', default=None, help='书名（projects 下的目录名）')
    ap.add_argument('--planned', type=int, default=None, help='作者声明的计划章数')
    ap.add_argument('--factor', type=float, default=None,
                    help='强度点→章 的系数（默认 %.1f，仅在无历史速率时起作用）'
                         % completion.COST_FACTOR)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--explain', action='store_true', help='只打印强度数值化方案')
    a = ap.parse_args()

    if a.explain:
        sys.stdout.write(EXPLAIN)
        return 0
    if not a.book:
        ap.error('--book 必填（或用 --explain 看方案）')
    if a.planned is not None and a.planned <= 0:
        print('--planned 必须是正整数，收到 %d' % a.planned)
        return 2

    r = completion.analyze(a.book, planned=a.planned, factor=a.factor)

    if a.json:
        slim = {k: v for k, v in r.items() if k not in ('unpaid', 'paid', 'voided', 'weird', 'cuts',
                                                        'promises', 'overdue')}
        slim['promises'] = r.get('promises', [])
        slim['cuts'] = [{'id': p['id'], 'title': p['title'], 'strength': p['strength'],
                         'points': p['points'], 'last_touch': p['last_touch'],
                         'deadline': p['deadline']} for p in r.get('cuts', [])]
        slim['overdue'] = [p['id'] for p in r.get('overdue', [])]
        print(json.dumps(slim, ensure_ascii=False, indent=1, default=str))
        return 0 if r.get('verdict') != 'red' and r.get('verdict') != 'red_hard' else 1

    sys.stdout.write(completion.report(r))

    v = r.get('verdict')
    if not r.get('exists'):
        return 2
    if v in ('invalid',):
        return 2
    if v in ('red', 'red_hard'):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
