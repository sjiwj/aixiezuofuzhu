# -*- coding: utf-8 -*-
"""给 index.js 接上模式：section.text 条件化 + 工具按模式注册 + 两条路由

2026-11-08：先写 .tmp 再 os.replace（上次被清空的教训）
"""
import io, os, sys

P = r"D:\NovelApp\plugin\lib\index.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "novelapp-mode" in s:
    print("ALREADY"); sys.exit(0)

# 1) import
old_imp = "import fs from 'node:fs'"
if old_imp not in s:
    print("fs import missing"); sys.exit(1)
s = s.replace(old_imp, old_imp + chr(10) + "import * as MODE from './mode.js'", 1)

# 2) section.text 条件化
old_txt = "        text: () => SECTION_TEXT,"
if old_txt not in s:
    print("text anchor missing"); sys.exit(1)
new_txt = ("        // 通用模式不注入小说 prompt（每轮都调，切模式即时生效）" + chr(10) +
           "        text: () => (MODE.get() === 'writing' ? SECTION_TEXT : ''),")
s = s.replace(old_txt, new_txt, 1)

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("step1-2 done, chars =", len(s))
