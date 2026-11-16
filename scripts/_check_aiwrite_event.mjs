const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map(); const evts = []
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable'); await call('Log.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR:' + JSON.stringify(r.result.exceptionDetails).slice(0,150); return r.result && r.result.result && r.result.result.value }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
// 埋监听：确认事件到底有没有被消费
await ev('(() => { window.__t = []; window.addEventListener("novelapp:ai-write", function (e) { window.__t.push("ai-write:" + (e.detail||"")); }); window.__t.push("listener-ready"); return "ok" })()')
console.log('click =', await ev('(() => { const b=[...document.querySelectorAll("button")].find(x=>(x.textContent||"").trim()==="AI 写这一章"); if(!b) return "miss"; b.click(); return "ok" })()'))
await wait(3000)
console.log('events =', JSON.stringify(await ev('window.__t')))
console.log('panel =', JSON.stringify(await ev('(document.querySelector("[data-active-panel]")||{}).getAttribute ? document.querySelector("[data-active-panel]").getAttribute("data-active-panel") : "?"')))
console.log('writeState =', JSON.stringify(String(await ev('(document.body.innerText||"").match(/花费 ¥|已写完|AI 正在写|写作中/gi) || []).slice(0,5)')))
ws.close(); process.exit(0)
