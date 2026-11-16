
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('reviseWithNotes')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) state
const st = find('const [injected, setInjected] = useState(null);')
if (st < 0) throw new Error('injected state')
L.splice(st + 1, 0,
  T(3) + 'const [revising, setRevising] = useState(false);',
  T(3) + 'const [revised, setRevised] = useState(null);',
  T(3) + 'const [recheck, setRecheck] = useState(null);'
)
console.log('1) state ok')

// 2) 两个动作：按意见改（dry_run 预览） / 采用并复检
const startFn = find('const start = useCallback(async function () {')
if (startFn < 0) throw new Error('start fn')
let startEnd = -1
for (let k = startFn; k < startFn + 90; k++) { if ((L[k] || '').trim().startsWith('}, [')) { startEnd = k; break } }
if (startEnd < 0) throw new Error('start end')
const fns = [
  '',
  T(3) + '/* Step 6 改稿：把审稿意见交给写手重写，先预览不落盘 */',
  T(3) + 'const reviseWithNotes = useCallback(async function () {',
  T(4) + 'const info = path ? parseChapterPath(path) : null;',
  T(4) + 'if (!info) { setError("先选一章"); return; }',
  T(4) + 'const notes = [];',
  T(4) + 'reviewers.forEach(function (r) {',
  T(5) + 'if (r.status === "done" && r.text) notes.push((r.name || r.id || "审稿人") + "：" + String(r.text).slice(0, 1200));',
  T(4) + '});',
  T(4) + 'if (!notes.length) { setError("还没有可用的审稿意见"); return; }',
  T(4) + 'setRevising(true);',
  T(4) + 'setError("");',
  T(4) + 'setRevised(null);',
  T(4) + 'setRecheck(null);',
  T(4) + 'try {',
  T(5) + 'const url = apiBase().replace(/\\/+$/, "") + "/api/write";',
  T(5) + 'let out = "";',
  T(5) + 'const r2 = await streamSSE(url, {',
  T(6) + 'path: path, book: info.book, chapter: info.file,',
  T(6) + 'mode: "replace", force: true, dry_run: true, stream: true, notes: notes',
  T(5) + '}, function (ev) {',
  T(6) + 'const t = String(ev.type || "");',
  T(6) + 'if (t === "delta") out += String(ev.text || "");',
  T(6) + 'if (t === "error") setError(String(ev.text || "改稿失败"));',
  T(5) + '}, null);',
  T(5) + 'if (!r2.ok) { setError(r2.error || "改稿失败"); setRevising(false); return; }',
  T(5) + 'if (!out.trim()) { setError("模型没有输出内容"); setRevising(false); return; }',
  T(5) + 'setRevised({ text: out });',
  T(4) + '} catch (e) {',
  T(5) + 'setError("改稿出错：" + String((e && e.message) || e));',
  T(4) + '}',
  T(4) + 'setRevising(false);',
  T(3) + '}, [path, reviewers]);',
  '',
  T(3) + '/* Step 7 复检：采用改稿 → 落盘 → 立刻重跑质检 */',
  T(3) + 'const adoptRevised = useCallback(async function () {',
  T(4) + 'if (!revised || !path) return;',
  T(4) + 'const r = await api("/api/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: path, content: revised.text, force: true }) });',
  T(4) + 'if (!r.ok || (r.data && r.data.ok === false)) { setError("落盘失败：" + ((r.data && r.data.error) || r.error || "未知")); return; }',
  T(4) + 'setRevised(null);',
  T(4) + 'const q = await api("/api/qc?path=" + encodeURIComponent(path));',
  T(4) + 'const d = (q && q.data) || {};',
  T(4) + 'setRecheck({ verdict: d.verdict || "-", issues: Array.isArray(d.issues) ? d.issues : [] });',
  T(4) + 'setError("");',
  T(4) + 'if (typeof refreshGate === "function") try { refreshGate(); } catch (e2) { /* ignore */ }',
  T(3) + '}, [revised, path]);',
]
L.splice(startEnd + 1, 0, ...fns)
console.log('2) revise/adopt 函数 ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE functions')
