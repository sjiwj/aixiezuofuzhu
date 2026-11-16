
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
// 删除 1875..1880（0-based 1874..1879）
const i = L.findIndex((x, idx) => idx > 1800 && idx < 1900 && x.includes("if isinstance(ev, dict) and ev.get('type') == 'team_done':") && (L[idx + 3] || '').includes('_b_rev'))
if (i < 0) throw new Error('misplaced block not found')
console.log('deleting lines', i + 1, '..', i + 6)
console.log(JSON.stringify(L.slice(i, i + 6), null, 1))
L.splice(i, 6)
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('deleted')
