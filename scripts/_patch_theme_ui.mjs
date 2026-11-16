
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('ThemeSettingRow')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) 应用主题的模块级函数（放在 UsageSettingRow 之前）
const anchor = find('function UsageSettingRow() {')
if (anchor < 0) throw new Error('usage row anchor')
const fn = [
  T(2) + '/* 外观：跟随系统 / 浅色 / 深色（正文配色定义在 040-theme.js）*/',
  T(2) + 'const LS_THEME = "novelapp.theme";',
  T(2) + 'function applyTheme(mode) {',
  T(3) + 'try {',
  T(4) + 'const root = document.documentElement;',
  T(4) + 'if (mode === "light" || mode === "dark") root.dataset.nvlTheme = mode;',
  T(4) + 'else delete root.dataset.nvlTheme;',
  T(3) + '} catch (e) { /* ignore */ }',
  T(2) + '}',
  '',
  T(2) + 'function ThemeSettingRow() {',
  T(3) + 'const [mode, setMode] = useState(function () { try { return localStorage.getItem(LS_THEME) || ""; } catch (e) { return ""; } });',
  T(3) + 'const pick = function (m) {',
  T(4) + 'setMode(m);',
  T(4) + 'try { if (m) localStorage.setItem(LS_THEME, m); else localStorage.removeItem(LS_THEME); } catch (e) { /* ignore */ }',
  T(4) + 'applyTheme(m);',
  T(3) + '};',
  T(3) + 'const items = [{ id: "", label: "跟随系统" }, { id: "light", label: "浅色" }, { id: "dark", label: "深色" }];',
  T(3) + 'return h("div", { className: "nvl-setrow" },',
  T(4) + 'h("div", { className: "nvl-setrow__text" },',
  T(5) + 'h("div", { className: "nvl-setrow__title" }, "外观"),',
  T(5) + 'h("div", { className: "nvl-setrow__desc" }, "浅色贴近纸张；与应用主体不一致时会有色差，建议跟随系统")',
  T(4) + '),',
  T(4) + 'h("div", { style: { display: "flex", gap: "6px" } },',
  T(5) + 'items.map(function (it) {',
  T(6) + 'return h("button", {',
  T(7) + 'key: it.id || "auto",',
  T(7) + 'className: "nvl-btn" + (mode === it.id ? " nvl-btn--primary" : ""),',
  T(7) + 'onClick: function () { pick(it.id); }',
  T(6) + '}, it.label);',
  T(5) + '})',
  T(4) + ')',
  T(3) + ');',
  T(2) + '}',
  '',
]
L.splice(anchor, 0, ...fn)
console.log('1) ThemeSettingRow ok')

// 2) 注册到设置页
const ab = find('safe("settings.general.item #usage", function () {')
if (ab < 0) throw new Error('usage register')
let ae = -1
for (let k = ab; k < ab + 14; k++) { if (L[k] === T(3) + '});') { ae = k; break } }
if (ae < 0) throw new Error('register end')
const reg = [
  '',
  T(3) + 'safe("settings.general.item #theme", function () {',
  T(4) + 'return ctx.slots.inject("settings.general.item", function () {',
  T(5) + 'return ctx.slots.register({',
  T(6) + 'name: "settings.general.item",',
  T(6) + 'id: "novel-theme-setting",',
  T(6) + 'order: 51',
  T(5) + '}, ThemeSettingRow);',
  T(4) + '});',
  T(3) + '});',
]
L.splice(ae + 1, 0, ...reg)
console.log('2) 注册 ok')

// 3) 挂载时应用一次
const mount = find('void nvlToken();')
if (mount > 0) {
  L.splice(mount + 1, 0, T(2) + 'try { applyTheme(localStorage.getItem(LS_THEME) || ""); } catch (e0) { /* ignore */ }')
  console.log('3) 启动应用 ok')
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE theme setting')
