
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('addChapter(book.name)')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

const mini = 'style: { height: "18px", padding: "0 5px", fontSize: "11px", marginLeft: "4px" }'

// 1) 书行：+ 新建一章（插在删除按钮之前）
const bd = find('onClick: function (e) { e.stopPropagation(); removeBook(book.name); }')
if (bd < 0) throw new Error('removeBook button')
// 找到该按钮的 h("button", { 起始行（向上找）
let bs = bd
for (let k = bd; k > bd - 6; k--) { if ((L[k] || '').includes('h("button", {')) { bs = k; break } }
L.splice(bs, 0,
  T(5) + 'h("button", {',
  T(6) + 'className: "nvl-btn",',
  T(6) + mini + ',',
  T(6) + 'title: "在这本书里新建一章",',
  T(6) + 'onClick: function (e) { e.stopPropagation(); addChapter(book.name); }',
  T(5) + '}, "+"),'
)
console.log('1) book add-chapter button ok')

// 2) 章节行：✎ 重命名（插在删除按钮之前）
const cr = find('onClick: function (e) { e.stopPropagation(); removeChapter(book.name, ch); }')
if (cr < 0) throw new Error('removeChapter button')
let cs = cr
for (let k = cr; k > cr - 6; k--) { if ((L[k] || '').includes('h("button", {')) { cs = k; break } }
L.splice(cs, 0,
  T(6) + 'h("button", {',
  T(7) + 'className: "nvl-btn",',
  T(7) + 'style: { height: "18px", padding: "0 5px", fontSize: "11px" },',
  T(7) + 'title: "重命名这一章的标题",',
  T(7) + 'onClick: function (e) { e.stopPropagation(); renameChapter(book.name, ch); }',
  T(6) + '}, "\u270E"),'
)
console.log('2) chapter rename button ok')

// 3) 404 兜底（码字面板 load）
const lnf = find('if (res.content === null) { setNote(res.error); return; }')
if (lnf >= 0) {
  L.splice(lnf, 1,
    T(4) + 'if (res.content === null) {',
    T(5) + 'setNote("这一章的文件不在了（可能被删或改名）：" + res.error);',
    T(5) + 'pathRef.current = ""; setPath(""); setText(""); setSavedText(""); textRef.current = "";',
    T(5) + 'try { store.set(null); } catch (e0) { /* ignore */ }',
    T(5) + 'return;',
    T(4) + '}'
  )
  console.log('3) 404 fallback ok')
} else { console.log('3) no 404 anchor') }

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE ui buttons')
