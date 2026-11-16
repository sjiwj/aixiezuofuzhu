
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const i = L.findIndex((x) => x.trim() === 'className: "nvl-review__path",')
if (i < 0) throw new Error('path class line')
const prev = (L[i - 1] || '').trim()
if (prev.startsWith('h("input"')) { console.log('already has input'); process.exit(0) }
if (!prev.startsWith('].join(')) throw new Error('unexpected prev: ' + JSON.stringify(L[i - 1]))
L.splice(i, 0, '\t\t\t\t\t\th("input", {')
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('restored h("input" at', i + 1)
