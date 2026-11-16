# -*- coding: utf-8 -*-
"""状态条去中点串：改成「标签+数字」用间距分隔，不用「 · 」"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "nvl-dock__stat" in s:
    print("ALREADY"); sys.exit(0)

OLD = '''				if (!open) {
					// 底部条只放顶部工具栏没有的信息。章名/字数顶部已有，不再重复；
					// data.chapters 是「这本书一共几章」，不是「当前第几章」，别当章号用。
					const brief = [];
					if (feas && feas !== "loading" && feas.M != null) brief.push("账目 " + feas.M + " 点");
					if (feas && feas !== "loading" && feas.remaining != null) brief.push("计划还剩 " + feas.remaining + " 章");
					if (pm.open != null) brief.push("未兑付承诺 " + pm.open);
					if (data.chapters) brief.push("全书 " + data.chapters + " 章");
					if (brief.length) head.appendChild(el("span", "nvl-dock__brief", brief.join("  ·  ")));
				}'''

NEW = '''				if (!open) {
					// 底部条只放顶部没有的，且不用「 · 」串（那是模板味的元信息写法）。
					// 改成「标签 + 数字」的小组，靠间距分隔。
					const brief = el("span", "nvl-dock__brief");
					function stat(label, value) {
						const w = el("span", "nvl-dock__stat");
						w.appendChild(el("span", "nvl-dock__stat-k", label));
						w.appendChild(el("span", "nvl-dock__stat-v", String(value)));
						brief.appendChild(w);
					}
					if (feas && feas !== "loading" && feas.M != null) stat("账目", feas.M);
					if (feas && feas !== "loading" && feas.remaining != null) stat("剩", feas.remaining + " 章");
					if (pm.open != null) stat("未兑付", pm.open);
					if (data.chapters) stat("全书", data.chapters + " 章");
					if (brief.childNodes.length) head.appendChild(brief);
				}'''

if OLD not in s:
    print("anchor missing"); sys.exit(1)
s = s.replace(OLD, NEW, 1)

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("brief -> stat groups")