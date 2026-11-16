# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\scripts\oldbook_diagnose.py"
s = io.open(p, encoding="utf-8").read()
# 阈值：全书出现 >=4 章 且 总次数 >=5 —— 碎片很难同时满足
old = "    per = [(no, fn, set(n for n in names if freq.get(n, 0) >= 2)) for no, fn, names in per]"
if old not in s:
    print("anchor missing"); raise SystemExit(1)
new = ("    # 阈值：至少出现在 4 个不同章节（碎片很难跨这么多章）\n"
       "    per = [(no, fn, set(n for n in names if freq.get(n, 0) >= 4)) for no, fn, names in per]")
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("threshold -> 4 chapters")