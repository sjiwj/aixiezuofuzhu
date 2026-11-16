# -*- coding: utf-8 -*-
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "installAssistant" in s:
    print("ALREADY"); sys.exit(0)
COMP = open(r"D:\NovelApp\scripts\_asst_component.txt", encoding="utf-8").read()
ANCHOR = "\t\t/* \u8bbe\u7f6e \u2192 通用 → 关于与许可：MIT 声明 + 版本 + AI 标识说明 */"
i = s.find(ANCHOR)
if i < 0:
    print("anchor missing"); sys.exit(1)
s = s[:i] + COMP + s[i:]
io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("assistant component added")