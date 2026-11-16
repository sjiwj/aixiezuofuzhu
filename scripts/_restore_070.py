# -*- coding: utf-8 -*-
"""从 client.js 切回 070-body.js（删除前的完整版）。"""
import io, os, sys

CLIENT = r"D:\NovelApp\_tmp\c41.js"
OUT = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"

s = io.open(CLIENT, encoding="utf-8").read()
print("client len:", len(s))

# 070 的起点：		/* 端点族（backend 实测，2026-11-06）
START_MARK = "\n\t\t/* \u7aef\u70b9\u65cf\uff08backend \u5b9e\u6d4b\uff0c2026-11-06\uff09"
i = s.find(START_MARK)
print("start idx:", i)
if i < 0:
    print("start missing"); sys.exit(1)

# 99-footer 的起点：		exports.name = PLUGIN_NAME;
END_MARK = "\t\texports.name = PLUGIN_NAME;"
j = s.find(END_MARK, i)
print("end idx:", j)
if j < 0:
    print("end missing"); sys.exit(1)

body = s[i:j]
print("body len:", len(body), "lines:", body.count(chr(10)))

if len(body) < 200000:
    print("too short, abort"); sys.exit(1)

tmp = OUT + ".tmp"
io.open(tmp, "w", encoding="utf-8", newline="").write(body)
os.replace(tmp, OUT)
print("restored")