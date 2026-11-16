
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const old = 'const note = err || (!configured ? "门禁未配置：敏感词表 / 事实核对项为空" : (st === "inconclusive" && allSkippedUnconfigured ? "这次没做机械检查：没配置敏感词表和核对规则" : ""));'
if (!s.includes(old)) { console.log('anchor miss'); process.exit(1) }
const neu = 'const note = err || (!configured ? "门禁未配置：敏感词表 / 事实核对项为空" : (allSkippedUnconfigured && !hits.length && !warned.length && !blocked.length ? "这次没做机械检查：没配置敏感词表和核对规则" : ""));'
s = s.split(old).join(neu)
fs.writeFileSync(p, s, 'utf8')
console.log('note condition updated')
