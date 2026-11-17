#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""issue 关单记录器：把一个已处理的 issue 写进错题本（三循环第一环）。

调用方是 scripts/_issue_pipeline.ps1 —— 每次「先红 → 改 → 转绿 → 自检」走完，
就把这条 issue 的根因记一笔。同类（category 归一化后相同）累计到 3 次，
loop_log.proposals() 会给出「升级为硬门禁」的提案，避免第 4 次还从零查。

用法：
  python scripts/_issue_recorder.py --subject "issue:entries" --category bug --message "发布包过期未报"

输出（单行 JSON）：
  {"count": 1, "strengthened": false}       strengthened=true 表示已达 3 次、出提案
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'core'))

import loop_log as LL          # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--subject', required=True, help='如 issue:entries')
    ap.add_argument('--category', required=True, help='triage 判定的类别：bug/env/quality/feature')
    ap.add_argument('--message', required=True, help='一句话根因（归一化后用作去重键）')
    ap.add_argument('--cycle', default='fix', help='默认 fix')
    a = ap.parse_args()

    r = LL.record(a.subject, a.category, a.message, cycle=a.cycle)
    print(json.dumps(r, ensure_ascii=False))
    if r.get('strengthened'):
        print('PROPOSAL_READY=1')
    return 0


if __name__ == '__main__':
    sys.exit(main())
