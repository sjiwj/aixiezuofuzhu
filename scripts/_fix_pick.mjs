
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const i = L.findIndex((x) => x.includes('className: "nvl-rev__pick"'))
if (i < 0) { console.log('no misplaced block'); process.exit(0) }
let j = -1
for (let k = i; k < i + 14; k++) { if ((L[k] || '').includes('h("span", null, "用")),')) { j = k; break } }
if (j < 0) throw new Error('block end')
console.log('removing lines', i + 1, '..', j + 1)
L.splice(i, j - i + 1)
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('removed')
