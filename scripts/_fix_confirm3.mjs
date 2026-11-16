
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const pairs = [
  ['？' + eol + eol + '文件会进回收站', '？ 文件会进回收站'],
  ['？' + eol + eol + '这本书的全部章节', '？ 这本书的全部章节'],
  ['？' + eol + eol + '里面的设定文件', '？ 里面的设定文件'],
]
let n = 0
for (const [a, b] of pairs) { while (s.includes(a)) { s = s.split(a).join(b); n++ } }
fs.writeFileSync(p, s, 'utf8')
console.log('joined', n)
