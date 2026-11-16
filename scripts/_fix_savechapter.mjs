
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const BS = String.fromCharCode(92)
const i = L.findIndex((x) => x.includes('const r = await saveChapter(target, "# " + safe + "') && !x.trim().endsWith('";'))
if (i < 0) { console.log('no broken line'); process.exit(0) }
let j = i
const buf = []
while (j < L.length) { buf.push(L[j]); if (L[j].trim().endsWith('";')) break; j++ }
const merged = buf.join('\n').split('\n').join(BS + 'n')
L.splice(i, j - i + 1, merged)
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('fixed at', i + 1, '->', JSON.stringify(merged))
