
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('const exportText')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) exportText：插在 persist 定义之后
const pi = find('const persist = useCallback(function (value, retried) {')
if (pi < 0) throw new Error('persist')
let pe = -1
for (let k = pi; k < pi + 40; k++) { if ((L[k] || '').trim().startsWith('}, [')) { pe = k; break } }
if (pe < 0) throw new Error('persist end')
const fn = [
  '',
  T(3) + '/* 导出当前章为 txt：末尾附 AI 生成标识（对外发布前请自行核验） */',
  T(3) + 'const exportText = useCallback(function () {',
  T(4) + 'const p0 = pathRef.current;',
  T(4) + 'const info0 = p0 ? parseChapterPath(p0) : null;',
  T(4) + 'const body = String(textRef.current || "");',
  T(4) + 'if (!info0 || !body.trim()) { setNote("这一章还没有内容，先写或让 AI 写"); return; }',
  T(4) + 'const d = new Date();',
  T(4) + 'const pad = function (n) { return String(n).padStart(2, "0"); };',
  T(4) + 'const when = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());',
  T(4) + 'const tail = "\n\n----\n本文件由「小说创作工作台」v" + APP_VERSION + " 导出。\n正文可能包含 AI 辅助生成内容，发布前请自行核验。\n导出时间：" + when + "\n";',
  T(4) + 'const name = (info0.book || "未命名") + "-" + String(info0.file || "章节").replace(/\.md$/i, "") + ".txt";',
  T(4) + 'try {',
  T(5) + 'const blob = new Blob([body + tail], { type: "text/plain;charset=utf-8" });',
  T(5) + 'const url = URL.createObjectURL(blob);',
  T(5) + 'const a = document.createElement("a");',
  T(5) + 'a.href = url;',
  T(5) + 'a.download = name;',
  T(5) + 'document.body.appendChild(a);',
  T(5) + 'a.click();',
  T(5) + 'setTimeout(function () { URL.revokeObjectURL(url); try { a.remove(); } catch (e) { /* ignore */ } }, 1200);',
  T(5) + 'setNote("已导出 " + name + "（末尾带 AI 生成标识）");',
  T(4) + '} catch (e) {',
  T(5) + 'setNote("导出失败：" + String((e && e.message) || e));',
  T(4) + '}',
  T(3) + '}, []);',
]
L.splice(pe + 1, 0, ...fn)
console.log('1) exportText ok')

// 2) 工具栏按钮
const bi = find('onClick: function () { load(path); } }, "重新加载"),')
if (bi < 0) throw new Error('reload button')
L.splice(bi, 0,
  T(5) + 'h("button", { className: "nvl-btn", onClick: exportText, title: "导出当前章为 txt（末尾附 AI 生成标识）" }, "导出 txt"),'
)
console.log('2) button ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE export')
