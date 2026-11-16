
import fs from 'node:fs'
const fp = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(fp, 'utf8')
if (s.includes('newBranchName') || s.includes('const [collapsed')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const J = (arr) => arr.join(eol)
function rep(oldStr, newStr, tag) {
  if (!s.includes(oldStr)) throw new Error('anchor fail: ' + tag)
  s = s.split(oldStr).join(newStr)
  console.log('ok', tag)
}

// 1) state
rep(
  '\t\t\tconst [sel, setSel] = useState(null);',
  J([
    '\t\t\tconst [sel, setSel] = useState(null);',
    '\t\t\tconst [collapsed, setCollapsed] = useState({ "承诺": true, "信息差": true });',
    '\t\t\tconst [busyNew, setBusyNew] = useState(false);',
  ]),
  'state'
)

// 2) setGroups
rep(
  J([
    '\t\t\t\tsetGroups([',
    '\t\t\t\t\t{ label: "承诺", items: (pm.ok && pm.data && pm.data.items) || [] },',
    '\t\t\t\t\t{ label: "信息差", items: (ig.ok && ig.data && ig.data.items) || [] },',
    '\t\t\t\t\t{ label: "设定文件", items: (docs.ok && docs.data && docs.data.items) || [] }',
    '\t\t\t\t]);',
  ]),
  J([
    '\t\t\t\tconst docItems = (docs.ok && docs.data && docs.data.items) || [];',
    '\t\t\t\tsetGroups([',
    '\t\t\t\t\t{ label: "承诺", kind: "promises", items: (pm.ok && pm.data && pm.data.items) || [] },',
    '\t\t\t\t\t{ label: "信息差", kind: "infogaps", items: (ig.ok && ig.data && ig.data.items) || [] }',
    '\t\t\t\t].concat(splitSettingBranches(docItems)));',
  ]),
  'setGroups'
)

// 3) head：+ 新建分支
rep(
  '\t\t\t\th("button", { className: "nvl-btn", onClick: load, disabled: busy }, "刷新"));',
  J([
    '\t\t\t\tisBreakdown ? null : h("button", { className: "nvl-btn", onClick: newBranch, disabled: busyNew, title: "在设定库里新建一个分支（例如 角色卡 / 功法库）" }, "+ 分支"),',
    '\t\t\t\th("button", { className: "nvl-btn", onClick: load, disabled: busy }, "刷新"));',
  ]),
  'head-button'
)

// 4) 新建分支 / 新建文件 两个动作（插在 openItem 之后、total 之前）
rep(
  '\t\t\tconst total = groups.reduce(function (n, g) { return n + (g.items ? g.items.length : 0); }, 0);',
  J([
    '\t\t\t/* 新建分支：设定库/ 下开一个目录，分支里的文件就是这个目录里的 .md */',
    '\t\t\tconst newBranch = useCallback(async function () {',
    '\t\t\t\tif (!book) { setError("先选一本书（左栏「项目」里点书名）"); return; }',
    '\t\t\t\tconst name = await nvlPrompt("新建分支", "分支名，例如 角色卡 / 功法库 / 势力", "");',
    '\t\t\t\tif (!name) return;',
    '\t\t\t\tsetBusyNew(true);',
    '\t\t\t\tconst r = await api("/novelapp/setting-branch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ book: book, name: name }) });',
    '\t\t\t\tsetBusyNew(false);',
    '\t\t\t\tif (!r.ok || (r.data && r.data.ok === false)) { setError((r.data && r.data.error) === "exists" ? ("分支「" + name + "」已经存在") : ((r.data && r.data.error) || "新建分支失败")); return; }',
    '\t\t\t\tsetError("");',
    '\t\t\t\tsetCollapsed(function (p) { const n = Object.assign({}, p); n[name] = false; return n; });',
    '\t\t\t\tload();',
    '\t\t\t}, [book, load]);',
    '',
    '\t\t\t/* 在某个分支里新建一个设定文件 */',
    '\t\t\tconst newDoc = useCallback(async function (branch) {',
    '\t\t\t\tif (!book) { setError("先选一本书"); return; }',
    '\t\t\t\tconst name = await nvlPrompt("新建设定文件", branch ? ("分支：" + branch + "，文件名例如 主角 / 反派") : "文件名例如 主角 / 反派");',
    '\t\t\t\tif (!name) return;',
    '\t\t\t\tsetBusyNew(true);',
    '\t\t\t\tconst r = await api("/novelapp/setting-new", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ book: book, branch: branch || "", name: name }) });',
    '\t\t\t\tsetBusyNew(false);',
    '\t\t\t\tif (!r.ok || (r.data && r.data.ok === false)) { setError((r.data && r.data.error) === "exists" ? ("「" + name + "」已经存在") : ((r.data && r.data.error) || "新建文件失败")); return; }',
    '\t\t\t\tsetError("");',
    '\t\t\t\tawait load();',
    '\t\t\t\tconst rel = (r.data && r.data.rel) || "";',
    '\t\t\t\tif (rel) {',
    '\t\t\t\t\tconst d = await api("/novelapp/setting-doc?book=" + encodeURIComponent(book) + "&path=" + encodeURIComponent(rel));',
    '\t\t\t\t\tif (d.ok) { const dd = d.data || {}; setSel({ title: dd.title || name, path: dd.path || rel, text: String(dd.content || "") }); }',
    '\t\t\t\t}',
    '\t\t\t}, [book, load]);',
    '',
    '\t\t\tconst total = groups.reduce(function (n, g) { return n + (g.items ? g.items.length : 0); }, 0);',
  ]),
  'actions'
)

fs.writeFileSync(fp, s, 'utf8')
console.log('WROTE step A/B/C/D')
