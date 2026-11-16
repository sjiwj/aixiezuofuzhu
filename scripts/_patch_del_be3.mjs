
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/index.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('setting-branch-rename')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const start = L.findIndex((x) => x.includes("'/novelapp/setting-new'"))
if (start < 0) throw new Error('setting-new not found')
let close = -1
for (let k = start + 1; k < start + 40; k++) { if ((L[k] || '').trim() === '}') { close = k; break } }
if (close < 0) throw new Error('close not found')
console.log('setting-new at', start + 1, 'close at', close + 1)

const BAD = "const okName = (v) => !!v && !v.includes('..') && !v.startsWith('.') && path.basename(v) === v && !/[<>:\"|?*]/.test(v)"
const block = [
  "",
  "    if (req.method === 'POST' && u.pathname === '/novelapp/setting-branch-rename') {",
  "      const body = await readBody(req)",
  "      const book = String(body.book || '').trim()",
  "      const from = String(body.from || '').trim()",
  "      const to = String(body.to || '').trim()",
  "      " + BAD,
  "      if (!okName(book) || !okName(from) || !okName(to)) return sendJson(res, 400, { ok: false, error: '名字不合法（不能含 / \\ : * ? \" < > |）' })",
  "      const root = path.join(projectsRoot(), book, '设定库')",
  "      const src = path.join(root, from)",
  "      const dst = path.join(root, to)",
  "      if (!fs.existsSync(src)) return sendJson(res, 404, { ok: false, error: '分支不存在' })",
  "      if (fs.existsSync(dst)) return sendJson(res, 200, { ok: false, error: 'exists' })",
  "      try { fs.renameSync(src, dst) } catch (e) { return sendJson(res, 500, { ok: false, error: String((e && e.message) || e) }) }",
  "      return sendJson(res, 200, { ok: true, from: from, to: to })",
  "    }",
  "",
  "    if (req.method === 'POST' && u.pathname === '/novelapp/setting-branch-delete') {",
  "      const body = await readBody(req)",
  "      const book = String(body.book || '').trim()",
  "      const name = String(body.name || '').trim()",
  "      " + BAD,
  "      if (!okName(book) || !okName(name)) return sendJson(res, 400, { ok: false, error: '名字不合法' })",
  "      const root = path.join(projectsRoot(), book, '设定库')",
  "      const dir = path.join(root, name)",
  "      if (!fs.existsSync(dir)) return sendJson(res, 404, { ok: false, error: '分支不存在' })",
  "      const stamp = new Date().toISOString().replace(/[:.]/g, '-')",
  "      const trash = path.join(path.dirname(projectsRoot()), '.trash', stamp)",
  "      try {",
  "        fs.mkdirSync(trash, { recursive: true })",
  "        fs.renameSync(dir, path.join(trash, name))",
  "      } catch (e) { return sendJson(res, 500, { ok: false, error: String((e && e.message) || e) }) }",
  "      return sendJson(res, 200, { ok: true, name: name, trash: '.trash/' + stamp })",
  "    }",
  "",
  "    if (req.method === 'POST' && u.pathname === '/novelapp/setting-move') {",
  "      const body = await readBody(req)",
  "      const book = String(body.book || '').trim()",
  "      const rel = String(body.path || '').trim().replace(new RegExp(String.fromCharCode(92) + String.fromCharCode(92), 'g'), '/')",
  "      const toDir = String(body.branch || '').trim()",
  "      " + BAD,
  "      if (!okName(book) || !rel || rel.includes('..') || rel.indexOf('设定库/') !== 0) return sendJson(res, 400, { ok: false, error: '路径不合法' })",
  "      if (toDir && !okName(toDir)) return sendJson(res, 400, { ok: false, error: '分支名不合法' })",
  "      const root = path.join(projectsRoot(), book, '设定库')",
  "      const from = path.join(root, rel.slice('设定库/'.length))",
  "      if (!fs.existsSync(from)) return sendJson(res, 404, { ok: false, error: '文件不存在' })",
  "      const fileName = rel.split('/').pop()",
  "      const targetDir = toDir ? path.join(root, toDir) : root",
  "      const target = path.join(targetDir, fileName)",
  "      if (!path.resolve(target).startsWith(path.resolve(root))) return sendJson(res, 400, { ok: false, error: '路径越界' })",
  "      if (fs.existsSync(target)) return sendJson(res, 200, { ok: false, error: 'exists', rel: '设定库/' + (toDir ? toDir + '/' : '') + fileName })",
  "      try {",
  "        fs.mkdirSync(targetDir, { recursive: true })",
  "        fs.renameSync(from, target)",
  "      } catch (e) { return sendJson(res, 500, { ok: false, error: String((e && e.message) || e) }) }",
  "      return sendJson(res, 200, { ok: true, rel: '设定库/' + (toDir ? toDir + '/' : '') + fileName })",
  "    }",
]
L.splice(close + 1, 0, ...block)
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('inserted 3 routes after line', close + 1)
