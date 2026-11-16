
import fs from 'node:fs'
const p = 'D:/NovelApp/core/write_context.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const i = L.findIndex((x) => x.includes('mains = [n for n in sections'))
if (i < 0) { console.log('no anchor'); process.exit(0) }
const T = (n) => ' '.repeat(n)
// 替换原来的 mains 判定：从原文找「## XXX（主角）」
L.splice(i, 3,
  T(4) + "# 主角名从原文拿（parse_state_sections 会把括号内容去掉，",
  T(4) + "# 所以 sections 的 key 里已经没有「主角」两字）",
  T(4) + "m = re.search(r'^##\\s*([^（(\\n]+)[（(][^）)]*主角[^）)]*[）)]', text, re.M)",
  T(4) + "if m:",
  T(8) + "mn = m.group(1).strip()",
  T(8) + "if mn in sections:",
  T(12) + "names = [mn] + [n for n in (names or []) if n != mn]",
)
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('_states: 从原文取主角名')
