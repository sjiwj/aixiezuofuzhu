
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('exportMenu')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) exportText 里加 copy 分支：把 a.click() 前的逻辑按模式分流
const ei = find('const exportText = useCallback(function () {')
if (ei < 0) throw new Error('exportText')
// 找到 a.click(); 行与 setNote 行，替换为模式分流
const clickIdx = find('a.click();', ei)
if (clickIdx < 0) throw new Error('a.click')
// 插入 mode 判断（在 try { 之前）
const tryIdx = find('try {', ei)
L.splice(tryIdx, 0,
  T(4) + 'const mode = String((arguments[0] && arguments[0].mode) || "file");'
)
// a.click() 之后的条件化：把 setNote 改成按 mode
const noteIdx = find('setNote("已导出 " + name + "（末尾带 AI 生成标识）");', ei)
if (noteIdx > 0) {
  L.splice(noteIdx, 1,
    T(5) + 'setNote(mode === "copy" ? "正文已复制（带 AI 标识），可直接粘贴" : ("已导出 " + name + "（末尾带 AI 生成标识）"));'
  )
}
// 在 a.click() 前加 copy 分支：如果 mode === copy，写剪贴板并 return
L.splice(clickIdx, 0,
  T(5) + 'if (mode === "copy") {',
  T(6) + 'navigator.clipboard.writeText(body + tail).then(function () { setNote("正文已复制（带 AI 标识），可直接粘贴"); }, function (err) { setNote("复制失败：" + String((err && err.message) || err)); });',
  T(6) + 'return;',
  T(5) + '}'
)
console.log('1) exportText mode ok')

// 2) 按钮改成「导出」+ 菜单
const bi = find('h("button", { className: "nvl-btn", onClick: exportText, title: "导出当前章为 txt（末尾附 AI 生成标识）" }, "导出 txt"),')
if (bi < 0) throw new Error('export button')
const menu = [
  T(5) + '/* 导出：保存成文件 or 直接复制（都带 AI 标识） */',
  T(5) + 'const exportMenu = useCallback(async function () {',
  T(6) + 'const pick = await nvlChoice("导出当前章", [',
  T(7) + '{ label: "保存为 txt 文件（带 AI 标识）", value: "file" },',
  T(7) + '{ label: "复制正文到剪贴板（带 AI 标识）", value: "copy" }',
  T(6) + ']);',
  T(6) + 'if (!pick) return;',
  T(6) + 'exportText({ mode: pick });',
  T(5) + '}, [exportText]);',
]
L.splice(bi, 1,
  ...menu,
  T(5) + 'h("button", { className: "nvl-btn", onClick: exportMenu, title: "导出当前章：存成 txt 或复制正文，都带 AI 生成标识" }, "导出"),'
)
console.log('2) menu button ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE export menu')
