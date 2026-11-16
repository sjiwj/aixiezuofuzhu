
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const anchor = "        _dump_worker_prompt('writing', model, system, prompt, call_cfg, source='api/write')"
if (!s.includes(anchor)) throw new Error('unique anchor missing')
// 在 SSE 头与 send 定义之后才能发；所以插在 send 定义结束之后 —— 用 _dump 之后的 send 定义块末尾定位
const idx = s.indexOf(anchor)
const after = s.indexOf('        def send(ev):', idx)
if (after < 0) throw new Error('send def after dump')
// send 函数体结束：紧随其后 4 行处
const seg = s.slice(after, after + 400)
const m = seg.match(/        def send\(ev\):[\s\S]*?\n\n/)
if (!m) throw new Error('send body end')
const insertAt = after + m[0].length
const block = [
  "        # 分级提示：放在所有 return 之前，机检失败时客户也知道这章按什么级别写的",
  "        if tier_name != 'normal':",
  "            send({'type': 'tier', 'tier': tier_name, 'reason': tier_reason, 'model': model})",
  "",
].join(eol)
s = s.slice(0, insertAt) + block + s.slice(insertAt)
fs.writeFileSync(p, s, 'utf8')
console.log('tier event inserted after send() in _write_stream')
