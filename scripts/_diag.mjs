
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
const s = fs.readFileSync(p, 'utf8')
console.log('len', s.length, 'contains nvlConfirm', s.includes('nvlConfirm'))
const idx = s.indexOf('await nvlConfirm')
console.log('idx', idx)
if (idx > 0) console.log(JSON.stringify(s.slice(idx - 40, idx + 160)))
const L = s.split(/\r?\n/)
console.log('lines', L.length)
L.forEach((x, k) => { if (x.includes('nvlConfirm')) console.log(k + 1, JSON.stringify(x.slice(0, 90))) })
