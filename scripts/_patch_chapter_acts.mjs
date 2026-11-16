
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('renameChapter')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) 文件名清洗 helper（放 chapterKey 之前）
const ck = find('function chapterKey(ch) {')
if (ck < 0) throw new Error('chapterKey')
const helper = [
  T(2) + '/* 文件名清洗：把 Windows 不允许的字符去掉（用 charCode 免得转义踩坑） */',
  T(2) + 'function safeFileName(name) {',
  T(3) + 'const bad = ["/", String.fromCharCode(92), ":", "*", "?", String.fromCharCode(34), "<", ">", "|"];',
  T(3) + 'return String(name || "").split("").filter(function (c) { return bad.indexOf(c) < 0; }).join("").trim();',
  T(2) + '}',
  '',
]
L.splice(ck, 0, ...helper)
console.log('1) safeFileName ok')

// 2) addChapter / renameChapter（放在 removeBook 之后）
const rb = find('const removeBook = useCallback(async function (bookName) {')
if (rb < 0) throw new Error('removeBook')
let rbe = -1
for (let k = rb; k < rb + 30; k++) { if ((L[k] || '').trim() === '}, [refresh]);') { rbe = k; break } }
if (rbe < 0) throw new Error('removeBook end')
const acts = [
  '',
  T(3) + '/* 在手边新建一章：编号自动排，建完直接打开 */',
  T(3) + 'const addChapter = useCallback(async function (bookName) {',
  T(4) + 'const title = await nvlPrompt("新建章节", "这一章叫什么？（编号自动排）", "");',
  T(4) + 'if (!title) return;',
  T(4) + 'const res = await fetchChapters({ name: bookName });',
  T(4) + 'const list = res.chapters || [];',
  T(4) + 'let maxNo = 0;',
  T(4) + 'for (let i = 0; i < list.length; i++) {',
  T(5) + 'const n = parseInt(chapterKey(list[i]), 10);',
  T(5) + 'if (!isNaN(n) && n > maxNo) maxNo = n;',
  T(4) + '}',
  T(4) + 'const nextNo = String(maxNo + 1).padStart(3, "0");',
  T(4) + 'const safe = safeFileName(title);',
  T(4) + 'if (!safe) { setError("标题里没有可用字符"); return; }',
  T(4) + 'const target = "projects/" + bookName + "/章节/" + nextNo + "-" + safe + ".md";',
  T(4) + 'const r = await saveChapter(target, "# " + safe + "\n\n", true);',
  T(4) + 'if (!r.ok || (r.data && r.data.ok === false)) { setError("新建章节失败：" + apiError(r, "新建章节")); return; }',
  T(4) + 'setError("");',
  T(4) + 'openChapter(target);',
  T(4) + 'refresh(bookName);',
  T(3) + '}, [refresh, openChapter]);',
  '',
  T(3) + '/* 重命名章节：只改文件名，正文不动；章号变了状态跟着搬 */',
  T(3) + 'const renameChapter = useCallback(async function (bookName, ch) {',
  T(4) + 'const oldFile = String(ch.file || "").replace(/\.md$/i, "") || String(ch.path || "").split("/").pop().replace(/\.md$/i, "");',
  T(4) + 'const to = await nvlPrompt("重命名这一章", "新文件名（不用写 .md）", oldFile);',
  T(4) + 'if (!to || to === oldFile) return;',
  T(4) + 'const r = await api("/api/file/rename", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: ch.path, to: to }) });',
  T(4) + 'if (!r.ok || (r.data && r.data.ok === false)) { setError((r.data && r.data.error) === "exists" ? "已有同名章节，换个名字" : ("重命名失败：" + ((r.data && r.data.error) || "未知错误"))); return; }',
  T(4) + 'setError("");',
  T(4) + 'const np = (r.data && r.data.path) || "";',
  T(4) + 'if (np && active === ch.path) openChapter(np);',
  T(4) + 'refresh(bookName);',
  T(3) + '}, [refresh, openChapter, active]);',
]
L.splice(rbe + 1, 0, ...acts)
console.log('2) addChapter / renameChapter ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE chapter actions')
