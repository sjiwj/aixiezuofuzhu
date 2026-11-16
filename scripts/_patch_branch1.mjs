
import fs from 'node:fs'

// ---------- A. 后端：两个新接口 ----------
const bp = 'D:/NovelApp/plugin/lib/index.js'
let b = fs.readFileSync(bp, 'utf8')
if (b.includes('/novelapp/setting-branch')) { console.log('backend ALREADY') }
else {
  const anchor = "    if (req.method === 'POST' && u.pathname === '/novelapp/save') {"
  if (!b.includes(anchor)) throw new Error('backend anchor missing')
  const routes = [
    "    if (req.method === 'POST' && u.pathname === '/novelapp/setting-branch') {",
    "      const body = await readBody(req)",
    "      const book = String(body.book || '').trim()",
    "      const name = String(body.name || '').trim()",
    "      const bad = (v) => !v || v.includes('..') || /[\\\\/:*?\"<>|]/.test(v) || v.startsWith('.')",
    "      if (bad(book) || bad(name)) return sendJson(res, 400, { ok: false, error: '书名或分支名不合法（不能含 / \\ : * ? \" < > |）' })",
    "      const root = path.join(projectsRoot(), book, '设定库')",
    "      const dir = path.join(root, name)",
    "      if (!path.resolve(dir).startsWith(path.resolve(root) + path.sep)) return sendJson(res, 400, { ok: false, error: '路径越界' })",
    "      if (fs.existsSync(dir)) return sendJson(res, 200, { ok: false, error: 'exists', branch: name })",
    "      try { fs.mkdirSync(dir, { recursive: true }) } catch (e) { return sendJson(res, 500, { ok: false, error: String((e && e.message) || e) }) }",
    "      return sendJson(res, 200, { ok: true, branch: name, path: '设定库/' + name })",
    "    }",
    "",
    "    if (req.method === 'POST' && u.pathname === '/novelapp/setting-new') {",
    "      const body = await readBody(req)",
    "      const book = String(body.book || '').trim()",
    "      const branch = String(body.branch || '').trim()",
    "      const name = String(body.name || '').trim().replace(/\\.md$/i, '')",
    "      const bad = (v) => v.includes('..') || /[\\\\/:*?\"<>|]/.test(v) || v.startsWith('.')",
    "      if (!book || bad(book) || !name || bad(name) || (branch && bad(branch))) return sendJson(res, 400, { ok: false, error: '书名 / 分支名 / 文件名不合法' })",
    "      const root = path.join(projectsRoot(), book, '设定库')",
    "      const dir = branch ? path.join(root, branch) : root",
    "      const file = path.join(dir, name + '.md')",
    "      if (!path.resolve(file).startsWith(path.resolve(root) + path.sep)) return sendJson(res, 400, { ok: false, error: '路径越界' })",
    "      if (fs.existsSync(file)) return sendJson(res, 200, { ok: false, error: 'exists', rel: '设定库/' + (branch ? branch + '/' : '') + name + '.md' })",
    "      try {",
    "        fs.mkdirSync(dir, { recursive: true })",
    "        fs.writeFileSync(file, '# ' + name + '\\n\\n', 'utf8')",
    "      } catch (e) { return sendJson(res, 500, { ok: false, error: String((e && e.message) || e) }) }",
    "      return sendJson(res, 200, { ok: true, rel: '设定库/' + (branch ? branch + '/' : '') + name + '.md' })",
    "    }",
    "",
  ].join('\n')
  b = b.replace(anchor, routes + anchor)
  fs.writeFileSync(bp, b, 'utf8')
  console.log('backend: +setting-branch +setting-new')
}

// ---------- B. 前端：设定库分支 ----------
const fp = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(fp, 'utf8')
if (s.includes('splitSettingBranches')) { console.log('frontend ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

// B1. 文件级 helper：插在 LibraryPane 之前
const libAnchor = '\t\t/* 设定库 / 拆书库：左栏面板（左列表 + 右预览，用语句拼装避免深层嵌套） */'
if (!s.includes(libAnchor)) throw new Error('lib anchor missing')
const helper = [
  '\t\t/* 设定库分支：把 listDocs 的扁平结果按「设定库/<分支>/」切成组；根目录散文件归「未分组」 */',
  '\t\tfunction splitSettingBranches(items) {',
  '\t\t\tconst order = [];',
  '\t\t\tconst map = {};',
  '\t\t\t(items || []).forEach(function (it) {',
  '\t\t\t\tconst rel = String(it.path || "").replace(/^设定库\\//, "");',
  '\t\t\t\tconst segs = rel.split("/");',
  '\t\t\t\tconst dir = segs.length > 1 ? segs.slice(0, -1).join("/") : "";',
  '\t\t\t\tconst key = dir || "未分组";',
  '\t\t\t\tif (!map[key]) { map[key] = { label: key, kind: "docs", branch: dir, items: [] }; order.push(key); }',
  '\t\t\t\tmap[key].items.push(it);',
  '\t\t\t});',
  '\t\t\torder.sort(function (a, b) {',
  '\t\t\t\tif (a === "未分组") return 1;',
  '\t\t\t\tif (b === "未分组") return -1;',
  '\t\t\t\treturn String(a).localeCompare(String(b), "zh");',
  '\t\t\t});',
  '\t\t\treturn order.map(function (k) { return map[k]; });',
  '\t\t}',
  '',
].join(eol)
s = s.replace(libAnchor, helper + libAnchor)
fs.writeFileSync(fp, s, 'utf8')
console.log('frontend: +splitSettingBranches')
