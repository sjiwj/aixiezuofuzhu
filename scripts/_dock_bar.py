# -*- coding: utf-8 -*-
"""挂件改底部状态条：折叠时贴窗口底，一行摘要；展开时浮动卡片"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "nvl-dock nvl-dock--bar" in s:
    print("ALREADY"); sys.exit(0)

# 1) class 切换：折叠用 --bar
OLD = '''				root.style.display = "";
				// 状态栏形态：class 固定为 --bar，展开时内容用浮层（不撑高状态栏）
				root.className = open ? "nvl-dock nvl-dock--wide" : "nvl-dock";'''
NEW = '''				root.style.display = "";
				// 折叠 = 底部状态条（一行，不遮挡正文）；展开 = 浮动卡片
				root.className = open ? "nvl-dock nvl-dock--wide" : "nvl-dock nvl-dock--bar";'''
if OLD not in s:
    print("class anchor missing"); sys.exit(1)
s = s.replace(OLD, NEW, 1)

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("class switched to --bar when collapsed")