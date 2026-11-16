# -*- coding: utf-8 -*-
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
lines = io.open(P, encoding="utf-8").read().split(chr(10))

i = None
for idx, ln in enumerate(lines):
    if ln.strip() == "function initTheme() {":
        i = idx; break
if i is None:
    print("missing"); sys.exit(1)
j = i
while lines[j].strip() != "}":
    j += 1

NEW = [
    "\t\tfunction initTheme() {",
    "\t\t\t/* LOCKED_LIGHT: \u56fa\u5b9a\u6d45\u8272\u3002\u5bbf\u4e3b\u7684 React \u5728\u6211\u4eec\u4e4b\u540e\u4f1a\u518d\u8bbe\u4e00\u6b21 dark\uff0c",
    "\t\t\t   \u6240\u4ee5\u8fc7\u4e00\u4f1a\u513f\u518d\u63a8\u51e0\u6b21\u3002\u4e0d\u7528 MutationObserver\uff08\u4f1a\u6b7b\u5faa\u73af\uff09\u3002 */",
    "\t\t\tapplyTheme(\"light\");",
    "\t\t\t[600, 1500, 3000, 6000].forEach(function (d) {",
    "\t\t\t\tsetTimeout(function () { applyTheme(\"light\"); }, d);",
    "\t\t\t});",
    "\t\t}",
]
lines[i:j+1] = NEW
io.open(TMP, "w", encoding="utf-8", newline="").write(chr(10).join(lines))
os.replace(TMP, P)
print("initTheme: retry pushes added")