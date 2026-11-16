
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('name === "未分组")) return')) { console.log('frontend ALREADY'); process.exit(0) }
const old = '\t\t\t\tif (!name) return;'
if (!s.includes(old)) throw new Error('branch loop anchor')
const neu = '\t\t\t\tif (!name || name === "未分组") return;'
s = s.split(old).join(neu)
fs.writeFileSync(p, s, 'utf8')
console.log('frontend: 跳过 未分组')
