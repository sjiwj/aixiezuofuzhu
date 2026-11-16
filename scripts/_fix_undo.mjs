
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
let removed = 0
for (let i = L.length - 1; i >= 0; i--) {
  if (L[i].includes('lastBackup ? h("button"') && L[i].includes('撤销这次改稿')) {
    L.splice(i, 1)
    removed++
  }
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('removed undo button lines:', removed)
