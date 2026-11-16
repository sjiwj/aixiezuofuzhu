
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)

// 1) 润色那处（1918 事件后的 log_usage('write', book, ch,...)）改成 polish + chapter
let fixedPolish = 0, addedWrite = 0
for (let i = 0; i < L.length; i++) {
  if (L[i].includes("log_usage('write', book, ch, billing)")) {
    L[i] = L[i].replace("log_usage('write', book, ch, billing)", "log_usage('polish', book, chapter, billing)")
    fixedPolish++
  }
}
// 2) 写章 usage 事件后补记账（2188 处的块，第 6 行是 usage_estimated 结束）
for (let i = 0; i < L.length; i++) {
  if (L[i].includes("send({'type': 'usage',") && (L[i + 5] || '').includes("'usage_estimated': bool(billing.get('usage_estimated'))})")) {
    // 只在写章那一处（其前有 'text = CO.sanitize_worker_text'）
    if ((L[i - 1] || '').includes("billing = resp.get('_billing')") && (L[i - 2] || '').includes('sanitize_worker_text')) {
      L.splice(i + 6, 0, '            log_usage('write', book, ch, billing)')
      addedWrite++
    }
  }
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('polish fixed:', fixedPolish, '| write added:', addedWrite)
