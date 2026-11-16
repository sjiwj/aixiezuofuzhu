
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes("type': 'promises'")) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const anchor = "        # 角色状态表更新：六问第 2 问的数据源，失败不影响主流程"
if (!s.includes(anchor)) throw new Error('role_state anchor')
const add = [
  "        # 承诺自动 touch：只有章纲明确指定（plan）才登记；auto 只提示不猜",
  "        try:",
  "            import write_context as WC",
  "            import promises as PM",
  "            _outline = WC._outline_struct(book, ch)",
  "            _chosen, _src = WC._pick_promises(book, ch, _outline)",
  "            _ids = [str(_p.get('编号') or '') for _p in (_chosen or []) if _p.get('编号')]",
  "            if _src == 'plan' and _ids:",
  "                for _pid in _ids:",
  "                    PM.touch(book, _pid, ch, '推进', '四层写完后自动登记')",
  "                send({'type': 'promises', 'ok': True, 'source': 'plan', 'touched': _ids})",
  "            elif _ids:",
  "                send({'type': 'promises', 'ok': True, 'source': 'auto', 'suggested': _ids,",
  "                      'note': '自动挑的，没有自动登记；确认后在设定库手动 touch'})",
  "            else:",
  "                send({'type': 'promises', 'ok': True, 'source': 'none', 'touched': []})",
  "        except Exception as _pe:",
  "            send({'type': 'promises', 'ok': False, 'error': '%s: %s' % (type(_pe).__name__, _pe)})",
  "",
  anchor,
].join(eol)
s = s.replace(anchor, add)
fs.writeFileSync(p, s, 'utf8')
console.log('server.py: +promises touch')
