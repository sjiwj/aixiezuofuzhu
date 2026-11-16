
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('sseHeaders')) { console.log('ALREADY'); process.exit(0) }
const sig = 'async function streamSSE(url, body, onEvent, signal) {'
const i = s.indexOf(sig)
if (i < 0) throw new Error('streamSSE sig')
const anchor = 'let res = null;'
const j = s.indexOf(anchor, i)
if (j < 0) throw new Error('res anchor')
const ins = 'let res = null;\n\t\t\tlet tk = "";\n\t\t\ttry { tk = await nvlToken(); } catch (e0) { tk = ""; }\n\t\t\tconst sseHeaders = { "Content-Type": "application/json" };\n\t\t\tif (tk) sseHeaders["X-Novelapp-Token"] = tk;'
s = s.slice(0, j) + ins + s.slice(j + anchor.length)
const hl = 'headers: { "Content-Type": "application/json" },'
const k = s.indexOf(hl, i)
if (k < 0) throw new Error('headers line')
s = s.slice(0, k) + 'headers: sseHeaders,' + s.slice(k + hl.length)
fs.writeFileSync(p, s, 'utf8')
console.log('streamSSE token injected')
