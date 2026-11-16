# -*- coding: utf-8 -*-
"""给挂件加完结可行性。

2026-11-08 教训：上一版直接 open(p,"w")，写到一半报代理对错误，文件被清空。
现在一律先写 .tmp，成功后 os.replace；且不在源码里写 emoji 代理对。
"""
import io, os, sys

P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "nvl-dock__feasible" in s:
    print("ALREADY"); sys.exit(0)

# 1) 声明缓存
old = "\t\t\tlet data = null;"
i = s.find(old)
if i < 0:
    print("data anchor missing"); sys.exit(1)
s = s[:i + len(old)] + chr(10) + "\t\t\tlet feas = null;   // 完结可行性" + s[i + len(old):]

# 2) 渲染块（纯文本标记，不用 emoji）
anchor = "\t\t\t\troot.appendChild(sum);"
j = s.find(anchor, s.find("const sum = el("))
if j < 0:
    print("sum anchor missing"); sys.exit(1)

BLOCK = [
  "",
  "\t\t\t\t// 完结可行性：一眼看到这本书还能不能写完",
  "\t\t\t\tif (feas === null && data.book) {",
  "\t\t\t\t\tfeas = \"loading\";",
  "\t\t\t\t\tfetch(apiBase().replace(/\\/+$/, \"\") + \"/api/completion?book=\" + encodeURIComponent(data.book))",
  "\t\t\t\t\t\t.then(function (r) { return r.ok ? r.json() : null; })",
  "\t\t\t\t\t\t.then(function (j2) { feas = (j2 && j2.ok) ? j2.report : false; render(); })",
  "\t\t\t\t\t\t.catch(function () { feas = false; });",
  "\t\t\t\t}",
  "\t\t\t\tif (feas && feas !== \"loading\" && feas.verdict) {",
  "\t\t\t\t\tvar VB = { ok: \"\u5bbd\u88d5\", warn: \"\u504f\u7d27\", red: \"\u503a\u8d85\u4e86\",",
  "\t\t\t\t\t\tred_hard: \"\u4e25\u91cd\u8d85\", clean: \"\u65e0\u672a\u507f\",",
  "\t\t\t\t\t\tno_plan: \"\u672a\u5b9a\u8ba1\u5212\u7ae0\u6570\", invalid: \"\u8f93\u5165\u6709\u8bef\" };",
  "\t\t\t\t\tvar fl = el(\"div\", \"nvl-dock__sum nvl-dock__feasible\", \"\u5b8c\u7ed3\u53ef\u884c\u6027  \" + (VB[feas.verdict] || feas.verdict));",
  "\t\t\t\t\tif (feas.need != null && feas.remaining != null) {",
  "\t\t\t\t\t\tfl.textContent += \"  \u9700\" + Math.round(feas.need) + \"\u7ae0 / \u5269\" + feas.remaining + \"\u7ae0\";",
  "\t\t\t\t\t}",
  "\t\t\t\t\tif (feas.cuts && feas.cuts.length) {",
  "\t\t\t\t\t\tfl.textContent += \"  \u5fc5\u987b\u780d\" + feas.cuts.length + \"\u6761\";",
  "\t\t\t\t\t}",
  "\t\t\t\t\troot.appendChild(fl);",
  "\t\t\t\t}",
]
s = s[:j + len(anchor)] + chr(10).join(BLOCK) + s[j + len(anchor):]

# 3) 先写 tmp，成功后原子替换
io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("feasibility added, chars =", len(s))
