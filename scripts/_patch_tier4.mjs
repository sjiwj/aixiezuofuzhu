
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
// 找到写章的 usage 事件（其后紧跟 log_usage('write'）
let changed = 0
for (let i = 0; i < L.length; i++) {
  if (L[i].includes("'usage_estimated': bool(billing.get('usage_estimated'))})") && (L[i + 1] || '').includes("log_usage('write'")) {
    L[i] = L[i].replace("'usage_estimated': bool(billing.get('usage_estimated'))})",
      "'usage_estimated': bool(billing.get('usage_estimated')), 'tier': tier_name, 'tier_reason': tier_reason, 'tier_model': (model if tier_name != 'normal' else '')})")
    changed++
  }
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('usage event got tier fields:', changed)
