const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map(); const downloads = []
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (m.method === 'Page.downloadWillBegin') downloads.push(m.params.suggestedFilename)
  if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) }
})
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable'); await call('Page.enable')
await call('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: '%USERPROFILE%\\AppData\\Local\\Temp' }).catch(() => null)
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR:' + JSON.stringify(r.result.exceptionDetails).slice(0,200); return r.result && r.result.result && r.result.result.value }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

await ev('(() => { const b=[...document.querySelectorAll("button")].find(x=>(x.textContent||"").trim().startsWith("设置")); if(b) b.click(); return "ok" })()')
await wait(1500)
console.log('open usage =', await ev('(() => { const row=[...document.querySelectorAll(".nvl-setrow")].find(r=>(r.textContent||"").includes("用量与花费")); if(!row) return "no-row"; row.querySelector("button").click(); return "ok" })()'))
await wait(1200)
console.log('modal text =', JSON.stringify(String(await ev('(() => { const m=document.querySelector(".nvl-modal"); return m ? (m.textContent||"").replace(/\\s+/g," ").slice(0,220) : "none" })()'))))
console.log('has button =', await ev('([...document.querySelectorAll(".nvl-modal button")].map(b=>(b.textContent||"").trim()).join("|"))'))
console.log('click export =', await ev('(() => { const b=[...document.querySelectorAll(".nvl-modal button")].find(x=>(x.textContent||"").trim()==="导出 CSV"); if(!b) return "miss"; b.click(); return "ok" })()'))
await wait(2500)
console.log('downloads =', JSON.stringify(downloads))
ws.close(); process.exit(0)
