# -*- coding: utf-8 -*-
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if s.count("feas === null && data.book") != 1:
    print("unexpected count"); sys.exit(1)

BLOCK = """				// 完结可行性数据：折叠态也要拉（底部状态条要显示）
				if (feas === null && data.book) {
					feas = "loading";
					fetch(apiBase().replace(/\\/+$/, "") + "/api/completion?book=" + encodeURIComponent(data.book))
						.then(function (r) { return r.ok ? r.json() : null; })
						.then(function (j2) { feas = (j2 && j2.ok) ? j2.report : false; render(); })
						.catch(function () { feas = false; });
				}
"""
# 删掉原位置的块
OLD = """				// 完结可行性：一眼看到这本书还能不能写完
				if (feas === null && data.book) {
					feas = "loading";
					fetch(apiBase().replace(/\\/+$/, "") + "/api/completion?book=" + encodeURIComponent(data.book))
						.then(function (r) { return r.ok ? r.json() : null; })
						.then(function (j2) { feas = (j2 && j2.ok) ? j2.report : false; render(); })
						.catch(function () { feas = false; });
				}
"""
if OLD in s:
    s = s.replace(OLD, "", 1)
    print("removed old block")
else:
    print("OLD block not matched, fallback to regex")
    import re
    s = re.sub(r"\n\t\t\t\t// 完结可行性：一\u773c[\s\S]{0,500}?\n\t\t\t\t\}\n", "\n", s, count=1)

# 插到 head 渲染之前（找 root.textContent = ""; 那一行）
ANCHOR = '\t\t\t\troot.textContent = "";'
i = s.find(ANCHOR)
if i < 0:
    print("anchor missing"); sys.exit(1)
s = s[:i + len(ANCHOR)] + chr(10) + BLOCK + s[i + len(ANCHOR):]

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("moved: count now", s.count("feas === null && data.book"))