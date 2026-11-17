#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""triage 分诊回归（v1.0.1 第 4 项配套）。

钉住两件事：
  1) 四类（bug / env / quality / feature）各判得对；
  2) issue 模板里的「## 环境」小节不参与分类 ——
     否则任何带网关/Python 版本的 bug 都会被误判成 env（issue-0001 实测踩到）。

用法：python scripts/_verify_triage.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import triage as T   # noqa: E402

CASES = [
    ('bug', '复现步骤\n1. 起服务\n2. curl http://127.0.0.1:8770/api/x\n'
            '报错 Traceback (most recent call last)\npython 3.15'),
    ('env', '装不上，ModuleNotFoundError: No module named webview，起不来，白屏'),
    ('quality', '读不下去，人物像复制粘贴，对话太少，AI味重'),
    ('feature', '希望支持一下导出 epub，能不能加个按钮'),
    ('bug', '## 环境\n- 网关：自建 new-api\n- Python 版本：3.15.1\n\n'
            '## 复现步骤\n1. curl http://127.0.0.1:8770/api/x\n\n'
            '## 期望 vs 实际\n- 实际：报错 HTTP 200 但字段缺失'),
]


def main():
    bad = 0
    for expect, text in CASES:
        cat, score = T.classify(text)
        ok = cat == expect
        bad += 0 if ok else 1
        print('%s  expect=%-8s got=%-8s scores=%s' % ('PASS' if ok else 'FAIL', expect, cat, score))

    # 环境段必须被剔除
    _, s = T.classify(CASES[4][1])
    ok = (s['env'] == 0 and s['bug'] > 0)
    bad += 0 if ok else 1
    print('%s  环境段剔除后 env=%d bug=%d' % ('PASS' if ok else 'FAIL', s['env'], s['bug']))

    # repro_ready 三要素
    ready, missing = T.repro_ready('复现步骤 curl http://x Traceback python 3.15.1')
    ok = ready and not missing
    bad += 0 if ok else 1
    print('%s  三要素齐 -> repro_ready=True' % ('PASS' if ok else 'FAIL'))
    ready2, missing2 = T.repro_ready('就是不好用')
    ok2 = (not ready2) and len(missing2) == 3
    bad += 0 if ok2 else 1
    print('%s  三要素缺 -> repro_ready=False missing=%s' % ('PASS' if ok2 else 'FAIL', missing2))

    print('\n结果: %s（失败 %d）' % ('PASS' if not bad else 'FAIL', bad))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
