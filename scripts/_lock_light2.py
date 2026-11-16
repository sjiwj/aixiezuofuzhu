# -*- coding: utf-8 -*-
"""精确改：initTheme 删 observer，applyTheme 固定 light。用行号，不靠字符串匹配。"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
lines = io.open(P, encoding="utf-8").read().split(chr(10))
print("before lines:", len(lines))

# 找 initTheme 和 applyTheme 的行（0-based）
i_init = None
i_apply = None
for idx, ln in enumerate(lines):
    if ln.strip() == "function initTheme() {":
        i_init = idx
    if ln.strip() == "function applyTheme(mode) {":
        i_apply = idx
print("initTheme at", i_init, "applyTheme at", i_apply)
if i_init is None or i_apply is None:
    print("anchor missing"); sys.exit(1)

# 1) initTheme：从 function 到对应 "}" 整段替换（4 行 body）
#    原：const getMode / applyTheme(getMode()) / try{observer}catch / }
j = i_init
while lines[j].strip() != "}":
    j += 1
init_new = [
    "\t\tfunction initTheme() {",
    "\t\t\t/* LOCKED_LIGHT: \u56fa\u5b9a\u6d45\u8272\u3002\u6df1\u8272\u4e3b\u9898\u6709 bug\uff0c\u4e0d\u8ddf\u968f\u5bbf\u4e3b/\u7cfb\u7edf\u3002",
    "\t\t\t   \u4e0d\u8981\u52a0 MutationObserver \u76d1\u542c data-ds-theme-source\uff1a",
    "\t\t\t   \u5bbf\u4e3b\u4f1a\u628a\u5b83\u6539\u56de dark\uff0capplyTheme \u4f1a\u518d\u6539\u56de\u6765 \u2192 \u6b7b\u5faa\u73af\u3002 */",
    "\t\t\tapplyTheme(\"light\");",
    "\t\t}",
]
lines[i_init:j+1] = init_new
print("initTheme replaced, removed", (j - i_init + 1) - len(init_new), "lines")

# applyTheme 位置会变，重新找
i_apply = None
for idx, ln in enumerate(lines):
    if ln.strip() == "function applyTheme(mode) {":
        i_apply = idx
j2 = i_apply
while lines[j2].strip() != "}":
    j2 += 1
apply_new = [
    "\t\tfunction applyTheme(mode) {",
    "\t\t\t/* LOCKED_LIGHT: \u6c38\u8fdc light\u3002\u8bbe\u7f6e\u91cc\u7684\u300c\u5916\u89c2\u300d\u5df2\u9690\u85cf\uff0c\u5ba2\u6237\u65e0\u6cd5\u5207\u3002 */",
    "\t\t\ttry {",
    "\t\t\t\tconst root = document.documentElement;",
    "\t\t\t\troot.dataset.nvlTheme = \"light\";",
    "\t\t\t\troot.setAttribute(\"data-ds-theme-source\", \"light\");",
    "\t\t\t} catch (e) { /* ignore */ }",
    "\t\t}",
]
lines[i_apply:j2+1] = apply_new
print("applyTheme replaced, removed", (j2 - i_apply + 1) - len(apply_new), "lines")

io.open(TMP, "w", encoding="utf-8", newline="").write(chr(10).join(lines))
os.replace(TMP, P)
print("after lines:", len(lines))