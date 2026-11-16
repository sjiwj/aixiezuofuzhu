
import fs from 'node:fs'
const fp = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(fp, 'utf8')
if (s.includes('SKIP_PROMISE_IG')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const old = [
  '\t\t\t\tconst rel = String(it.path || "").replace(/^设定库\\//, "");',
  '\t\t\t\tconst segs = rel.split("/");',
].join(eol)
const neu = [
  '\t\t\t\tconst rel = String(it.path || "").replace(/^设定库\\//, "");',
  '\t\t\t\t/* SKIP_PROMISE_IG：承诺 / 信息差 已经单独成组，不能再混进分支，否则重复计数 */',
  '\t\t\t\tif (/^(承诺|信息差)\\//.test(rel)) return;',
  '\t\t\t\tconst segs = rel.split("/");',
].join(eol)
if (!s.includes(old)) throw new Error('anchor fail')
s = s.split(old).join(neu)
fs.writeFileSync(fp, s, 'utf8')
console.log('patched skip promise/infogap dirs')
