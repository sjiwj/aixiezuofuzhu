
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const i = L.findIndex((x) => x.includes("head = '\u4f60\u662f\u300a%s\u300b\u7684\u4f5c\u8005"))
if (i < 0) throw new Error('head line')
// 该行 + 后面两行（空行 + ' % (...)）共 3 行被拆坏
const fixed = "    head = ('\u4f60\u662f\u300a%s\u300b\u7684\u4f5c\u8005\u3002\u4e0b\u9762\u662f\u4f60\u521a\u60f3\u5230\u7684\u4e00\u53e5\u8bdd\uff0c\u8bf7\u628a\u5b83\u5c55\u5f00\u6210\u4e00\u6bb5\u6b63\u6587\u3002' + chr(10) + chr(10)",
  "           % (book or '\u8fd9\u672c\u4e66'))"
L.splice(i, 3, ...fixed.split(eol))
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('head fixed')
