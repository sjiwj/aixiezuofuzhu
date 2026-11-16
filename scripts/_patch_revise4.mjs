
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('useNotes')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) state：勾选哪些意见 + 改稿前原文（用于回滚）
const st = find('const [recheck, setRecheck] = useState(null);')
if (st < 0) throw new Error('recheck state')
L.splice(st + 1, 0,
  T(3) + 'const [useNotes, setUseNotes] = useState({});',
  T(3) + 'const [reviseBackup, setReviseBackup] = useState(null);'
)
console.log('1) state ok')

// 2) reviseWithNotes：只取勾选的；记录原文用于回滚
const rv = find('const reviseWithNotes = useCallback(async function () {')
if (rv < 0) throw new Error('reviseWithNotes')
// 替换 notes 收集循环
const collStart = find('reviewers.forEach(function (r) {', rv)
const collEnd = find('});', collStart)
if (collStart < 0 || collEnd < 0) throw new Error('notes collect')
L.splice(collStart, collEnd - collStart + 1,
  T(4) + 'reviewers.forEach(function (r) {',
  T(5) + 'const rid = r.id || r.name || "";',
  T(5) + 'if (useNotes[rid] === false) return;',
  T(5) + 'if (r.status === "done" && r.text) notes.push((r.name || rid || "审稿人") + "：" + String(r.text).slice(0, 1200));',
  T(4) + '});'
)
// 在 notes 判空之后、setRevising 之前：读原文存备份
const emptyCheck = find('if (!notes.length) { setError("还没有可用的审稿意见"); return; }', rv)
if (emptyCheck < 0) throw new Error('notes empty check')
L.splice(emptyCheck + 1, 0,
  T(4) + '/* 回滚用：先把改稿前的原文读出来存着 */',
  T(4) + 'let _orig = "";',
  T(4) + 'try { const _o = await readChapter(path); _orig = String(_o.content || ""); } catch (e0) { /* ignore */ }',
  T(4) + 'setReviseBackup(_orig || null);'
)
console.log('2) reviseWithNotes ok')

// 3) adoptRevised：落盘前写一份 .bak-revise-<时间戳>.md，并支持撤销
const ad = find('const adoptRevised = useCallback(async function () {')
if (ad < 0) throw new Error('adoptRevised')
let adEnd = -1
for (let k = ad; k < ad + 20; k++) { if ((L[k] || '').trim().startsWith('}, [revised, path'+"'"+']')) || (L[k] || '').trim().startsWith('}, [revised, path]'))') { adEnd = k; break } }
if (adEnd < 0) { for (let k = ad; k < ad + 20; k++) { if ((L[k] || '').trim().startsWith('}, [')) { adEnd = k; break } } }
if (adEnd < 0) throw new Error('adopt end')
// 在函数体开头插入备份逻辑（第一行 const r = await api("/api/save"...) 之前）
const saveLine = find('const r = await api("/api/save"', ad)
if (saveLine < 0) throw new Error('save line')
L.splice(saveLine, 0,
  T(4) + '/* 回滚用备份：改稿前的原文另存一份 .bak-revise-时间戳.md（能被普通编辑器打开） */',
  T(4) + 'if (reviseBackup) {',
  T(5) + 'const _stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 15);',
  T(5) + 'const _bp = path.replace(/\\.md$/i, "") + ".bak-revise-" + _stamp + ".md";',
  T(5) + 'try { await api("/api/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: _bp, content: reviseBackup, force: true }) }); setLastBackup(_bp); } catch (e0) { /* ignore */ }',
  T(4) + '}'
)
// 依赖加 reviseBackup
if (adEnd >= 0) L[adEnd] = T(3) + '}, [revised, path, reviseBackup, setLastBackup]);'
console.log('3) adopt + backup ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE part1')
