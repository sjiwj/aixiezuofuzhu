
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('renameBranch')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) 三个动作函数：插在 total 行之前
const i = find('const total = groups.reduce(function (n, g) { return n + (g.items ? g.items.length : 0); }, 0);')
if (i < 0) throw new Error('total anchor')
const fns = [
  T(3) + '/* 分支：改名 / 删除（进回收站） */',
  T(3) + 'const renameBranch = useCallback(async function (branch) {',
  T(4) + 'if (!book || !branch) return;',
  T(4) + 'const to = await nvlPrompt("重命名分支", "新名字，例如 角色卡 / 功法库", branch);',
  T(4) + 'if (!to || to === branch) return;',
  T(4) + 'const r = await api("/novelapp/setting-branch-rename", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ book: book, from: branch, to: to }) });',
  T(4) + 'if (!r.ok || (r.data && r.data.ok === false)) { setError((r.data && r.data.error) === "exists" ? ("已有同名分支：" + to) : ((r.data && r.data.error) || "改名失败")); return; }',
  T(4) + 'setError("");',
  T(4) + 'await load();',
  T(3) + '}, [book, load]);',
  '',
  T(3) + 'const deleteBranch = useCallback(async function (branch) {',
  T(4) + 'if (!book || !branch) return;',
  T(4) + 'const yes = await nvlPrompt("删除分支", "确认删除分支「" + branch + "」？里面的设定文件会进回收站。输入 删除 确认");',
  T(4) + 'if (!yes) return;',
  T(4) + 'if (String(yes).trim() !== "删除") { setError("没有删除：需要输入「删除」两个字确认"); return; }',
  T(4) + 'const r = await api("/novelapp/setting-branch-delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ book: book, name: branch }) });',
  T(4) + 'if (!r.ok || (r.data && r.data.ok === false)) { setError((r.data && r.data.error) || "删除分支失败"); return; }',
  T(4) + 'setError("");',
  T(4) + 'setSel(null);',
  T(4) + 'await load();',
  T(3) + '}, [book, load]);',
  '',
  T(3) + '/* 文件：移到别的分支（留空 = 未分组） */',
  T(3) + 'const moveDoc = useCallback(async function (it) {',
  T(4) + 'if (!book || !it) return;',
  T(4) + 'const to = await nvlPrompt("移动到分支", "目标分支名；留空 = 未分组", "");',
  T(4) + 'if (to === null) return;',
  T(4) + 'const r = await api("/novelapp/setting-move", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ book: book, path: it.path, branch: String(to || "").trim() }) });',
  T(4) + 'if (!r.ok || (r.data && r.data.ok === false)) { setError((r.data && r.data.error) === "exists" ? "目标分支里已有同名文件" : ((r.data && r.data.error) || "移动失败")); return; }',
  T(4) + 'setError("");',
  T(4) + 'await load();',
  T(3) + '}, [book, load]);',
  '',
]
L.splice(i, 0, ...fns)
console.log('fns ok before', i + 1)

// 2) 分支行按钮：+ ✎ ✕
const b0 = find('(isBreakdown || g.kind !== "docs") ? null : h("button", {')
if (b0 < 0) throw new Error('branch buttons')
let b1 = -1
for (let k = b0; k < b0 + 12; k++) { if ((L[k] || '').includes('}, "+")));')) { b1 = k; break } }
if (b1 < 0) throw new Error('branch buttons end')
const mini = 'style: { height: "20px", padding: "0 6px", fontSize: "11px" }'
const newBtns = [
  T(5) + '/* 分支操作：+ 新建文件 / ✎ 改名 / ✕ 删除（「未分组」没有后两个） */',
  T(5) + '(isBreakdown || g.kind !== "docs")',
  T(6) + '? null',
  T(6) + ': h("span", { style: { display: "inline-flex", gap: "2px" } },',
  T(7) + 'h("button", { className: "nvl-btn", ' + mini + ', title: "在这个分支里新建设定文件", onClick: function (e) { e.stopPropagation(); newDoc(g.branch || ""); } }, "+"),',
  T(7) + 'g.branch ? h("button", { className: "nvl-btn", ' + mini + ', title: "重命名分支", onClick: function (e) { e.stopPropagation(); renameBranch(g.branch); } }, "\u270E") : null,',
  T(7) + 'g.branch ? h("button", { className: "nvl-btn", ' + mini + ', title: "删除分支（进回收站）", onClick: function (e) { e.stopPropagation(); deleteBranch(g.branch); } }, "\u2715") : null)));',
]
L.splice(b0, b1 - b0 + 1, ...newBtns)
console.log('branch buttons ok', b0 + 1, b1 + 1)

// 3) 文件行：加「移到」
const f0 = find('h("span", { className: "nvl-tree__name" }, label),', find('function LibraryPane'))
if (f0 < 0) throw new Error('doc row name')
L.splice(f0 + 1, 0,
  T(6) + 'h("span", { style: { flex: "1" } }),',
  T(6) + '(isBreakdown || g.kind !== "docs") ? null : h("button", { className: "nvl-btn", ' + mini + ', title: "移到别的分支", onClick: function (e) { e.stopPropagation(); moveDoc(it); } }, "\u2192"),'
)
console.log('doc move button at', f0 + 2)

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE library branch ops')
