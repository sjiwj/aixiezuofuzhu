
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('nvl-rev__pick')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) 卡片勾选框：插在 verdict span 之后
const vd = find('r.verdictLabel || VERDICT_TEXT[v] || String(r.verdict || "")')
if (vd < 0) throw new Error('verdict span')
// 该行是 h("span", ... , ...) 的一行，插入到它之后
L.splice(vd + 1, 0,
  T(6) + 'h("label", { className: "nvl-rev__pick", title: "改稿时是否采用这条意见", onClick: function (e3) { e3.stopPropagation(); } },',
  T(7) + 'h("input", {',
  T(8) + 'type: "checkbox",',
  T(8) + 'checked: useNotes[r.id || r.name] !== false,',
  T(8) + 'onChange: function (e4) {',
  T(9) + 'const rid = r.id || r.name || "";',
  T(9) + 'setUseNotes(function (prev) { const n = Object.assign({}, prev); n[rid] = !!e4.target.checked; return n; });',
  T(8) + '}',
  T(7) + '}),',
  T(7) + 'h("span", null, "用")),'
)
console.log('1) checkbox ok')

// 2) 撤销按钮：recheck 行里加（在「没有新问题」的提示之后）
const rk = find('recheck.issues.length ? h("span", { className: "nvl-review__hint" }, recheck.issues.slice(0, 3)')
if (rk < 0) throw new Error('recheck row')
L.splice(rk + 1, 0,
  T(6) + 'lastBackup ? h("button", { className: "nvl-btn", style: { marginLeft: "8px" }, onClick: undoRevise, title: "从改稿前的备份恢复，然后复检" }, "撤销这次改稿") : null'
)
console.log('2) undo button ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE ui')
