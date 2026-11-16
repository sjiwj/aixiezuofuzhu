
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('function nvlConfirm')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// (a) nvlConfirm / nvlChoice：插在 nvlPrompt 之前
const i0 = find('function nvlPrompt(title, placeholder, defaultValue) {')
if (i0 < 0) throw new Error('nvlPrompt')
const modals = [
  T(2) + '/* 确认框：只要「确定 / 取消」，不打字 */',
  T(2) + 'function nvlConfirm(title, message) {',
  T(3) + 'return new Promise(function (resolve) {',
  T(4) + 'const wrap = makeEl("div", "nvl-modal");',
  T(4) + 'wrap.setAttribute("role", "dialog");',
  T(4) + 'wrap.setAttribute("aria-modal", "true");',
  T(4) + 'const panel = makeEl("div", "nvl-modal__panel");',
  T(4) + 'const head = makeEl("div", "nvl-modal__head");',
  T(4) + 'head.appendChild(makeEl("span", "nvl-modal__title", title || "确认"));',
  T(4) + 'const body = makeEl("div", "nvl-modal__body");',
  T(4) + 'const txt = makeEl("div", "nvl-modal__text", message || "");',
  T(4) + 'txt.style.whiteSpace = "pre-wrap";',
  T(4) + 'txt.style.lineHeight = "1.7";',
  T(4) + 'txt.style.fontSize = "13px";',
  T(4) + 'body.appendChild(txt);',
  T(4) + 'const foot = makeEl("div", "nvl-modal__foot");',
  T(4) + 'const cancel = makeEl("button", "nvl-btn", "取消");',
  T(4) + 'const ok = makeEl("button", "nvl-btn nvl-btn--primary", "确定");',
  T(4) + 'foot.appendChild(cancel);',
  T(4) + 'foot.appendChild(ok);',
  T(4) + 'panel.appendChild(head);',
  T(4) + 'panel.appendChild(body);',
  T(4) + 'panel.appendChild(foot);',
  T(4) + 'wrap.appendChild(panel);',
  T(4) + 'let done = false;',
  T(4) + 'const close = function (v) { if (done) return; done = true; try { removeEl(wrap); } catch (e) { /* ignore */ } resolve(v); };',
  T(4) + 'cancel.addEventListener("click", function () { close(false); });',
  T(4) + 'ok.addEventListener("click", function () { close(true); });',
  T(4) + 'document.body.appendChild(wrap);',
  T(4) + 'try { ok.focus(); } catch (e) { /* ignore */ }',
  T(3) + '});',
  T(2) + '}',
  '',
  T(2) + '/* 选项框：直接列出现有分支，点一下就选 */',
  T(2) + 'function nvlChoice(title, options) {',
  T(3) + 'return new Promise(function (resolve) {',
  T(4) + 'const wrap = makeEl("div", "nvl-modal");',
  T(4) + 'wrap.setAttribute("role", "dialog");',
  T(4) + 'wrap.setAttribute("aria-modal", "true");',
  T(4) + 'const panel = makeEl("div", "nvl-modal__panel");',
  T(4) + 'const head = makeEl("div", "nvl-modal__head");',
  T(4) + 'head.appendChild(makeEl("span", "nvl-modal__title", title || "选择"));',
  T(4) + 'const body = makeEl("div", "nvl-modal__body");',
  T(4) + 'body.style.maxHeight = "50vh";',
  T(4) + 'body.style.overflow = "auto";',
  T(4) + 'const foot = makeEl("div", "nvl-modal__foot");',
  T(4) + 'const cancel = makeEl("button", "nvl-btn", "取消");',
  T(4) + 'let done = false;',
  T(4) + 'const close = function (v) { if (done) return; done = true; try { removeEl(wrap); } catch (e) { /* ignore */ } resolve(v); };',
  T(4) + '(options || []).forEach(function (o) {',
  T(5) + 'const b = makeEl("button", "nvl-btn", String(o.label));',
  T(5) + 'b.style.display = "block";',
  T(5) + 'b.style.width = "100%";',
  T(5) + 'b.style.marginBottom = "6px";',
  T(5) + 'b.style.textAlign = "left";',
  T(5) + 'b.addEventListener("click", function () { close(o.value); });',
  T(5) + 'body.appendChild(b);',
  T(4) + '});',
  T(4) + 'foot.appendChild(cancel);',
  T(4) + 'cancel.addEventListener("click", function () { close(null); });',
  T(4) + 'panel.appendChild(head);',
  T(4) + 'panel.appendChild(body);',
  T(4) + 'panel.appendChild(foot);',
  T(4) + 'wrap.appendChild(panel);',
  T(4) + 'document.body.appendChild(wrap);',
  T(3) + '});',
  T(2) + '}',
  '',
]
L.splice(i0, 0, ...modals)
console.log('(a) modals ok before', i0 + 1)

// (b) 删除章节
let i = find('const yes = await nvlPrompt("删除这一章"')
if (i < 0) throw new Error('chapter prompt')
L.splice(i, 3,
  T(4) + 'const yes = await nvlConfirm("删除这一章", "确认删除「" + name + "」？\n\n文件会进回收站（data/.trash），之后可以捞回来。");',
  T(4) + 'if (!yes) return;'
)
console.log('(b) ok')

// (c) 删除整本书
i = find('const yes = await nvlPrompt("删除整本书"')
if (i < 0) throw new Error('book prompt')
L.splice(i, 3,
  T(4) + 'const yes = await nvlConfirm("删除整本书", "确认删除《" + bookName + "》？\n\n这本书的全部章节和设定都会进回收站（data/.trash），可以捞回来。");',
  T(4) + 'if (!yes) return;'
)
console.log('(c) ok')

// (d) 删除分支
i = find('const yes = await nvlPrompt("删除分支"')
if (i < 0) throw new Error('branch prompt')
L.splice(i, 3,
  T(4) + 'const yes = await nvlConfirm("删除分支", "确认删除分支「" + branch + "」？\n\n里面的设定文件会进回收站（data/.trash），可以捞回来。");',
  T(4) + 'if (!yes) return;'
)
console.log('(d) ok')

// (e) 移动：改成选项
i = find('const to = await nvlPrompt("移动到分支"')
if (i < 0) throw new Error('move prompt')
L.splice(i, 2,
  T(4) + 'const picks = groups.filter(function (g) { return g.kind === "docs"; }).map(function (g) { return { label: g.label === "未分组" ? "未分组（根目录）" : g.label, value: g.branch || "" }; });',
  T(4) + 'if (!picks.length) { setError("还没有别的分支，先点「+ 分支」建一个"); return; }',
  T(4) + 'const to = await nvlChoice("移动到分支", picks);',
  T(4) + 'if (to === null) return;'
)
// moveDoc 依赖加 groups
i = find('}, [book, load]);', find('const moveDoc = useCallback'))
if (i > 0) L[i] = T(3) + '}, [book, load, groups]);'
console.log('(e) ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE a-e')
