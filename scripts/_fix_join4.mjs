
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const BS = String.fromCharCode(92)
const ab = L.findIndex((x) => x.includes('nvlInfo("关于与许可"'))
if (ab < 0) throw new Error('about marker')
let aj = -1
for (let k = ab; k < ab + 20; k++) { if ((L[k] || '').trim().startsWith('].join(')) { aj = k; break } }
if (aj < 0) throw new Error('about join')
console.log('before:', JSON.stringify(L[aj]))
L[aj] = '\t\t\t\t].join("' + BS + 'n"' + '));'
console.log('after :', JSON.stringify(L[aj]))
fs.writeFileSync(p, L.join(eol), 'utf8')
