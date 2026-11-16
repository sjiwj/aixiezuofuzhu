
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('AboutSettingRow')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) APP_VERSION 常量 + nvlInfo（插在 nvlConfirm 之前）
const i0 = find('function nvlConfirm(title, message) {')
if (i0 < 0) throw new Error('nvlConfirm')
const head = [
  T(2) + '/* 版本号：构建时由 build.ps1 按 $VERSION 自动改写，别手改 */',
  T(2) + 'const APP_VERSION = "0.8.3";',
  '',
  T(2) + '/* 信息弹层：只读长文，只有一个「关闭」 */',
  T(2) + 'function nvlInfo(title, text) {',
  T(3) + 'return new Promise(function (resolve) {',
  T(4) + 'const wrap = makeEl("div", "nvl-modal");',
  T(4) + 'wrap.setAttribute("role", "dialog");',
  T(4) + 'wrap.setAttribute("aria-modal", "true");',
  T(4) + 'const panel = makeEl("div", "nvl-modal__panel");',
  T(4) + 'const headEl = makeEl("div", "nvl-modal__head");',
  T(4) + 'headEl.appendChild(makeEl("span", "nvl-modal__title", title || "关于"));',
  T(4) + 'const body = makeEl("div", "nvl-modal__body");',
  T(4) + 'const pre = makeEl("div", null, String(text || ""));',
  T(4) + 'pre.style.whiteSpace = "pre-wrap";',
  T(4) + 'pre.style.lineHeight = "1.75";',
  T(4) + 'pre.style.fontSize = "13px";',
  T(4) + 'pre.style.maxHeight = "52vh";',
  T(4) + 'pre.style.overflow = "auto";',
  T(4) + 'body.appendChild(pre);',
  T(4) + 'const foot = makeEl("div", "nvl-modal__foot");',
  T(4) + 'const ok = makeEl("button", "nvl-btn nvl-btn--primary", "关闭");',
  T(4) + 'foot.appendChild(ok);',
  T(4) + 'panel.appendChild(headEl);',
  T(4) + 'panel.appendChild(body);',
  T(4) + 'panel.appendChild(foot);',
  T(4) + 'wrap.appendChild(panel);',
  T(4) + 'let done = false;',
  T(4) + 'const close = function () { if (done) return; done = true; try { removeEl(wrap); } catch (e) { /* ignore */ } resolve(true); };',
  T(4) + 'ok.addEventListener("click", close);',
  T(4) + 'document.body.appendChild(wrap);',
  T(3) + '});',
  T(2) + '}',
  '',
]
L.splice(i0, 0, ...head)
console.log('1) APP_VERSION + nvlInfo ok')

// 2) AboutSettingRow（插在 StreamSettingRow 之后）
const si = find('function StreamSettingRow() {')
if (si < 0) throw new Error('StreamSettingRow')
let se = -1
for (let k = si; k < si + 60; k++) { if ((L[k] || '').trim() === '}' && (L[k + 1] || '').trim() === '') { se = k; break } }
if (se < 0) throw new Error('StreamSettingRow end')
const about = [
  '',
  T(2) + '/* 设置 → 通用 → 关于与许可：MIT 声明 + 版本 + AI 标识说明 */',
  T(2) + 'function AboutSettingRow() {',
  T(3) + 'const open = function () {',
  T(4) + 'nvlInfo("关于与许可", [',
  T(5) + '"小说创作工作台  v" + APP_VERSION,',
  T(5) + '""',
  T(5) + '"基于 DeepSeek Harness（MIT License）二次开发。",',
  T(5) + '"Copyright (c) 2026 DeepSeek —— 该组件的许可证全文与版权声明随安装包提供（LICENSE 文件），本软件按 MIT 许可证使用并保留该声明。",',
  T(5) + '""',
  T(5) + '"本软件与 DeepSeek 无隶属、无授权、无合作关系；模型调用经由本项目自建网关，按实际用量计费。DeepSeek、DSH 等名称为其各自权利人所有。",',
  T(5) + '""',
  T(5) + '"其他第三方组件：Electron、React 等，许可证见安装目录内相关声明文件。",',
  T(5) + '""',
  T(5) + '"AI 生成内容提示：本软件为写作辅助工具，正文可能包含模型生成的内容。导出文件时会在末尾附加生成标识；对外发布前请自行核验事实、人物与版权。"',
  T(4) + '].join("\n"));',
  T(3) + '};',
  T(3) + 'return h("div", { className: "nvl-setrow" },',
  T(4) + 'h("div", { className: "nvl-setrow__text" },',
  T(5) + 'h("div", { className: "nvl-setrow__title" }, "关于与许可"),',
  T(5) + 'h("div", { className: "nvl-setrow__desc" }, "v" + APP_VERSION + " · 基于 DeepSeek Harness（MIT）构建 · 第三方许可与 AI 生成说明")',
  T(4) + '),',
  T(4) + 'h("button", { className: "nvl-btn", onClick: open }, "查看")',
  T(3) + ');',
  T(2) + '}',
]
L.splice(se + 1, 0, ...about)
console.log('2) AboutSettingRow ok')

// 3) 注册设置项（在 #stream 注册块之后）
const reg = find('safe("settings.general.item #stream", function () {')
if (reg < 0) throw new Error('stream register')
let regEnd = -1
for (let k = reg; k < reg + 20; k++) { if ((L[k] || '').trim() === '});') { regEnd = k; break } }
if (regEnd < 0) throw new Error('stream register end')
const reg2 = [
  '',
  T(3) + 'safe("settings.general.item #about", function () {',
  T(4) + 'return ctx.slots.inject("settings.general.item", function () {',
  T(5) + 'return ctx.slots.register({',
  T(6) + 'name: "settings.general.item",',
  T(6) + 'key: "@novelapp/about"',
  T(5) + '}, AboutSettingRow);',
  T(4) + '});',
  T(3) + '});',
]
L.splice(regEnd + 1, 0, ...reg2)
console.log('3) register ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE about')
