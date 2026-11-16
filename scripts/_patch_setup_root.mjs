
import fs from 'node:fs'
const p = 'D:/NovelApp/core/check_setup.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('_projects_root')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

// 1) 加数据目录函数
const anchor = 'def read(p):'
const fns = [
  'def _projects_root():',
  '    """客户数据目录（与 coordinator.projects_root 同一套优先级）。',
  '    2026-11-07 修：原来用 CO.ROOT（程序安装目录），客户数据在 %APPDATA% 时读不到。"""',
  '    try:',
  '        return CO.projects_root()',
  '    except Exception:',
  '        return os.path.join(CO.ROOT, "projects")',
  '',
  '',
  'def read(p):',
].join(eol)
if (!s.includes(anchor)) throw new Error('read anchor')
s = s.replace(anchor, fns)

// 2) run 里两处改用数据目录
s = s.replace("    base = os.path.join(CO.ROOT, 'projects', book, '设定库')",
              "    base = os.path.join(_projects_root(), book, '设定库')")
s = s.replace("        chapters = os.path.join(CO.ROOT, 'projects', book, '章节')",
              "        chapters = os.path.join(_projects_root(), book, '章节')")

fs.writeFileSync(p, s, 'utf8')
console.log('check_setup: data dir fixed')
