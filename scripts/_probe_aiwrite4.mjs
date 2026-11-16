const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR:' + JSON.stringify(r.result.exceptionDetails).slice(0,200); return r.result && r.result.result && r.result.result.value }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
for (const t of [0, 8000, 20000, 35000]) {
  if (t) await wait(t === 8000 ? 8000 : 12000)
  const s = String(await ev('(function(){var b=document.body.innerText||"";var m=b.match(/(AI 正在写[^\n]*|已写完[^\n]*|花费 ¥[0-9.]+|本章按[重点卷][^\n]*|先选一章|资料不全|chapter_not_empty|还有 [0-9]+ 字)/g);return m?m.slice(0,4).join(" | "):""})()'))
  console.log('t=' + t + ' ->', JSON.stringify(s))
}
console.log('tierNote els =', JSON.stringify(await ev('(function(){return [].slice.call(document.querySelectorAll(".nvl-dim")).map(function(e){return (e.textContent||"").trim()}).filter(function(t){return t.length>0 && t.length<80}).slice(0,4)})()')))
ws.close(); process.exit(0)
