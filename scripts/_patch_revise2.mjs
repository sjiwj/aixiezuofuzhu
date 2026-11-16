
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('revisePanel')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) 按钮：插在「停止」按钮之后（head 内）
const stopBtn = find('status === "running" ? h("button", { className: "nvl-btn", onClick: stopReview')
if (stopBtn < 0) throw new Error('stop button')
L.splice(stopBtn + 1, 0,
  T(5) + 'reviewers.some(function (r) { return r.status === "done" && r.text; })',
  T(6) + '? h("button", { className: "nvl-btn", onClick: reviseWithNotes, disabled: revising, title: "把审稿意见交给写手重写，先预览，采用后自动复检" }, revising ? "改稿中…" : "按意见改")',
  T(6) + ': null,'
)
console.log('1) 按钮 ok')

// 2) revisePanel 定义 + 渲染：插在 sum 之前定义，sum 之后渲染
const sumLine = find('\t\t\t\t\t\tsum', find('const cards = reviewers.map'))
if (sumLine < 0) throw new Error('sum render line')
const panelDef = [
  T(3) + '/* 改稿预览 + 复检结果 */',
  T(3) + 'const revisePanel = (revising || revised || recheck)',
  T(4) + '? h("div", { className: "nvl-sum", style: { marginTop: "10px" } },',
  T(5) + 'revising ? h("div", { className: "nvl-sum__row" }, h("span", { className: "nvl-sum__k" }, "改稿"), h("span", { className: "nvl-sum__v" }, "按审稿意见重写中（约 30-60 秒，不落盘）…")) : null,',
  T(5) + 'revised ? h("div", null,',
  T(6) + 'h("div", { className: "nvl-sum__row" },',
  T(7) + 'h("span", { className: "nvl-sum__k" }, "改后正文"),',
  T(7) + 'h("span", { className: "nvl-sum__v" }, String(revised.text || "").length + " 字符 · 尚未落盘")),',
  T(6) + 'h("pre", { className: "nvl-ai-reason", style: { maxHeight: "240px", overflow: "auto", borderBottom: "0", whiteSpace: "pre-wrap" } }, String(revised.text || "").slice(0, 6000)),',
  T(6) + 'h("div", { style: { display: "flex", gap: "8px", margin: "8px 0" } },',
  T(7) + 'h("button", { className: "nvl-btn nvl-btn--primary", onClick: adoptRevised }, "采用并复检"),',
  T(7) + 'h("button", { className: "nvl-btn", onClick: function () { setRevised(null); } }, "放弃"))) : null,',
  T(5) + 'recheck ? h("div", { className: "nvl-sum__row" },',
  T(6) + 'h("span", { className: "nvl-sum__k" }, "复检"),',
  T(6) + 'h("span", { className: "nvl-sum__v" }, "判定 " + String(recheck.verdict || "-") + " · " + recheck.issues.length + " 条问题"),',
  T(6) + 'recheck.issues.length ? h("span", { className: "nvl-review__hint" }, recheck.issues.slice(0, 3).map(function (x) { return (x.rule || "") + "：" + (x.message || ""); }).join("；")) : h("span", { className: "nvl-review__hint" }, "没有新问题")) : null)',
  T(4) + ': null;',
  '',
]
const sumIdx = find('let sum = null;', find('const cards = reviewers.map'))
if (sumIdx < 0) throw new Error('sum def')
L.splice(sumIdx, 0, ...panelDef)
console.log('2) revisePanel 定义 ok')

// 3) 渲染：sum 之后
const sumLine2 = find('\t\t\t\t\t\tsum', sumIdx + panelDef.length)
if (sumLine2 < 0) throw new Error('sum render after def')
L.splice(sumLine2 + 1, 0, T(6) + 'revisePanel')
console.log('3) 渲染 ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE UI')
