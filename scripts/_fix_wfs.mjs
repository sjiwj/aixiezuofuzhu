
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/index.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const i = L.findIndex((x) => x.includes("fs.writeFileSync(file, '# ' + name + '") && !x.includes(', ' + String.fromCharCode(39) + 'utf8'))
if (i < 0) throw new Error('broken line not found')
console.log('fix at', i + 1, JSON.stringify(L[i]), JSON.stringify(L[i + 1]), JSON.stringify(L[i + 2]))
const BS = String.fromCharCode(92)
L.splice(i, 3, "        fs.writeFileSync(file, '# ' + name + '" + BS + "n" + BS + "n', 'utf8')")
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('fixed writeFileSync line')
