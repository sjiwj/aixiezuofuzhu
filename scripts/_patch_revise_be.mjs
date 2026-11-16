
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('cliche_ban_block')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

// 1) 写章主路径也要吃套话禁令（之前只加在 chat_worker，主路径漏了）
const old1 = "        system = CO.WORKER_SYSTEM.get('writing') or ''"
const new1 = [
  "        system = CO.WORKER_SYSTEM.get('writing') or ''",
  "        # 套话禁令：四层写章走的是这里，不是 chat_worker —— 两处都要注入",
  "        try:",
  "            _ban = CO.cliche_ban_block()",
  "            if _ban:",
  "                system = (system + _ban).strip()",
  "        except Exception:",
  "            pass",
].join(eol)
if (!s.includes(old1)) throw new Error('system anchor')
s = s.split(old1).join(new1)

// 2) 支持 notes（审稿意见）注入 prompt
const old2 = "        if mode == 'append':"
const new2 = [
  "        _notes = data.get('notes')",
  "        if isinstance(_notes, list) and _notes:",
  "            _lines = [str(x).strip() for x in _notes if str(x).strip()][:8]",
  "            if _lines:",
  "                prompt = (prompt + '\\n\\n【审稿意见（逐条处理，改完不许再犯）】\\n'",
  "                          + '\\n'.join('- ' + x for x in _lines))",
  "        if mode == 'append':",
].join(eol)
if (!s.includes(old2)) throw new Error('append anchor')
s = s.replace(old2, new2, )
fs.writeFileSync(p, s, 'utf8')
console.log('server.py: 写章注入 cliche 禁令 + notes（审稿意见）')
