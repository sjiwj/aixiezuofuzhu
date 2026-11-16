
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('hostTheme')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const i = L.findIndex((x) => x.trim() === 'function applyTheme(mode) {')
if (i < 0) throw new Error('applyTheme line')

// 在 applyTheme 之前插入 hostTheme + watchHostTheme
const pre = [
  T(2) + '/* 宿主 DSH 用 html[data-ds-theme-source] 表示外观（light/dark/system），',
  T(2) + '   比猜 prefers-color-scheme 准 —— 用户可以在 DSH 设置里手动切 */',
  T(2) + 'function hostTheme() {',
  T(3) + 'try {',
  T(4) + 'const t = String(document.documentElement.dataset.dsThemeSource || "");',
  T(4) + 'if (t === "light" || t === "dark") return t;',
  T(3) + '} catch (e) { /* ignore */ }',
  T(3) + 'try { return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"; }',
  T(3) + 'catch (e2) { return "dark"; }',
  T(2) + '}',
  '',
]
L.splice(i, 0, ...pre)
const j = L.findIndex((x) => x.trim() === 'function applyTheme(mode) {')
// 改 applyTheme 的 else 分支
for (let k = j; k < j + 10; k++) {
  if ((L[k] || '').includes('else delete root.dataset.nvlTheme;')) {
    L[k] = T(4) + 'else root.dataset.nvlTheme = hostTheme();'
    break
  }
}
// 在 ThemeSettingRow 之后加 watchHostTheme + 启动应用
const w = [
  '',
  T(2) + '/* 宿主切外观时跟着变，不用重启 */',
  T(2) + 'function initTheme() {',
  T(3) + 'const getMode = function () { try { return localStorage.getItem(LS_THEME) || ""; } catch (e) { return ""; } };',
  T(3) + 'applyTheme(getMode());',
  T(3) + 'try {',
  T(4) + 'const ob = new MutationObserver(function () { applyTheme(getMode()); });',
  T(4) + 'ob.observe(document.documentElement, { attributes: true, attributeFilter: ["data-ds-theme-source"] });',
  T(3) + '} catch (e2) { /* ignore */ }',
  T(2) + '}',
  T(2) + 'initTheme();',
]
L.splice(j, 0, ...w)
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('theme: hostTheme + initTheme 已插入')
