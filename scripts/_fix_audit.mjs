
import fs from 'node:fs'
const p = 'D:/NovelApp/scripts/audit_paths.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('cur_func')) { console.log('ALREADY'); process.exit(0) }
const old = [
  "    for i, raw in enumerate(lines, 1):",
  "        line = raw.rstrip('\\n')",
  "        stripped = line.strip()",
  "        if stripped.startswith('#'):",
  "            continue",
].join('\n')
const neu = [
  "    cur_func = ''",
  "    for i, raw in enumerate(lines, 1):",
  "        line = raw.rstrip('\\n')",
  "        stripped = line.strip()",
  "        mdef = re.match(r'def\\s+(\\w+)', stripped)",
  "        if mdef:",
  "            cur_func = mdef.group(1)",
  "        if stripped.startswith('#'):",
  "            continue",
  "        # projects_root / _projects_root 定义体内的 fallback 是合法的",
  "        if cur_func in ('projects_root', '_projects_root'):",
  "            continue",
].join('\n')
if (!s.includes(old)) throw new Error('loop anchor')
s = s.split(old).join(neu)
fs.writeFileSync(p, s, 'utf8')
console.log('audit_paths: fallback 排除')
