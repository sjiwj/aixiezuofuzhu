
import fs from 'node:fs'
const fp = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(fp, 'utf8')
if (s.includes('toggleGroup')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const L = s.split(eol)
const i0 = L.findIndex((x) => x === '\t\t\tconst rows = [];')
if (i0 < 0) throw new Error('rows anchor missing')
let i1 = -1
for (let i = i0 + 1; i < L.length; i++) { if (L[i] === '\t\t\t});') { i1 = i; break } }
if (i1 < 0) throw new Error('rows end anchor missing')
const T = (n) => '\t'.repeat(n)
const nu = [
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
L.splice(i0, i1 - i0 + 1, ...nu)
fs.writeFileSync(fp, L.join(eol), 'utf8')
console.log('rows block replaced', i0, i1)
