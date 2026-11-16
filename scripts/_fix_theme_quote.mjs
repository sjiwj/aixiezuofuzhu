
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/040-theme.js'
let s = fs.readFileSync(p, 'utf8')
const bs = String.fromCharCode(92)
const q = bs + '"'
// 把浅色块里被吃掉的转义补回来
const bad1 = '  "--nvl-font-ui: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;",'
const good1 = '  "--nvl-font-ui: -apple-system, ' + q + 'Segoe UI' + q + ', ' + q + 'Microsoft YaHei' + q + ', sans-serif;",'
const bad2 = '  "--nvl-font-data: Consolas, "Cascadia Mono", "Courier New", monospace;",'
const good2 = '  "--nvl-font-data: Consolas, ' + q + 'Cascadia Mono' + q + ', ' + q + 'Courier New' + q + ', monospace;",'
let n = 0
if (s.includes(bad1)) { s = s.split(bad1).join(good1); n++ }
if (s.includes(bad2)) { s = s.split(bad2).join(good2); n++ }
// 选择器里的引号也要修
s = s.split('html[data-nvl-theme="dark"]').join('html[data-nvl-theme=' + q + 'dark' + q + ']')
s = s.split('html[data-nvl-theme="light"]').join('html[data-nvl-theme=' + q + 'light' + q + ']')
s = s.split('html:not([data-nvl-theme="dark"])').join('html:not([data-nvl-theme=' + q + 'dark' + q + '])')
fs.writeFileSync(p, s, 'utf8')
console.log('fixed font quotes:', n)
