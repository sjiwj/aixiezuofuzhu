# -*- coding: utf-8 -*-
"""码字面板改成「主区 + 右栏 320px」，照 blog-sidebar 的配色和组件。"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "nvl-side" in s:
    print("ALREADY"); sys.exit(0)

# 在 buildPane 的最后（正文 body 之后）找不到简单锚点，改为：在 pane 打开处插入右栏
ANCHOR = 'const buildPane = function () { return h("div", { className: "nvl nvl-pane" },'
if ANCHOR not in s:
    print("anchor missing"); sys.exit(1)

SIDE = '''const buildPane = function () { return h("div", { className: "nvl nvl-pane nvl-pane--split" },'''
s = s.replace(ANCHOR, SIDE, 1)

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("pane -> split")