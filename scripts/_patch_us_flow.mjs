
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('role_state')) { console.log('server ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const anchor = "        send({'type': 'done', 'chars': len(body), 'added_chars': len(text), 'mode': mode,"
if (!s.includes(anchor)) throw new Error('done anchor')
const add = [
  "        # 角色状态表更新：六问第 2 问的数据源，失败不影响主流程",
  "        try:",
  "            import update_state as US",
  "            _us = US.update_one(abs_rel, book)",
  "            send({'type': 'role_state', 'ok': bool(_us.get('ok')),",
  "                  'changed': _us.get('changed') or [],",
  "                  'note': _us.get('note') or _us.get('error') or ''})",
  "        except Exception as _e:",
  "            send({'type': 'role_state', 'ok': False, 'error': '%s: %s' % (type(_e).__name__, _e)})",
  "",
  anchor,
].join(eol)
s = s.replace(anchor, add)
fs.writeFileSync(p, s, 'utf8')
console.log('server.py: +role_state 更新')
