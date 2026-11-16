# -*- coding: utf-8 -*-
import io, sys
p = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
s = io.open(p, encoding="utf-8").read()
if "InspireBox" in s:
    print("ALREADY"); sys.exit(0)

COMP = open(r"D:\NovelApp\scripts\_inspire_component.txt", encoding="utf-8").read()

anchor = "\t\t/* \u8bbe\u7f6e \u2192 \u901a\u7528 \u2192 \u7528\u91cf\u4e0e\u82b1\u8d39\uff1a\u8bfb data/usage.jsonl \u7684\u672c\u673a\u8bb0\u8d26 */"
i = s.find(anchor)
if i < 0:
    print("anchor missing"); sys.exit(1)
s = s[:i] + COMP + s[i:]
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("InspireBox added")