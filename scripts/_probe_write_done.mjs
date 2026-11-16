const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
for (let i = 0; i < 4; i++) {
  await wait(20000)
  const t = String(await ev('(document.body.innerText||"").replace(/\s+/g," ")'))
  const state = ['生成中', '已写完', '花费 ¥', '本章按重点章'].filter(function (m) { return t.indexOf(m) >= 0 })
  console.log('t=' + ((i + 1) * 20) + 's state=' + JSON.stringify(state))
  if (state.indexOf('生成中') < 0) { console.log('DONE snippet =', JSON.stringify(t.slice(60, 260))); break }
}
ws.close(); process.exit(0)
