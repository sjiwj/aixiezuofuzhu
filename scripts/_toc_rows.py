# -*- coding: utf-8 -*-
"""章节列表改书的目录：章号 | 标题 | 引导点线 | 字数；操作按钮 hover 才出"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "nvl-toc__dots" in s:
    print("ALREADY"); sys.exit(0)

OLD = '''							h("span", { className: "nvl-tree__name" }, ch.name),
						h("span", { style: { flex: "1" } }),'''

NEW = '''							// 书的目录：章号 | 标题 | 引导点线 | 字数（操作按钮 hover 才出）
							(function () {
								var mm = String(ch.name || "").match(/^(\u7b2c[^-\u2014]+\u7ae0|\u7b2c\d+\u7ae0)[-\u2014\s]*(.*)$/);
								var no = mm ? mm[1] : "";
								var ti = mm ? (mm[2] || "") : String(ch.name || "");
								return [
									h("span", { className: "nvl-toc__no", key: "n" }, no),
									h("span", { className: "nvl-toc__title", key: "t" }, ti || "（无标题）"),
									h("span", { className: "nvl-toc__dots", key: "d" }),
									h("span", { className: "nvl-toc__chars", key: "c" }, ch.chars ? String(ch.chars) : ""),
									h("span", { className: "nvl-toc__acts", key: "a" })
								];
							})(),'''

if OLD not in s:
    print("anchor missing"); sys.exit(1)
s = s.replace(OLD, NEW, 1)

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("toc rows added")