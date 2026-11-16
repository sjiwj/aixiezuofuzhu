
import fs from 'node:fs'
const p = 'D:/NovelApp/core/coordinator.py'
let s = fs.readFileSync(p, 'utf8')
const a = "    proj = os.path.join(ROOT, 'projects')"
const b = "    proj = projects_root()"
const n = s.split(a).length - 1
s = s.split(a).join(b)
fs.writeFileSync(p, s, 'utf8')
console.log('coordinator proj lines replaced:', n)
