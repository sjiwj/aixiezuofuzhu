
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('useNotes')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) state
const st = find('const [recheck, setRecheck] = useState(null);')
if (st < 0) throw new Error('recheck state')
L.splice(st + 1, 0,
  T(3) + 'const [useNotes, setUseNotes] = useState({});',
  T(3) + 'const [reviseBackup, setReviseBackup] = useState(null);',
  T(3) + 'const [lastBackup, setLastBackup] = useState(null);'
)
console.log('1) state ok')

// 2) 只取勾选的 + 读原文
const rv = find('const reviseWithNotes = useCallback(async function () {')
if (rv < 0) throw new Error('reviseWithNotes')
const cs = find('reviewers.forEach(function (r) {', rv)
let ce = -1
for (let k = cs; k < cs + 12; k++) { if ((L[k] || '').trim() === '});') { ce = k; break } }
if (cs < 0 || ce < 0) throw new Error('collect block')
L.splice(cs, ce - cs + 1,
  T(4) + 'reviewers.forEach(function (r) {',
  T(5) + 'const rid = r.id || r.name || "";',
  T(5) + 'if (useNotes[rid] === false) return;',
  T(5) + 'if (r.status === "done" && r.text) notes.push((r.name || rid || "审稿人") + "：" + String(r.text).slice(0, 1200));',
  T(4) + '});'
)
const ec = find('if (!notes.length) { setError("还没有可用的审稿意见"); return; }', rv)
if (ec < 0) throw new Error('empty check')
L.splice(ec + 1, 0,
  T(4) + 'let _orig = "";',
  T(4) + 'try { const _o = await readChapter(path); _orig = String(_o.content || ""); } catch (e0) { /* ignore */ }',
  T(4) + 'setReviseBackup(_orig || null);'
)
console.log('2) reviseWithNotes ok')

// 3) adoptRevised：落盘前写备份
const ad = find('const adoptRevised = useCallback(async function () {')
if (ad < 0) throw new Error('adopt')
const sl = find('const r = await api("/api/save"', ad)
if (sl < 0) throw new Error('save line')
L.splice(sl, 0,
  T(4) + 'if (reviseBackup) {',
  T(5) + 'const _stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 15);',
  T(5) + 'const _bp = path.replace(/\\.md$/i, "") + ".bak-revise-" + _stamp + ".md";',
  T(5) + 'try {',
  T(6) + 'await api("/api/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: _bp, content: reviseBackup, force: true }) });',
  T(6) + 'setLastBackup(_bp);',
  T(5) + '} catch (e0) { /* ignore */ }',
  T(4) + '}'
)
let adEnd = -1
for (let k = ad; k < ad + 30; k++) { const t = (L[k] || '').trim(); if (t.startsWith('}, [')) { adEnd = k; break } }
if (adEnd > 0) L[adEnd] = T(3) + '}, [revised, path, reviseBackup]);'
console.log('3) adopt backup ok')

// 4) 撤销函数（插在 adoptRevised 之后）
const undo = [
  '',
  T(3) + '/* 撤销本次改稿：从备份恢复，然后复检 */',
  T(3) + 'const undoRevise = useCallback(async function () {',
  T(4) + 'if (!lastBackup || !path) { setError("没有可撤销的改稿备份"); return; }',
  T(4) + 'const b = await readChapter(lastBackup);',
  T(4) + 'if (b.content === null) { setError("备份读不到：" + b.error); return; }',
  T(4) + 'const r = await api("/api/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: path, content: b.content, force: true }) });',
  T(4) + 'if (!r.ok || (r.data && r.data.ok === false)) { setError("撤销失败：" + ((r.data && r.data.error) || r.error || "未知")); return; }',
  T(4) + 'const q = await api("/api/qc?path=" + encodeURIComponent(path));',
  T(4) + 'const d = (q && q.data) || {};',
  T(4) + 'setRecheck({ verdict: d.verdict || "-", issues: Array.isArray(d.issues) ? d.issues : [], undone: true });',
  T(4) + 'setLastBackup(null);',
  T(3) + '}, [lastBackup, path]);',
]
if (adEnd > 0) L.splice(adEnd + 1, 0, ...undo)
console.log('4) undo ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE core logic')
