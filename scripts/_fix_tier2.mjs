
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)

// 1) 删除错位段（在 _polish 里，2022 之前）
let removed = 0
for (let i = L.length - 1; i >= 0; i--) {
  if (i < 2020 && L[i].includes('# 分级提示（dry_run 与真写都发）')) {
    // 删该行 + 之后 4 行（if / send / 空行）
    L.splice(i, 5)
    removed++
  }
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('removed misplaced tier block:', removed)

// 2) 在两个 done 前各插一次（锚点更精确）
s = fs.readFileSync(p, 'utf8')
const dryDone = "        if dry_run:"
// 找 dry_run 分支（_write_stream 内，且后面紧跟 send done dry_run）
const marker = "send({'type': 'done', 'dry_run': True,"
const wi = s.indexOf('def _write_stream')
const mi = s.indexOf(marker, wi)
if (mi < 0) throw new Error('dry done')
// 在该 send 所在行前插
const lineStart = s.lastIndexOf('\n', mi) + 1
const indent = s.slice(lineStart, mi)
const block = [
  "        if tier_name != 'normal':",
  "            send({'type': 'tier', 'tier': tier_name, 'reason': tier_reason, 'model': model})",
].join(eol) + eol + indent
s = s.slice(0, lineStart) + block + s.slice(lineStart)
console.log('inserted before dry_run done')

// 3) 真写盘的 done 前也插
const realDone = "        send({'type': 'done', 'chars': len(body), 'added_chars': len(text), 'mode': mode,"
if (!s.includes(realDone)) throw new Error('real done')
s = s.replace(realDone, [
  "        if tier_name != 'normal':",
  "            send({'type': 'tier', 'tier': tier_name, 'reason': tier_reason, 'model': model})",
  realDone,
].join(eol))
console.log('inserted before real done')
fs.writeFileSync(p, s, 'utf8')
