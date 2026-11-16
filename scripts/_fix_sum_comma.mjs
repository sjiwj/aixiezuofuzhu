
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
let fixed = 0
for (let i = 0; i < L.length; i++) {
  if (L[i] === T(6) + 'sum' && (L[i + 1] || '').trim() === 'revisePanel') {
    L[i] = T(6) + 'sum,'
    fixed++
  }
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('fixed commas:', fixed)
