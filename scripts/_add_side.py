# -*- coding: utf-8 -*-
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\070-body.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "nvl-side__card" in s:
    print("ALREADY"); sys.exit(0)

ANCHOR = '''				note ? h("div", { className: "nvl-note", role: "status" }, note) : null
			); };'''

SIDE = '''				note ? h("div", { className: "nvl-note", role: "status" }, note) : null,
				/* 右栏 320px（照 blog-sidebar 的 grid 1fr 320px）：账目 / 承诺 / 快捷 */
				h("aside", { className: "nvl-side" },
					h("div", { className: "nvl-side__card" },
						h("div", { className: "nvl-side__h" }, "账目"),
						h("div", { className: "nvl-side__m" },
							h("span", { className: "nvl-side__k" }, "必须兑现"),
							h("span", { className: "nvl-side__v nvl-side__v--warn" }, String((debt && debt.must_touch && debt.must_touch.length) || 0))),
						h("div", { className: "nvl-side__m" },
							h("span", { className: "nvl-side__k" }, "未兑付承诺"),
							h("span", { className: "nvl-side__v" }, String((debt && debt.promises_open) || "—"))),
						h("div", { className: "nvl-side__m" },
							h("span", { className: "nvl-side__k" }, "本章字数"),
							h("span", { className: "nvl-side__v" }, String(stats.cjk)))),

					(debt && debt.must_touch && debt.must_touch.length)
						? h("div", { className: "nvl-side__card" },
							h("div", { className: "nvl-side__h" }, "这一章必须动"),
							debt.must_touch.map(function (it, i3) {
								return h("div", { key: i3, className: "nvl-side__item" },
									h("div", { className: "nvl-side__t" }, it.title),
									h("div", { className: "nvl-side__meta" }, (it.why || "") + (it.kind ? " · " + it.kind : "")),
									h("div", { className: "nvl-side__bar" }, h("i", { className: "warn", style: { width: "80%" } })));
							}))
						)
						: null,

					h("div", { className: "nvl-side__card" },
						h("div", { className: "nvl-side__h" }, "快捷"),
						h("div", { className: "nvl-side__chips" },
							h("button", { className: "nvl-side__chip", onClick: function () { try { selectPanel("novel-projects"); } catch (e) { /* ignore */ } } }, "看账本"),
							h("button", { className: "nvl-side__chip", onClick: exportMenu }, "导出"),
							h("button", { className: "nvl-side__chip", onClick: function () { load(path); } }, "重新加载"),
							h("button", { className: "nvl-side__chip", onClick: function () { persist(text, true); } }, "保存"))))
			); };'''

if ANCHOR not in s:
    print("anchor missing"); sys.exit(1)
s = s.replace(ANCHOR, SIDE, 1)
io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("side panel inserted")