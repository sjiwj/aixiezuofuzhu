
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const BS = String.fromCharCode(92)

function splitOutsideStrings(line) {
  let out = '', inStr = false, q = ''
  for (let i = 0; i < line.length; i++) {
    const c = line[i]
    if (inStr) {
      if (c === BS) { out += c + (line[i + 1] || ''); i++; continue }
      if (c === q) inStr = false
      out += c
      continue
    }
    if (c === '"' || c === "'") { inStr = true; q = c; out += c; continue }
    if (c === BS && line[i + 1] === 'n') { out += '\u0001NL\u0001'; i++; continue }
    out += c
  }
  return out.split('\u0001NL\u0001')
}

const i = L.findIndex((x) => x.includes('const r = await saveChapter(target, "# " + safe + "') && x.length > 400)
if (i < 0) { console.log('no long line'); process.exit(0) }
const parts = splitOutsideStrings(L[i])
console.log('split into', parts.length, 'lines')
L.splice(i, 1, ...parts)
// 修回正则里的反斜杠
for (let k = 0; k < L.length; k++) {
  if (L[k].includes('.replace(/.md$/i')) L[k] = L[k].split('.replace(/.md$/i').join('.replace(/' + BS + '.md$/i')
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('done')
