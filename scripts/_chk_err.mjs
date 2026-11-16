const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
const logs = []
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (m.method === 'Runtime.consoleAPICalled' && (m.params.type === 'error' || m.params.type === 'warning')) {
    logs.push({ t: m.params.type, txt: (m.params.args || []).map(a => String(a.value || a.description || '')).join(' ').slice(0, 200) })
  }
  if (m.method === 'Runtime.exceptionThrown') {
    logs.push({ t: 'exception', txt: String((m.params.exceptionDetails && m.params.exceptionDetails.text) || '').slice(0, 200) })
  }
  if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) }
})
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable'); await call('Page.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

console.log('bootErr:', await ev('window.__bootErr || ""'))
console.log('wpErr:', await ev('window.__wpErr || ""'))
console.log('current panel:', await ev('(function(){var a=document.querySelector(".nvl-pane");return a?String(a.className):"none"})()'))
console.log('plan steps:', await ev('document.querySelectorAll(".nvl-plan__step").length'))
// 切到策划再看
await ev('(function(){var bs=[].slice.call(document.querySelectorAll("button,[role=button],a"));for(var i=0;i<bs.length;i++){if((bs[i].textContent||"").trim()==="\u7b56\u5212"){bs[i].click();return "ok"}}return "no"})()')
await wait(2500)
console.log('after click steps:', await ev('document.querySelectorAll(".nvl-plan__step").length'))
console.log('errors:', JSON.stringify(logs.slice(-8), null, 1))
ws.close(); process.exit(0)
