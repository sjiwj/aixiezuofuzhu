
import fs from 'node:fs'
const fp = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
const ref = 'D:/NovelApp/_archive/restore/client-079.js'
const parts = fs.readFileSync(fp, 'utf8')
const refTxt = fs.readFileSync(ref, 'utf8')
const eol = parts.includes('\r\n') ? '\r\n' : '\n'

function blocks(lines) {
  const out = []
  for (let i = 0; i < lines.length; i++) {
    if (lines[i] === '\t\t\tconst rows = [];') {
      let j = -1
      for (let k = i + 1; k < lines.length; k++) { if (lines[k] === '\t\t\t});') { j = k; break } }
      if (j > 0) out.push({ start: i, end: j, text: lines.slice(i, j + 1).join(eol), body: lines.slice(i, j + 1).join('\n') })
    }
  }
  return out
}

const refLines = refTxt.split(/\r?\n/)
const refBlocks = blocks(refLines)
console.log('ref blocks:', refBlocks.length, refBlocks.map(b => b.body.includes('books.length') ? 'tree' : 'other').join(','))
const treeBlock = refBlocks.find((b) => b.body.includes('books.length'))
if (!treeBlock) throw new Error('tree block not found in ref')
console.log('tree block lines:', treeBlock.end - treeBlock.start + 1)

let L = parts.split(eol)
let bs = blocks(L)
console.log('parts blocks:', bs.length, bs.map((b, i) => i + ':' + (b.body.includes('toggleGroup') ? 'BROKEN(lib-style)' : b.body.includes('books.length') ? 'tree' : 'lib-orig')).join(' | '))

const broken = bs.find((b) => b.body.includes('toggleGroup'))
const libOrig = bs.find((b) => !b.body.includes('toggleGroup') && !b.body.includes('books.length'))
if (!broken) throw new Error('broken block not found')
if (!libOrig) throw new Error('lib orig block not found')

const T = (n) => '\t'.repeat(n)
const newLib = [
T(3)+'const rows = [];',
T(3)+'const toggleGroup = function (label) {',
T(4)+'setCollapsed(function (p) { const n = Object.assign({}, p); n[label] = !n[label]; return n; });',
T(3)+'};',
T(3)+'groups.forEach(function (g) {',
T(4)+'const list = g.items || [];',
T(4)+'const closed = !!collapsed[g.label];',
T(4)+'rows.push(h("div", {',
T(5)+'key: "h-" + g.label,',
T(5)+'className: "nvl-tree__bookname",',
T(5)+'style: { cursor: "pointer" },',
T(5)+'title: closed ? "点开" : "收起",',
T(5)+'onClick: function () { toggleGroup(g.label); }',
T(4)+'},',
T(5)+'h("span", null, (closed ? "> " : "v ") + g.label),',
T(5)+'h("span", { style: { flex: "1" } }),',
T(5)+'h("span", { className: "nvl-tree__count nvl-mono" }, String(list.length)),',
T(5)+'(isBreakdown || g.kind !== "docs") ? null : h("button", {',
T(6)+'className: "nvl-btn",',
T(6)+'style: { height: "20px", padding: "0 6px", fontSize: "11px" },',
T(6)+'title: "在这个分支里新建设定文件",',
T(6)+'onClick: function (e) { e.stopPropagation(); newDoc(g.branch || ""); }',
T(5)+'}, "+")));',
T(4)+'if (closed) return;',
T(4)+'if (!list.length) {',
T(5)+'rows.push(h("div", { key: "e-" + g.label, className: "nvl-empty", style: { paddingTop: "0" } },',
T(6)+'isBreakdown ? "还没拆过书，点 README 看怎么拆" : "（空）"));',
T(5)+'return;',
T(4)+'}',
T(4)+'list.forEach(function (it, idx) {',
T(5)+'const label = String(it.title || it.name || it.id || it.path || "");',
T(5)+'rows.push(h("div", {',
T(6)+'key: g.label + "-" + idx,',
T(6)+'className: "nvl-tree__chapter",',
T(6)+'role: "button",',
T(6)+'tabIndex: 0,',
T(6)+'title: it.path || it.file || label,',
T(6)+'onClick: function () { openItem(it, g.kind === "docs" ? "设定文件" : g.label); }',
T(5)+'},',
T(6)+'h("span", { className: "nvl-tree__name" }, label),',
T(6)+'h("span", { className: "nvl-dim nvl-mono", style: { fontSize: "11px" } }, itemChars(it) + " 字")));',
T(4)+'});',
T(3)+'});',
]

// 从大到小改，避免位移
const edits = [
  { at: libOrig, lines: newLib },
  { at: broken, lines: treeBlock.body.split('\n') },
].sort((a, b) => b.at.start - a.at.start)

for (const ed of edits) {
  L.splice(ed.at.start, ed.at.end - ed.at.start + 1, ...ed.lines)
}
fs.writeFileSync(fp, L.join(eol), 'utf8')
console.log('RESTORED + INSERTED, lines:', L.length)
