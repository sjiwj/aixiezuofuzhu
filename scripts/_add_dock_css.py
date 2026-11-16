# -*- coding: utf-8 -*-
"""把「对话区移到右侧」做成正式 CSS（可开关）。"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\040-theme.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "nvl-layout-dock" in s:
    print("ALREADY"); sys.exit(0)

CSS = '''
		/* 对话区靠边（照 Laper 的做法：AI 在一边，中间留给写作）
		   用 :has() 找到真正的内容容器——[data-conversation-region] 只是内部锚点，
		   它自己是个空座位，真正的对话内容在父级里。
		   默认关闭，靠 html[data-nvl-layout="dock"] 打开；出问题把属性去掉就还原。 */
		"html[data-nvl-layout=\\"dock\\"] div:has(> [data-conversation-region]) {"
			+ " position: fixed !important; right: 0 !important; top: 0 !important; bottom: 0 !important;"
			+ " left: auto !important; width: 380px !important; height: auto !important; z-index: 30;"
			+ " background: var(--nvl-paper); border-left: 1px solid var(--nvl-rule); overflow: auto; }",
		"html[data-nvl-layout=\\"dock\\"] .nvl-dock, html[data-nvl-layout=\\"dock\\"] .nvl-asst { right: 396px; }",
		"html[data-nvl-layout=\\"dock\\"] .nvl-debt { padding-right: 380px; }",
'''

ANCHOR = "\t\t/* \u5199\u4f5c\u52a9\u624b\u6302\u4ef6\uff08\u7167 Laper \u7684\u6d6e\u52a8\u68c0\u67e5\u9762\u677f\u505a\uff09 */"
i = s.find(ANCHOR)
if i < 0:
    print("anchor missing"); sys.exit(1)
s = s[:i] + CSS + "\n" + s[i:]
io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("dock css added")