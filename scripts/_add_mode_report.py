# -*- coding: utf-8 -*-
"""前端：面板切换时上报 auto 模式"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "reportModeByPanel" in s:
    print("ALREADY"); sys.exit(0)

OLD = '''		function markActivePanel(slug) {
			try {
				if (slug) document.body.dataset.activePanel = slug;
			} catch (e) { /* ignore */ }
		}'''
if OLD not in s:
    print("markActivePanel anchor missing"); sys.exit(1)

NEW = '''		/* 模式自动判定：写作相关面板 -> writing，其余 -> general
		   上报给插件后端，后端据此决定 system prompt 与工具是否注入 */
		const WRITING_PANELS = ["writing", "library", "breakdown", "review"];
		let lastPanelMode = "";
		function reportModeByPanel(slug) {
			const want = WRITING_PANELS.indexOf(slug) >= 0 ? "writing" : "general";
			if (want === lastPanelMode) return;
			lastPanelMode = want;
			try {
				nvlToken().then(function (tk) {
					return fetch(apiBase().replace(/\\/+$/, "") + "/novelapp/mode", {
						method: "POST",
						headers: Object.assign({ "Content-Type": "application/json" },
							tk ? { "X-Novelapp-Token": tk } : {}),
						body: JSON.stringify({ auto: want })
					});
				}).catch(function () { /* 模式上报失败不影响界面 */ });
			} catch (e) { /* ignore */ }
		}

		function markActivePanel(slug) {
			try {
				if (slug) document.body.dataset.activePanel = slug;
			} catch (e) { /* ignore */ }
			try { reportModeByPanel(slug); } catch (e2) { /* ignore */ }
		}'''
s = s.replace(OLD, NEW, 1)

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("reportModeByPanel added, chars =", len(s))
