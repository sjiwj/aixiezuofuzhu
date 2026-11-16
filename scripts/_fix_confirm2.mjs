
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const targets = [3279, 1086, 1075]
let done = 0
for (const ln of targets) {
  const i = ln - 1
  const a = L[i] || ''
  if (!a.includes('await nvlConfirm(')) { console.log('skip', ln, JSON.stringify(a.slice(0, 60))); continue }
  const b = (L[i + 1] || '').trim()
  if (!b) { console.log('no cont at', ln); continue }
  const merged = a.replace(/\s+$/, '') + ' ' + b
  L.splice(i, 2, merged)
  done++
  console.log('merged at', ln)
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('done', done)
