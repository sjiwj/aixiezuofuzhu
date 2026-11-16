# -*- coding: utf-8 -*-
"""严重度分层：风格类降 warn，结构类保持 error。"""
import io, sys
p = r"D:\NovelApp\scripts\l1_l2_check.py"
s = io.open(p, encoding="utf-8").read()
changed = []

# 破折号 / 阿拉伯数字：纯排版风格，降 warn（来源：平台排版规范，不是文学标准）
for rule, why in (("dash_count", "破折号"), ("arabic_number", "阿拉伯数字")):
    old = 'issues.append({"rule": "%s", "severity": "error",' % rule
    new = 'issues.append({"rule": "%s", "severity": "warn",   # 风格类：降 warn（见 docs/quality/规则来源.md）' % rule
    if old in s:
        s = s.replace(old, new, 1)
        changed.append(rule)

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("downgraded:", changed)