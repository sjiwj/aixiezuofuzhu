
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const res = [
  [new RegExp('\\?\\s*\\r?\\n\\s*\\r?\\n\\s*文件会进回收站'), '？ 文件会进回收站'],
  [new RegExp('\\?\\s*\\r?\\n\\s*\\r?\\n\\s*这本书的全部章节'), '？ 这本书的全部章节'],
  [new RegExp('\\?\\s*\\r?\\n\\s*\\r?\\n\\s*里面的设定文件'), '？ 里面的设定文件'],
]
let n = 0
for (const [re, to] of res) { const before = s; s = s.replace(re, to); if (s !== before) n++ }
fs.writeFileSync(p, s, 'utf8')
console.log('regex replaced', n)
