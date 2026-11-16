
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/index.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const BS_N = String.fromCharCode(92) + 'n'
let L = s.split(eol)
let fixed = 0
for (let i = 0; i < L.length; i++) {
  if (L[i].includes(BS_N) && L[i].includes('/novelapp/')) {
    const parts = L[i].split(BS_N)
    L.splice(i, 1, ...parts)
    fixed++
    i += parts.length - 1
  }
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('fixed single-line blocks:', fixed)
