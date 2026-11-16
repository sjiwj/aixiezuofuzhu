
import fs from 'node:fs'
const p = 'D:/NovelApp/core/test_api.py'
let s = fs.readFileSync(p, 'utf8')
let n = 0
for (const [a, b] of [
  ["root_proj = os.path.join(ROOT, 'projects', PROJ)", "root_proj = os.path.join(CO.projects_root(), PROJ)"],
  ["rep_dir = os.path.join(ROOT, 'projects', PROJ, 'reports')", "rep_dir = os.path.join(CO.projects_root(), PROJ, 'reports')"],
]) {
  if (s.includes(a)) { s = s.split(a).join(b); n++ }
}
// 确保 import coordinator as CO
if (!/import coordinator as CO/.test(s)) {
  s = s.replace('import', 'import coordinator as CO  # noqa: E402\nimport', 1)
  console.log('added CO import')
}
fs.writeFileSync(p, s, 'utf8')
console.log('test_api fixed:', n)
