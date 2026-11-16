
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) 取出渲染区的 exportMenu 块（从注释行到 '}, [exportText]);'）
const a = find('/* 导出：保存成文件 or 直接复制（都带 AI 标识） */')
if (a < 0) throw new Error('menu block')
let b = -1
for (let k = a; k < a + 14; k++) { if ((L[k] || '').includes('}, [exportText]);')) { b = k; break } }
if (b < 0) throw new Error('menu end')
const block = L.slice(a, b + 1)
// 去掉空行（块尾）
L.splice(a, b - a + 1 + (L[b + 1] && L[b + 1].trim() === '' ? 1 : 0))
console.log('removed render-area block at', a + 1)

// 2) 插到 exportText 的 '}, []);' 之后（组件内）
const ei = find('const exportText = useCallback(function () {')
if (ei < 0) throw new Error('exportText')
let ee = -1
for (let k = ei; k < ei + 40; k++) { if ((L[k] || '').trim() === '}, []);') { ee = k; break } }
if (ee < 0) throw new Error('exportText end')
L.splice(ee + 1, 0, '', ...block)
console.log('inserted after exportText at', ee + 1)

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('done')
