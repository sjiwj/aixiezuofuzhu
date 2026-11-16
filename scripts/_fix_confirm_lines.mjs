
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
let fixed = 0
for (let i = 0; i < L.length; i++) {
  if (L[i].includes('await nvlConfirm(') && !L[i].trim().endsWith(');')) {
    let j = i
    const parts = [L[i]]
    while (j + 1 < L.length && !L[j].trim().endsWith(');')) { j++; parts.push(L[j].trim()) }
    const merged = parts.map((x, k) => k === 0 ? x.replace(/\s+$/, '') : x).join(' ')
    L.splice(i, j - i + 1, merged)
    fixed++
  }
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('merged', fixed)
