
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const a = L.findIndex((x) => x.includes('nvlInfo("关于与许可", ['))
if (a < 0) throw new Error('about array start')
let b = -1
for (let k = a; k < a + 20; k++) { if ((L[k] || '').includes('].join("\\n"));')) { b = k; break } }
if (b < 0) throw new Error('about array end')
let n = 0
for (let k = a + 1; k < b; k++) {
  const t = (L[k] || '').trim()
  if (!t) continue
  if (!t.endsWith(',')) { L[k] = L[k] + ','; n++ }
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('added commas', n, 'lines', a + 1, b + 1)
