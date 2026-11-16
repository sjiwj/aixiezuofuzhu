
import fs from 'node:fs'
const p = 'D:/NovelApp/scripts/page_probe.mjs'
let s = fs.readFileSync(p, 'utf8')
const old = "const sse = await ev('fetch(\"http://127.0.0.1:18760/api/polish\", {method:\"POST\", headers:{\"Content-Type\":\"application/json\"}, body:\"{}\"}).then(r => ({status:r.status})).catch(e => ({status:0, err:String(e.message||e)}))')"
if (!s.includes(old)) throw new Error('probe anchor')
const neu = "const sse = await ev('(async () => { const b=\"http://127.0.0.1:18760\"; try { const h=await (await fetch(b+\"/novelapp/handshake\",{cache:\"no-store\"})).json(); const tk=h&&h.token?String(h.token):\"\"; const r=await fetch(b+\"/api/polish\",{method:\"POST\",headers:{\"Content-Type\":\"application/json\",\"X-Novelapp-Token\":tk},body:\"{}\"}); return {status:r.status, withToken:!!tk}; } catch (e) { return {status:0, err:String(e.message||e)}; } })()')"
s = s.split(old).join(neu)
fs.writeFileSync(p, s, 'utf8')
console.log('probe fixed: 带 token 探测')
