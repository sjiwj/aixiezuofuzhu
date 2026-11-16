# -*- coding: utf-8 -*-
"""顶栏精简：统计行只留字数（详情放 title），场景标签缩短，模型名缩短"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
changed = []

# 1) 统计行：3271-3272 那处（带 lines）
OLD1 = '''					h("span", { className: "nvl-editor__stat" },
						stats.cjk + " \u6c49\u5b57 \u00b7 " + stats.chars + " \u5b57\u7b26 \u00b7 " + stats.paragraphs + " \u6bb5 \u00b7 " + stats.lines + " \u884c"),'''
NEW1 = '''					h("span", { className: "nvl-editor__stat", title: stats.cjk + " \u6c49\u5b57 \u00b7 " + stats.chars + " \u5b57\u7b26 \u00b7 " + stats.paragraphs + " \u6bb5 \u00b7 " + stats.lines + " \u884c" },
						stats.cjk + " \u5b57"),'''
if OLD1 in s:
    s = s.replace(OLD1, NEW1, 1); changed.append("stat-with-lines")

# 2) 另一处（不带 lines）
OLD2 = 'h("span", { className: "nvl-editor__stat" }, stats.cjk + " \u6c49\u5b57 \u00b7 " + stats.chars + " \u5b57\u7b26 \u00b7 " + stats.paragraphs + " \u6bb5"),'
NEW2 = 'h("span", { className: "nvl-editor__stat", title: stats.cjk + " \u6c49\u5b57 \u00b7 " + stats.chars + " \u5b57\u7b26 \u00b7 " + stats.paragraphs + " \u6bb5" }, stats.cjk + " \u5b57"),'
if OLD2 in s:
    s = s.replace(OLD2, NEW2, 1); changed.append("stat-plain")

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("changed:", changed)