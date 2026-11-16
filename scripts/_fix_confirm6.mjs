
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const pairs = [
  ['？\n\n文件会进回收站', '？ 文件会进回收站'],
  ['？\n\n这本书的全部章节', '？ 这本书的全部章节'],
  ['？\n\n里面的设定文件', '？ 里面的设定文件'],
  ['？\r\n\r\n文件会进回收站', '？ 文件会进回收站'],
  ['？\r\n\r\n这本书的全部章节', '？ 这本书的全部章节'],
  ['？\r\n\r\n里面的设定文件', '？ 里面的设定文件'],
]
let n = 0
for (const [a, b] of pairs) { if (s.includes(a)) { s = s.split(a).join(b); n++ } }
fs.writeFileSync(p, s, 'utf8')
console.log('replaced', n, '| still broken:', s.includes('？\n\n') || s.includes('？\r\n\r\n'))
