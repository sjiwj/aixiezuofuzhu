
import fs from 'node:fs'
const eol = '\n'
let total = 0
function fix(file, pairs) {
  let s = fs.readFileSync(file, 'utf8')
  let n = 0
  for (const [a, b] of pairs) {
    if (!s.includes(a)) { console.log('  MISS: ' + a.slice(0, 60)); continue }
    s = s.split(a).join(b)
    n++
  }
  fs.writeFileSync(file, s, 'utf8')
  console.log(file.split('core\\')[1] + ': ' + n + ' 处')
  total += n
}

// 1) coordinator.py —— 本文件已有 projects_root()
fix('D:/NovelApp/core/coordinator.py', [
  ["    proj = os.path.join(ROOT, 'projects')\n    if os.path.isdir(proj):\n        for name in sorted(os.listdir(proj)):\n            cand = os.path.join(proj, name, '设定库', '世界地图.md')",
   "    proj = projects_root()\n    if os.path.isdir(proj):\n        for name in sorted(os.listdir(proj)):\n            cand = os.path.join(proj, name, '设定库', '世界地图.md')"],
  ["    proj = os.path.join(ROOT, 'projects')\n    if os.path.isdir(proj):\n        for name in sorted(os.listdir(proj)):\n            cand = os.path.join(proj, name, '设定库', '角色状态.md')",
   "    proj = projects_root()\n    if os.path.isdir(proj):\n        for name in sorted(os.listdir(proj)):\n            cand = os.path.join(proj, name, '设定库', '角色状态.md')"],
  ["        for dirpath, _, files in os.walk(os.path.join(ROOT, 'projects')):",
   "        for dirpath, _, files in os.walk(projects_root()):"]
])

// 2) infogap.py —— 加 _projects_root
let ig = fs.readFileSync('D:/NovelApp/core/infogap.py', 'utf8')
if (!ig.includes('def _projects_root')) {
  ig = ig.replace('def gap_dir(book):', [
    'def _projects_root():',
    '    \"\"\"\u5ba2\u6237\u6570\u636e\u76ee\u5f55\uff08\u4e0e coordinator.projects_root \u540c\u4e00\u5957\u4f18\u5148\u7ea7\uff09\u3002',
    '    \u539f\u6765\u76f4\u63a5\u62fc ROOT\uff08\u7a0b\u5e8f\u76ee\u5f55\uff09\uff0c\u5ba2\u6237\u6570\u636e\u5728 %APPDATA% \u65f6\u8bfb\u4e0d\u5230\u3002\"\"\"',
    '    try:',
    '        import coordinator as _CO',
    '        return _CO.projects_root()',
    '    except Exception:',
    '        return os.path.join(ROOT, \"projects\")',
    '',
    '',
    'def gap_dir(book):'
  ].join('\n'))
  fs.writeFileSync('D:/NovelApp/core/infogap.py', ig, 'utf8')
}
fix('D:/NovelApp/core/infogap.py', [
  ['return os.path.join(ROOT, "projects", book, "设定库", "信息差")', 'return os.path.join(_projects_root(), book, "设定库", "信息差")'],
  ['d = os.path.join(ROOT, "projects", book, "章节")', 'd = os.path.join(_projects_root(), book, "章节")'],
  ['d = os.path.join(ROOT, "projects", book, "设定库", "角色卡.md")', 'd = os.path.join(_projects_root(), book, "设定库", "角色卡.md")']
])

// 3) update_ledgers.py / precheck.py / review_history.py
fix('D:/NovelApp/core/update_ledgers.py', [
  ["return os.path.join(CO.ROOT, 'projects', book, '设定库', name)", "return os.path.join(CO.projects_root(), book, '设定库', name)"]
])
fix('D:/NovelApp/core/precheck.py', [
  ["p = os.path.join(CO.ROOT, 'projects', book, '设定库', '角色卡.md')", "p = os.path.join(CO.projects_root(), book, '设定库', '角色卡.md')"]
])
let rh = fs.readFileSync('D:/NovelApp/core/review_history.py', 'utf8')
if (!rh.includes('def _projects_root')) {
  rh = rh.replace('def reports_dir(book):', [
    'def _projects_root():',
    '    try:',
    '        import coordinator as _CO',
    '        return _CO.projects_root()',
    '    except Exception:',
    '        return os.path.join(ROOT, "projects")',
    '',
    '',
    'def reports_dir(book):'
  ].join('\n'))
  fs.writeFileSync('D:/NovelApp/core/review_history.py', rh, 'utf8')
}
fix('D:/NovelApp/core/review_history.py', [
  ['return os.path.join(ROOT, "projects", book, "reports")', 'return os.path.join(_projects_root(), book, "reports")']
])
console.log('total fixes:', total)
