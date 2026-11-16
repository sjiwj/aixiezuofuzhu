# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\scripts\oldbook_diagnose.py"
s = io.open(p, encoding="utf-8").read()
if "freq.get(n, 0) >= 2" in s:
    print("ALREADY"); raise SystemExit
old = '    if len(per) < 3:'
i = s.find(old)
if i < 0:
    print("anchor missing"); raise SystemExit(1)
j = s.find("\n", s.find("\n", i) + 1)  # 跳过 if 行与 return 行
ins = [
    "",
    "    # 全书频率：只在全书出现 >=2 次的说话人才算候选（单章 1 次也算）",
    "    freq = {}",
    "    for _no, _fn, names in per:",
    "        for n in names:",
    "            freq[n] = freq.get(n, 0) + 1",
    "    per = [(no, fn, set(n for n in names if freq.get(n, 0) >= 2)) for no, fn, names in per]",
]
s = s[:j] + "\n".join(ins) + s[j:]
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("freq filter inserted")