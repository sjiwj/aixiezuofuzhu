
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)

// 定位并重建 dry_run 分支
const i = L.findIndex((x) => x === "        if dry_run:")
if (i < 0) throw new Error('dry_run if')
// 找到 return 结束（2280 后第一处 "            return" 紧接空行）
let j = -1
for (let k = i; k < i + 16; k++) { if (L[k] === "            return") { j = k; break } }
if (j < 0) throw new Error('dry return')
console.log('rebuilding lines', i + 1, '..', j + 1)
const block = [
  "        if dry_run:",
  "            # 只写出来给客户看：不写盘、不 commit、不改章节状态、不备份",
  "            if tier_name != 'normal':",
  "                send({'type': 'tier', 'tier': tier_name, 'reason': tier_reason, 'model': model})",
  "            send({'type': 'done', 'dry_run': True, 'chars': len(text), 'mode': mode,",
  "                  'path': rel.replace(os.sep, '/'), 'precheck': pre,",
  "                  'next': {'stage': 'preview', 'options': [",
  "                      {'id': 'apply', 'label': '用这个（写回文件）', 'enabled': True},",
  "                      {'id': 'discard', 'label': '保留原文', 'enabled': True}]},",
  "                  'note': 'dry_run：没有写盘、没有 commit、章节状态未变'})",
  "            return",
]
L.splice(i, j - i + 1, ...block)
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('rebuilt')
