# -*- coding: utf-8 -*-
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
lines = io.open(P, encoding="utf-8").read().split(chr(10))
# 5337 行（0-based 5336）是多出来的 ")"
idx = 5336
print("before:", repr(lines[idx-1]), repr(lines[idx]), repr(lines[idx+1]))
if lines[idx].strip() == ")":
    del lines[idx]
    io.open(TMP, "w", encoding="utf-8", newline="").write(chr(10).join(lines))
    os.replace(TMP, P)
    print("removed line 5337")
else:
    print("not the expected line")