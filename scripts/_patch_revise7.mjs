
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)

// A) 撤销按钮：替换 recheck 那一行（先处理大行号）
const rk = L.findIndex((x) => x.includes('recheck.issues.length ? h("span", { className: "nvl-review__hint" }') && x.trim().endsWith(') : null)'))
if (rk < 0) throw new Error('recheck line')
console.log('recheck at', rk + 1)
const newRk = [
  T(6) + 'recheck.issues.length ? h("span", { className: "nvl-review__hint" }, recheck.issues.slice(0, 3).map(function (x) { return (x.rule || "") + "：" + (x.message || ""); }).join("；")) : h("span", { className: "nvl-review__hint" }, "没有新问题"),',
  T(6) + 'lastBackup ? h("button", { className: "nvl-btn", style: { marginLeft: "8px" }, onClick: undoRevise, title: "从改稿前的备份恢复，然后复检" }, "撤销这次改稿") : null) : null)',
]
L.splice(rk, 1, ...newRk)
console.log('A) undo button ok')

// B) 勾选框：在卡片 head 的 meta 之后（那一行以 ].filter(Boolean).join 结尾）
const mt = L.findIndex((x) => x.includes('].filter(Boolean).join(" · "))'))
if (mt < 0) throw new Error('meta line')
console.log('meta at', mt + 1)
L[mt] = T(7) + '].filter(Boolean).join(" · ")),'
const pick = [
  T(6) + 'h("label", { className: "nvl-rev__pick", title: "改稿时是否采用这条意见", style: { marginLeft: "6px", fontSize: "11px", opacity: 0.85 } },',
  T(7) + 'h("input", {',
  T(8) + 'type: "checkbox",',
  T(8) + 'checked: useNotes[r.id || r.name] !== false,',
  T(8) + 'onChange: function (e4) {',
  T(9) + 'const rid = r.id || r.name || "";',
  T(9) + 'setUseNotes(function (prev) { const n = Object.assign({}, prev); n[rid] = !!e4.target.checked; return n; });',
  T(8) + '}',
  T(7) + '}),',
  T(7) + 'h("span", null, "用"))',
]
L.splice(mt + 1, 0, ...pick)
console.log('B) checkbox ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE')
