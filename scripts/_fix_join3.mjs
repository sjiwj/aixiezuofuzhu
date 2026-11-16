
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const BS = String.fromCharCode(92)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// A) injected 的 join（在「本次带上的资料」之后 10 行内）
const inj = find('本次带上的资料')
if (inj < 0) throw new Error('injected marker')
let ij = -1
for (let k = inj; k < inj + 12; k++) { if ((L[k] || '').trim().startsWith('].join(')) { ij = k; break } }
if (ij < 0) throw new Error('injected join')
console.log('injected join at', ij + 1, JSON.stringify(L[ij]))
L[ij] = '\t\t\t\t\t\t].join(" · ")) : null,'

// B) about 的 join（在 nvlInfo("关于与许可" 之后）
const ab = find('nvlInfo("关于与许可"')
if (ab < 0) throw new Error('about marker')
let aj = -1
for (let k = ab; k < ab + 20; k++) { if ((L[k] || '').trim().startsWith('].join(')) { aj = k; break } }
if (aj < 0) throw new Error('about join')
console.log('about join at', aj + 1, JSON.stringify(L[aj]), JSON.stringify(L[aj + 1]))
const needsMerge = !(L[aj].trim().endsWith('));'))
if (needsMerge) {
  L.splice(aj, 2, '\t\t\t\t].join("' + BS + 'n"' + '));')
  console.log('about join rebuilt')
} else {
  console.log('about join already ok')
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('done')
