
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('dsThemeSource')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

// 1) applyTheme 改成：手动设置优先，否则跟随宿主 dsThemeSource，最后跟系统
const old = [
  '\t\tfunction applyTheme(mode) {',
  '\t\t\ttry {',
  '\t\t\t\tconst root = document.documentElement;',
  '\t\t\t\tif (mode === "light" || mode === "dark") root.dataset.nvlTheme = mode;',
  '\t\t\t\telse delete root.dataset.nvlTheme;',
  '\t\t\t} catch (e) { /* ignore */ }',
  '\t\t}',
].join(eol)
if (!s.includes(old)) throw new Error('applyTheme block')
const neu = [
  '\t\t/* 宿主 DSH 用 html[data-ds-theme-source] 表示外观（light/dark/system），',
  '\t\t   比自己猜 prefers-color-scheme 准 —— 用户可以在 DSH 设置里手动切。 */',
  '\t\tfunction hostTheme() {',
  '\t\t\ttry {',
  '\t\t\t\tconst t = String(document.documentElement.dataset.dsThemeSource || "");',
  '\t\t\t\tif (t === "light" || t === "dark") return t;',
  '\t\t\t} catch (e) { /* ignore */ }',
  '\t\t\ttry { return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"; }',
  '\t\t\tcatch (e2) { return "dark"; }',
  '\t\t}',
  '',
  '\t\tfunction applyTheme(mode) {',
  '\t\t\ttry {',
  '\t\t\t\tconst root = document.documentElement;',
  '\t\t\t\tif (mode === "light" || mode === "dark") root.dataset.nvlTheme = mode;',
  '\t\t\t\telse root.dataset.nvlTheme = hostTheme();',
  '\t\t\t} catch (e) { /* ignore */ }',
  '\t\t}',
  '',
  '\t\t/* 宿主切换外观时跟着变（不用重启） */',
  '\t\tfunction watchHostTheme(getMode) {',
  '\t\t\ttry {',
  '\t\t\t\tconst ob = new MutationObserver(function () { applyTheme(getMode()); });',
  '\t\t\t\tob.observe(document.documentElement, { attributes: true, attributeFilter: ["data-ds-theme-source"] });',
  '\t\t\t} catch (e) { /* ignore */ }',
  '\t\t}',
].join(eol)
s = s.split(old).join(neu)

// 2) 启动时应用 + 监听
const mOld = '\t\ttry { applyTheme(localStorage.getItem(LS_THEME) || ""); } catch (e0) { /* ignore */ }'
if (!s.includes(mOld)) throw new Error('mount line')
const mNew = [
  '\t\ttry {',
  '\t\t\tconst _getMode = function () { try { return localStorage.getItem(LS_THEME) || ""; } catch (e) { return ""; } };',
  '\t\t\tapplyTheme(_getMode());',
  '\t\t\twatchHostTheme(_getMode);',
  '\t\t} catch (e0) { /* ignore */ }',
].join(eol)
s = s.split(mOld).join(mNew)
fs.writeFileSync(p, s, 'utf8')
console.log('theme: 跟随宿主 dsThemeSource')
