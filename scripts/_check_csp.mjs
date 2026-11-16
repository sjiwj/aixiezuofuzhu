const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map(); const logs = []
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (m.method === 'Log.entryAdded') logs.push('LOG ' + m.params.entry.level + ': ' + String(m.params.entry.text).slice(0, 200))
  if (m.method === 'Runtime.consoleAPICalled') logs.push('CON ' + m.params.type + ': ' + (m.params.args || []).map(a => a.value || a.description || '').join(' ').slice(0, 200))
  if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) }
})
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable'); await call('Log.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR:' + JSON.stringify(r.result.exceptionDetails).slice(0,200); return r.result && r.result.result && r.result.result.value }
console.log('csp =', JSON.stringify(await ev('(document.querySelector(\'meta[http-equiv="Content-Security-Policy"]\')||{}).content || "no-meta"')))
console.log('retry =', await ev('fetch("http://127.0.0.1:18760/novelapp/handshake").then(r => "ok:" + r.status).catch(e => "ERR:" + e.message)'))
await new Promise((r) => setTimeout(r, 800))
console.log('logs =', JSON.stringify(logs.slice(-8), null, 1))
ws.close(); process.exit(0)
