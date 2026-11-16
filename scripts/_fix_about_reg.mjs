
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

const ab = find('safe("settings.general.item #about", function () {')
if (ab < 0) throw new Error('about register')
// 1) 改 key -> id + order
const ki = find('key: "@novelapp/about"', ab)
if (ki > 0) L[ki] = T(6) + 'id: "novel-about-setting",'
const ki2 = find('key: "@novelapp/about"', ab)
if (ki2 > 0) L[ki2] = T(6) + 'key: "@novelapp/about",'
// 在 id 行后补 order
if (ki > 0 && !L[ki + 1].includes('order:')) L.splice(ki + 1, 0, T(6) + 'order: 52,')
console.log('id/order ok')

// 2) 修嵌套：about 块应在其后的 '});' 之后，且 stream 块要补一个 '});'
// 找 about 块结束（第一个 trim === '});'）
let ae = -1
for (let k = ab; k < ab + 14; k++) { if ((L[k] || '').trim() === '});') { ae = k; break } }
if (ae < 0) throw new Error('about end')
// 现在 ab-1 应为 '});'（stream 的 inject 闭合），检查
const before = (L[ab - 1] || '').trim()
console.log('before about:', JSON.stringify(L[ab - 1]), JSON.stringify(L[ab]))
if (before === '});') {
  // 缺 safe 的闭合：在 ab 前插一个
  L.splice(ab, 0, T(3) + '});')
  console.log('inserted safe close')
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('done')
