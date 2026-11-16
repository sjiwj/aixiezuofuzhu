
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
let n = 0
for (let i = 0; i < L.length; i++) {
  if (!L[i].includes('await nvlConfirm(')) continue
  let j = i + 1
  while (j < L.length && L[j].trim() === '') j++
  if (j >= L.length) continue
  const cont = L[j].trim()
  if (!(cont.startsWith('文件会进回收站') || cont.startsWith('这本书的全部章节') || cont.startsWith('里面的设定文件'))) continue
  L[i] = L[i].replace(/\s+$/, '') + ' ' + cont
  L.splice(i + 1, j - i)
  n++
  console.log('joined at line', i + 1)
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('total', n)
