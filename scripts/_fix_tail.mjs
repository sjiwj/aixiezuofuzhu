
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const BS = String.fromCharCode(92)
const i = L.findIndex((x) => x.trim().startsWith('const tail = "'))
if (i < 0) throw new Error('tail line')
console.log('before lines:', JSON.stringify(L.slice(i, i + 4)))
// 合并直到某行以 "; 结尾（即 '";' 出现在行尾）
let j = i
const buf = []
while (j < L.length) {
  buf.push(L[j])
  if (L[j].trim().endsWith('";')) break
  j++
}
const merged = buf.join('\n')
const safe = merged.split('\n').join(BS + 'n')
L.splice(i, j - i + 1, safe)
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('after:', JSON.stringify(safe))
