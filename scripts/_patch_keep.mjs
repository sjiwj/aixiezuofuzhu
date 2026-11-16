
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/index.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('未分组")) return')) { console.log('backend ALREADY'); process.exit(0) }
const old = "          .filter((e) => e.isDirectory() && !e.name.startsWith('.') && e.name !== '承诺' && e.name !== '信息差')"
if (!s.includes(old)) throw new Error('branches filter anchor')
const neu = "          .filter((e) => e.isDirectory() && !e.name.startsWith('.') && e.name !== '承诺' && e.name !== '信息差' && e.name !== '未分组')"
s = s.split(old).join(neu)
fs.writeFileSync(p, s, 'utf8')
console.log('backend: 过滤 未分组')
