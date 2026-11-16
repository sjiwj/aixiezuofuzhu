# -*- coding: utf-8 -*-
import io, os, sys, re
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "LOCKED_LIGHT" in s:
    print("ALREADY"); sys.exit(0)

# 找 initTheme 到 applyTheme 结束的整块，替换成固定浅色
START = "\t\t/* \u5916\u89c2\uff1a\u8ddf\u968f\u7cfb\u7edf / \u6d45\u8272 / \u6df1\u8272\uff08\u6b63\u6587\u914d\u8272\u5b9a\u4e49\u5728 040-theme.js\uff09*/"
i = s.find(START)
if i < 0:
    print("start anchor missing"); sys.exit(1)
# 从 START 往后找 "initTheme();" 之后到 applyTheme 函数的结尾
j = s.find("initTheme();", i)
if j < 0:
    print("initTheme missing"); sys.exit(1)
# 找 applyTheme 定义的结束（下一个顶层注释或函数）
k = s.find("\t\t/* \u8bbe\u7f6e \u2192 \u901a\u7528 \u2192 \u7528\u91cf\u4e0e\u82b1\u8d39", j)
if k < 0:
    # 退而求其次：往后 60 行内找 "\t\t}" 且下一行是注释
    k = s.find("\t\t\t}\n\t\t}\n", j)
    if k < 0:
        print("end anchor missing"); sys.exit(1)
    k = k + len("\t\t\t}\n\t\t}\n")

NEW = """\t\t/* LOCKED_LIGHT\uff1a\u56fa\u5b9a\u6d45\u8272\u3002\u6df1\u8272\u4e3b\u9898\u6709 bug\uff0c\u4e0d\u518d\u8ddf\u968f\u5bbf\u4e3b/\u7cfb\u7edf\uff0c\u4e5f\u4e0d\u7ed9\u5ba2\u6237\u5207\uff08\u8bbe\u7f6e\u91cc\u7684\u300c\u5916\u89c2\u300d\u5df2\u9690\u85cf\uff09\u3002
\t\t   \u4e0d\u8981\u518d\u52a0 MutationObserver \u76d1\u542c data-ds-theme-source\uff1a\u5bbf\u4e3b\u4f1a\u628a\u5b83\u6539\u56de dark\uff0c\u76d1\u542c\u5c31\u662f\u8ddf\u7740\u9519\u3002 */
\t\ttry {
\t\t\tdocument.documentElement.setAttribute("data-nvl-theme", "light");
\t\t\tdocument.documentElement.setAttribute("data-ds-theme-source", "light");
\t\t} catch (e) { /* ignore */ }
\t\t/* \u5bbf\u4e3b\u542f\u52a8\u540e\u4f1a\u518d\u8bbe\u4e00\u6b21\uff0c\u6240\u4ee5\u8fc7\u4e00\u4f1a\u513f\u518d\u63a8\u4e00\u6b21\uff08\u4e0d\u7528 observer\uff0c\u907f\u514d\u6b7b\u5faa\u73af\uff09 */
\t\tsetTimeout(function () {
\t\t\ttry {
\t\t\t\tdocument.documentElement.setAttribute("data-nvl-theme", "light");
\t\t\t\tdocument.documentElement.setAttribute("data-ds-theme-source", "light");
\t\t\t} catch (e) { /* ignore */ }
\t\t}, 1200);
\t\tsetTimeout(function () {
\t\t\ttry {
\t\t\t\tdocument.documentElement.setAttribute("data-nvl-theme", "light");
\t\t\t\tdocument.documentElement.setAttribute("data-ds-theme-source", "light");
\t\t\t} catch (e) { /* ignore */ }
\t\t}, 3000);
"""
s = s[:i] + NEW + s[k:]

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("locked light")