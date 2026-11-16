
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const BS = String.fromCharCode(92)

// 1) 先修 injected 那行（2505，1-based）
const i1 = 2504
if (!(L[i1] || '').includes('].join(')) throw new Error('injected join missing: ' + JSON.stringify(L[i1]))
L[i1] = '\t\t\t\t\t\t].join(" · ")) : null,'
console.log('fixed injected:', JSON.stringify(L[i1]))

// 2) 再修 about 的 join（1927/1928）
const i2 = L.findIndex((x, idx) => idx < 1950 && x.trim() === '].join("')
if (i2 < 0) throw new Error('about join missing')
console.log('about join at', i2 + 1, JSON.stringify(L[i2]), JSON.stringify(L[i2 + 1]))
L.splice(i2, 2, '\t\t\t\t].join("' + BS + 'n"' + '));')
console.log('fixed about:', JSON.stringify(L[i2]))

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('done')
