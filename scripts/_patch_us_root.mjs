
import fs from 'node:fs'
const p = 'D:/NovelApp/core/update_state.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('_projects_root')) { console.log('update_state ALREADY'); process.exit(0) }
const old = [
  "def state_file(book):",
  "    p = os.path.join(CO.ROOT, 'projects', book, STATE_REL)",
  "    return p if os.path.exists(p) else None",
].join('\n')
if (!s.includes(old)) throw new Error('state_file anchor')
const neu = [
  "def _projects_root():",
  "    \"\"\"客户数据目录（与 coordinator.projects_root 同一套优先级）。",
  "    原来用 CO.ROOT（程序目录），客户数据在 %APPDATA% 时永远找不到状态表。\"\"\"",
  "    try:",
  "        return CO.projects_root()",
  "    except Exception:",
  "        return os.path.join(CO.ROOT, 'projects')",
  "",
  "",
  "def state_file(book):",
  "    p = os.path.join(_projects_root(), book, STATE_REL)",
  "    return p if os.path.exists(p) else None",
].join('\n')
s = s.split(old).join(neu)
fs.writeFileSync(p, s, 'utf8')
console.log('update_state: 数据目录修正')
