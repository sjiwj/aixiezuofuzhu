
import fs from 'node:fs'
const p = 'D:/NovelApp/core/write_context.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const i = L.findIndex((x) => x.includes("if '甲' in n or '主角' in n:"))
if (i < 0) { console.log('ALREADY/none'); process.exit(0) }
const T = (n) => '	'.repeat(0) + ' '.repeat(n)
L[i] = T(8) + "if '主角' in n:"
// 在 break 之后补兜底
let j = -1
for (let k = i; k < i + 6; k++) { if ((L[k] || '').trim() === 'break') { j = k; break } }
if (j > 0) L.splice(j + 1, 0, T(4) + "if not main_state and states:", T(8) + "main_state = states[0]")
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('patched at line', i + 1)
