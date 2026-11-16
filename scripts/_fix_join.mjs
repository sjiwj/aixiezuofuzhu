
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const i = L.findIndex((x) => x.trim().startsWith('].join("') && !x.trim().endsWith('));'))
if (i < 0) throw new Error('join line not found')
console.log('before:', JSON.stringify(L[i]), JSON.stringify(L[i + 1]))
const BS = String.fromCharCode(92)
L.splice(i, 2, '\t\t\t\t].join("' + BS + 'n"' + '));')
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('after:', JSON.stringify(L[i]))
