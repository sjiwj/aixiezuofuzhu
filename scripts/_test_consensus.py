# -*- coding: utf-8 -*-
"""端到端测 extract_consensus：三条假意见，看能不能分出 必改/待定/忽略。"""
import io, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))
import reviewers as RV

# 三条意见：两人提同一个问题（必改）、一人提独有问题（待定）、一人说空话（忽略）
results = [
    {'id': 'a1', 'label': '读者A', 'ok': True,
     'review': '第一段「上个月醒来在示例镇」之后直接跳到回忆，读者会不知道现在是什么时候。建议先给一个当下动作。'},
    {'id': 'b2', 'label': '编辑B', 'ok': True,
     'review': '开头的时间线跳跃太大。「上个月」「上上个月」连着两句，读者容易划走。建议压成一句。'},
    {'id': 'c3', 'label': '第三家', 'ok': True,
     'review': '节奏略慢，人物不够丰满，建议加个反转。'},
]
out = RV.extract_consensus(results)
print(json.dumps(out, ensure_ascii=False, indent=2)[:1600])
print("")
if out.get('ok'):
    print("必改:", len(out.get('must_fix') or []))
    print("待定:", len(out.get('pending') or []))
    print("忽略:", len(out.get('ignored') or []))
    for it in (out.get('must_fix') or []):
        print("  [必改]", it.get('issue'))
    for it in (out.get('ignored') or []):
        print("  [忽略]", it.get('reason'))
