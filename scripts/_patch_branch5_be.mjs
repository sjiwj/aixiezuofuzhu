
import fs from 'node:fs'
const bp = 'D:/NovelApp/plugin/lib/index.js'
let b = fs.readFileSync(bp, 'utf8')
if (b.includes('branches: branches')) { console.log('backend ALREADY'); process.exit(0) }
const eol = b.includes('\r\n') ? '\r\n' : '\n'
const old = [
  "      const dir = path.join(projectsRoot(), book, '设定库')",
  "      const items = listDocs(dir, '设定库')",
  "      return sendJson(res, 200, { ok: true, items })",
].join(eol)
const neu = [
  "      const dir = path.join(projectsRoot(), book, '设定库')",
  "      const items = listDocs(dir, '设定库')",
  "      // 空分支也要能被看到：把 设定库/ 下的子目录一并返回（承诺 / 信息差 已单独成组）",
  "      let branches = []",
  "      try {",
  "        branches = fs.readdirSync(dir, { withFileTypes: true })",
  "          .filter((e) => e.isDirectory() && !e.name.startsWith('.') && e.name !== '承诺' && e.name !== '信息差')",
  "          .map((e) => e.name)",
  "      } catch { branches = [] }",
  "      return sendJson(res, 200, { ok: true, items, branches: branches })",
].join(eol)
if (!b.includes(old)) {
  const idx = b.indexOf('const items = listDocs(dir, ')
  console.log('DEBUG around:', JSON.stringify(b.slice(idx - 80, idx + 160)))
  throw new Error('backend anchor fail')
}
b = b.split(old).join(neu)
fs.writeFileSync(bp, b, 'utf8')
console.log('backend: setting-list + branches OK')
