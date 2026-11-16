
import fs from 'node:fs'
const p = 'D:/NovelApp/core/write_context.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const i = L.findIndex((x) => x.trim() === "if '主角' in n:")
if (i < 0) { console.log('no anchor'); process.exit(0) }
L[i] = ' '.repeat(8) + "if '主角' in n and '配角' not in n:"
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('patched: 排除配角')
