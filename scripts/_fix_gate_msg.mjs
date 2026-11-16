
import fs from 'node:fs'
const p = 'D:/NovelApp/scripts/gate_report.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('def _msg')) { console.log('ALREADY'); process.exit(0) }
s = s.replace("def load_json_file(path):", [
  "def _msg(i):",
  "    for k in ('message', 'detail', 'text', 'msg', 'reason'):",
  "        if i.get(k):",
  "            return str(i[k])",
  "    return ''",
  "",
  "",
  "def load_json_file(path):",
].join('\n'))
s = s.replace("        print('%-6s %-8s %s' % (lvl, i.get('ledger'), i.get('message')))",
              "        print('%-6s %-8s %s' % (lvl, i.get('ledger'), _msg(i)))")
fs.writeFileSync(p, s, 'utf8')
console.log('gate_report: _msg fallback')
