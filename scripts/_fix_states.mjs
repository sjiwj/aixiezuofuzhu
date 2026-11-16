
import fs from 'node:fs'
const p = 'D:/NovelApp/core/write_context.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const i = L.findIndex((x) => x.trim() === "if not names:")
if (i < 0) { console.log('no anchor'); process.exit(0) }
const T = (n) => ' '.repeat(n)
const add = [
  T(4) + '# 主角必须在列表里且排第一（六问第 2 问只看 states[0]）',
  T(4) + "mains = [n for n in sections if '主角' in n and '配角' not in n]",
  T(4) + 'if mains:',
  T(8) + 'names = mains[:1] + [n for n in (names or []) if n not in mains]',
]
L.splice(i, 0, ...add)
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('_states: 主角置顶')
