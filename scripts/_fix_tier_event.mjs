
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes("send({'type': 'tier'") && s.includes('2170')) { console.log('x'); }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const anchor = [
  "        def send_or_die(ev):",
  "            if not send(ev):",
].join(eol)
if (!s.includes(anchor)) throw new Error('send_or_die anchor')
const neu = [
  "        # 分级提示（dry_run 与真写都发）：客户能看见这一章按什么级别、用什么模型",
  "        if tier_name != 'normal':",
  "            send({'type': 'tier', 'tier': tier_name, 'reason': tier_reason, 'model': model})",
  "",
  anchor,
].join(eol)
s = s.replace(anchor, neu)
// 去掉之前加在 done 前的那一处，避免重复
const dup = [
  "        if tier_name != 'normal':",
  "            send({'type': 'tier', 'tier': tier_name, 'reason': tier_reason, 'model': model})",
  "        send({'type': 'done', 'chars': len(body), 'added_chars': len(text), 'mode': mode,",
].join(eol)
if (s.includes(dup)) {
  s = s.replace(dup, "        send({'type': 'done', 'chars': len(body), 'added_chars': len(text), 'mode': mode,")
  console.log('dup removed')
}
fs.writeFileSync(p, s, 'utf8')
console.log('tier event moved to after send_or_die def')
