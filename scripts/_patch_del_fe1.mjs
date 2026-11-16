
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('removeChapter')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) 项目树：删章节 / 删书 两个动作（放在 openChapter 之后）
const oc = find('const openChapter = useCallback(function (path) {')
if (oc < 0) throw new Error('openChapter')
let ocEnd = find('}, []);', oc)
if (ocEnd < 0) throw new Error('openChapter end')
const actions = [
  '',
  T(3) + '/* 删除：一律二次确认；后端只移到 data/.trash，能捞回来 */',
  T(3) + 'const removeChapter = useCallback(async function (bookName, ch) {',
  T(4) + 'const name = ch.name || ch.file || ch.path;',
  T(4) + 'const yes = await nvlPrompt("删除这一章", "确认删除「" + name + "」？输入 删除 继续（文件会进回收站，可恢复）");',
  T(4) + 'if (!yes) return;',
  T(4) + 'if (String(yes).trim() !== "删除") { setError("没有删除：需要输入「删除」两个字确认"); return; }',
  T(4) + 'const r = await api("/api/file/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: ch.path }) });',
  T(4) + 'if (!r.ok || (r.data && r.data.ok === false)) { setError("删除失败：" + ((r.data && r.data.error) || r.error || "未知错误")); return; }',
  T(4) + 'setError("");',
  T(4) + 'refresh(bookName);',
  T(3) + '}, [refresh]);',
  '',
  T(3) + 'const removeBook = useCallback(async function (bookName) {',
  T(4) + 'const yes = await nvlPrompt("删除整本书", "确认删除《" + bookName + "》？这本书的全部章节和设定都会进回收站。输入书名确认");',
  T(4) + 'if (!yes) return;',
  T(4) + 'if (String(yes).trim() !== bookName) { setError("没有删除：书名输得不一样（需要完整输入「" + bookName + "」）"); return; }',
  T(4) + 'const r = await api("/api/project/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: bookName }) });',
  T(4) + 'if (!r.ok || (r.data && r.data.ok === false)) { setError("删除失败：" + ((r.data && r.data.error) || r.error || "未知错误")); return; }',
  T(4) + 'setError("");',
  T(4) + 'if (getCurrentBook() === bookName) { try { localStorage.removeItem("novelapp.currentBook"); } catch (e9) { /* ignore */ } }',
  T(4) + 'refresh();',
  T(3) + '}, [refresh]);',
]
L.splice(ocEnd + 1, 0, ...actions)
console.log('actions ok after', ocEnd + 1)

// 2) 书名行加删除按钮
let i = find('h("span", { className: "nvl-tree__count nvl-mono" },', find('const rows = [];'))
if (i < 0) throw new Error('book count span')
// 该 span 是 h(...) 调用，跨两行（第 i 行与 i+1）
const countBlockEnd = find('(book.count != null) ? (String(book.count) + " 章") : "")', i)
if (countBlockEnd < 0) throw new Error('book count end')
L.splice(countBlockEnd + 1, 0,
  T(5) + ',',
  T(5) + 'h("button", {',
  T(6) + 'className: "nvl-btn",',
  T(6) + 'style: { height: "18px", padding: "0 5px", fontSize: "11px", marginLeft: "4px" },',
  T(6) + 'title: "删除整本书（进回收站）",',
  T(6) + 'onClick: function (e) { e.stopPropagation(); removeBook(book.name); }',
  T(5) + '}, "\u2715")'
)
console.log('book delete button at', countBlockEnd + 1)

// 3) 章节行加删除按钮
i = find('h("span", { className: "nvl-dot", "data-stage": stage,', find('isOpen ? ((byBook[book.name]'))
if (i < 0) throw new Error('chapter dot')
L.splice(i, 0,
  T(6) + 'h("span", { style: { flex: "1" } }),',
  T(6) + 'h("button", {',
  T(7) + 'className: "nvl-btn",',
  T(7) + 'style: { height: "18px", padding: "0 5px", fontSize: "11px" },',
  T(7) + 'title: "删除这一章（进回收站）",',
  T(7) + 'onClick: function (e) { e.stopPropagation(); removeChapter(book.name, ch); }',
  T(6) + '}, "\u2715"),'
)
console.log('chapter delete button at', i + 1)

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE project-tree delete')
