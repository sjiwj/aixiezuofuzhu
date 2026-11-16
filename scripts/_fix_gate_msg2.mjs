
import fs from 'node:fs'
const p = 'D:/NovelApp/scripts/gate_report.py'
let s = fs.readFileSync(p, 'utf8')
s = s.replace("    for k in ('message', 'detail', 'text', 'msg', 'reason'):",
              "    for k in ('message', 'item', 'detail', 'text', 'msg', 'reason'):")
fs.writeFileSync(p, s, 'utf8')
console.log('_msg +item')
