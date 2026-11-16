# -*- coding: utf-8 -*-
"""挂件的完结可行性一行：加「复制」按钮，产出一行可转发文本"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "nvl-dock__copy" in s:
    print("ALREADY"); sys.exit(0)

OLD = chr(9)*4 + '''if (feas.cuts && feas.cuts.length) {
					fl.textContent += "  必须砍" + feas.cuts.length + "条";
				}
				root.appendChild(fl);'''

if OLD not in s:
    print("anchor missing"); sys.exit(1)

NEW = chr(9)*4 + '''if (feas.cuts && feas.cuts.length) {
					fl.textContent += "  必须砍" + feas.cuts.length + "条";
				}
				// 一行可转发文本：商业调研里唯一能被贴进作者群的资产
				var copyBtn = el("button", "nvl-dock__copy", "复制一行");
				copyBtn.title = "复制成一行，能直接贴进作者群";
				copyBtn.onclick = function () {
					var v = VB[feas.verdict] || feas.verdict;
					var one = "《" + (data.book || "") + "》完结可行性  " + v;
					if (feas.need != null && feas.remaining != null) {
						one += " · 需" + Math.round(feas.need) + "章 / 剩" + feas.remaining + "章";
					}
					if (feas.cuts && feas.cuts.length) one += " · 必须砍" + feas.cuts.length + "条";
					try {
						if (navigator.clipboard && navigator.clipboard.writeText) {
							navigator.clipboard.writeText(one);
						}
					} catch (e) { /* 复制失败不影响显示 */ }
					copyBtn.textContent = "已复制";
					setTimeout(function () { copyBtn.textContent = "复制一行"; }, 1500);
				};
				fl.appendChild(copyBtn);
				root.appendChild(fl);'''

s = s.replace(OLD, NEW, 1)
io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("copy button added")