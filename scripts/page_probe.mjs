// 页面级连通断言：补 ui_smoke 的洞（只查渲染，查不到"前端连不上后端"）
// 用法: node scripts/page_probe.mjs --port 9650
const PORT = (() => { const i = process.argv.indexOf('--port'); return (i > 0 && process.argv[i + 1]) || process.env.NOVELAPP_CDP_PORT || '9650' })()
const list = await (await fetch('http://127.0.0.1:' + PORT + '/json/list')).json().catch(() => null)
if (!list) { console.log('SKIP no CDP on ' + PORT); process.exit(0) }
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => {
  const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true })
  if (r.result && r.result.exceptionDetails) return { __err: String(r.result.exceptionDetails.text || '').slice(0, 200) }
  return r.result && r.result.result && r.result.result.value
}

let fails = 0
function check(name, ok, detail) {
  if (!ok) fails++
  console.log((ok ? 'PASS  ' : 'FAIL  ') + name.padEnd(22) + ' ' + (detail || ''))
}

// 1) handshake（GET，验证 CORS 放行 + 拿到 token）
const hs = await ev('fetch("http://127.0.0.1:18760/novelapp/handshake", {cache:"no-store"}).then(r => r.json().then(j => ({status:r.status, token:!!j.token}))).catch(e => ({status:0, err:String(e.message||e)}))')
check('handshake', hs && hs.status === 200 && hs.token === true, JSON.stringify(hs))

// 2) projects（要有书，证明数据真的到手）
const pj = await ev('fetch("http://127.0.0.1:18760/novelapp/projects", {cache:"no-store"}).then(r => r.json().then(j => ({status:r.status, books:(j.books||[]).length}))).catch(e => ({status:0, err:String(e.message||e)}))')
check('projects', pj && pj.status === 200 && pj.books >= 1, JSON.stringify(pj))

// 3) /api/health（经插件代理，证明 8770 可达 + token 注入）
const hl = await ev('fetch("http://127.0.0.1:18760/api/health", {cache:"no-store"}).then(r => r.json().then(j => ({status:r.status, ok:j.ok === true}))).catch(e => ({status:0, err:String(e.message||e)}))')
check('api/health', hl && hl.status === 200 && hl.ok === true, JSON.stringify(hl))

// 4) SSE 鉴权通道：POST /api/polish 空 body。401 = 没带 token（SSE 路径坏）；其他 = 通道正常
const sse = await ev('(async () => { const b="http://127.0.0.1:18760"; try { const h=await (await fetch(b+"/novelapp/handshake",{cache:"no-store"})).json(); const tk=h&&h.token?String(h.token):""; const r=await fetch(b+"/api/polish",{method:"POST",headers:{"Content-Type":"application/json","X-Novelapp-Token":tk},body:"{}"}); return {status:r.status, withToken:!!tk}; } catch (e) { return {status:0, err:String(e.message||e)}; } })()')
check('sse auth path', sse && sse.status !== 401 && sse.status !== 0, JSON.stringify(sse))

// 5) 页面不出现 [object Object]（渲染兜底）
const txt = String(await ev('(document.body.innerText||"")'))
check('no [object Object]', !txt.includes('[object Object]'), 'len=' + txt.length)

console.log()
console.log('结果: ' + (5 - fails) + '/5 ' + (fails ? 'FAIL' : 'PASS'))
ws.close()
process.exit(fails ? 1 : 0)
