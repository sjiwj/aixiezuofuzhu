# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
s = io.open(p, encoding="utf-8").read()
if "nvl-dock__feasible" in s:
    print("ALREADY"); raise SystemExit

# 1) 声明 completion 缓存（data 声明旁边）
old = "\t\t\tlet data = null;"
i = s.find(old)
if i < 0:
    print("data anchor missing"); raise SystemExit(1)
s = s[:i] + old + chr(10) + "\t\t\tlet feas = null;          // \u5b8c\u7ed3\u53ef\u884c\u6027\uff08\u62c9\u4e00\u6b21\uff0c\u6362\u4e66\u6e05\u7a7a\uff09" + s[i+len(old):]

# 2) 渲染：插在 root.appendChild(sum) 之后
old2 = "\t\t\t\troot.appendChild(sum);"
j = s.find(old2, s.find("const sum = el("))
if j < 0:
    print("sum anchor missing"); raise SystemExit(1)

BLOCK = [
  "\t\t\t\t// \u5b8c\u7ed3\u53ef\u884c\u6027\uff1a\u4e00\u773c\u770b\u5230\u8fd9\u672c\u4e66\u8fd8\u80fd\u4e0d\u80fd\u5199\u5b8c",
  "\t\t\t\tif (feas === null && data.book) {",
  "\t\t\t\t\tfeas = \"loading\";",
  "\t\t\t\t\tfetch(apiBase().replace(/\\/+$/, \"\") + \"/api/completion?book=\" + encodeURIComponent(data.book))",
  "\t\t\t\t\t\t.then(function (r) { return r.ok ? r.json() : null; })",
  "\t\t\t\t\t\t.then(function (j2) { feas = (j2 && j2.ok) ? j2.report : false; render(); })",
  "\t\t\t\t\t\t.catch(function () { feas = false; });",
  "\t\t\t\t}",
  "\t\t\t\tif (feas && feas !== \"loading\" && feas.verdict) {",
  "\t\t\t\t\tvar VB = { ok: \"\u2705 \u5bbd\u88d5\", warn: \"\u26a0\ufe0f \u504f\u7d27\", red: \"\ud83d\udd34 \u503a\u8d85\u4e86\",",
  "\t\t\t\t\t\tred_hard: \"\ud83d\udd34 \u4e25\u91cd\u8d85\", clean: \"\u2705 \u65e0\u672a\u507f\",",
  "\t\t\t\t\t\tno_plan: \"\u00b7 \u672a\u5b9a\u8ba1\u5212\u7ae0\u6570\", invalid: \"\u00b7 \u8f93\u5165\u6709\u8bef\" };",
  "\t\t\t\t\tvar line = el(\"div\", \"nvl-dock__sum nvl-dock__feasible\", \"\u5b8c\u7ed3\u53ef\u884c\u6027  \" + (VB[feas.verdict] || feas.verdict));",
  "\t\t\t\t\tif (feas.need != null && feas.remaining != null) {",
  "\t\t\t\t\t\tline.textContent += \"  \u9700\" + Math.round(feas.need) + \"\u7ae0 / \u5269\" + feas.remaining + \"\u7ae0\";",
  "\t\t\t\t\t}",
  "\t\t\t\t\tif (feas.cuts && feas.cuts.length) {",
  "\t\t\t\t\t\tline.textContent += \"  \u5fc5\u987b\u780d\" + feas.cuts.length + \"\u6761\";",
  "\t\t\t\t\t}",
  "\t\t\t\t\troot.appendChild(line);",
  "\t\t\t\t}",
]
s = s[:j+len(old2)] + chr(10) + chr(10).join(BLOCK) + s[j+len(old2):]

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("feasibility line added to dock")