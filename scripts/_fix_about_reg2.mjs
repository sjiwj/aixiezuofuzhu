
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const ab = L.findIndex((x) => x.includes('safe("settings.general.item #about"'))
if (ab < 0) throw new Error('about')
// 找 about 块结束（'			});' 3 tabs）
let ae = -1
for (let k = ab; k < ab + 14; k++) { if (L[k] === T(3) + '});') { ae = k; break } }
if (ae < 0) throw new Error('about end')
console.log('about at', ab + 1, 'end at', ae + 1)
// 若 end 后紧跟又一个同样的 '});'，删掉多余那个
if ((L[ae + 1] || '') === T(3) + '});') {
  L.splice(ae + 1, 1)
  console.log('removed duplicate close')
}
// 若 about 前一行不是 '});'（缺 stream 的 safe 闭合），补上
const prev = L[ab - 1]
const prev2 = L[ab - 2]
if ((prev2 || '').trim() === '});' && (prev || '').trim() === '') {
  L.splice(ab, 0, T(3) + '});')
  console.log('inserted missing safe close before about')
}
// 去掉 register 对象末尾多余逗号
const ci = L.findIndex((x, idx) => idx > ab && idx < ab + 10 && x.trim() === 'order: 52,')
if (ci > 0) L[ci] = T(6) + 'order: 52'
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('done')
