
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
let fixedPolish = 0, addedWrite = 0
for (let i = 0; i < L.length; i++) {
  if (L[i].includes("log_usage('write', book, ch, billing)")) {
    L[i] = L[i].replace("log_usage('write', book, ch, billing)", "log_usage('polish', book, chapter, billing)")
    fixedPolish++
  }
}
for (let i = 0; i < L.length; i++) {
  if (!L[i].includes("send({'type': 'usage',")) continue
  const tail = (L[i + 5] || '')
  if (!tail.includes("'usage_estimated'")) continue
  if (!(L[i - 1] || '').includes("billing = resp.get('_billing')")) continue
  if (!(L[i - 2] || '').includes('sanitize_worker_text')) continue
  L.splice(i + 6, 0, "            log_usage('write', book, ch, billing)")
  addedWrite++
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('polish fixed:', fixedPolish, '| write added:', addedWrite)
