
import fs from 'node:fs'
const ref = 'D:/NovelApp/_archive/restore/index-080.js'
const cur = 'D:/NovelApp/plugin/lib/index.js'
const rl = fs.readFileSync(ref, 'utf8').split(/\r?\n/)
const cl = fs.readFileSync(cur, 'utf8').split(/\r?\n/)
const ri = rl.findIndex((x) => x.includes("'/novelapp/setting-new'"))
const ci = cl.findIndex((x) => x.includes("'/novelapp/setting-new'"))
console.log('ref setting-new at', ri + 1, '| cur at', ci + 1)
console.log('--- REF 附近 ---')
rl.slice(ri, ri + 22).forEach((x, k) => console.log((ri + 1 + k) + '|' + x))
console.log('--- CUR 附近（末尾 12 行）---')
cl.slice(ci + 12, ci + 30).forEach((x, k) => console.log((ci + 13 + k) + '|' + x))
