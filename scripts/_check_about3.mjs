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

// 关于弹层
console.log('open =', await ev('(() => { const row=[...document.querySelectorAll(".nvl-setrow")].find(r=>(r.textContent||"").includes("关于与许可")); if(!row) return "no-row"; const b=row.querySelector("button"); b.click(); return "ok" })()'))
await wait(700)
console.log('ABOUT =', JSON.stringify(String(await ev('(() => { const d=document.querySelector("[role=dialog]"); return d ? (d.textContent||"").replace(/\\s+/g," ").slice(0, 520) : "no-dialog" })()'))))
await ev('(() => { const d=[...document.querySelectorAll("button")].find(b=>b.textContent.trim()==="关闭"); if(d) d.click(); return "closed" })()')
await wait(500)

// 码字面板导出按钮
await ev('(() => { const d=[...document.querySelectorAll("button")].find(b=>b.textContent.trim()==="关闭"); if(d) d.click(); return "x" })()')
await wait(400)
await ev('(() => { const b=[...document.querySelectorAll("button")].find(x=>(x.textContent||"").trim().startsWith("码字")); if(b) b.click(); return "ok" })()')
await wait(1200)
console.log('hasExport =', await ev('([...document.querySelectorAll("button")].some(b=>(b.textContent||"").trim()==="导出 txt"))'))
console.log('buttons =', JSON.stringify(await ev('([...document.querySelectorAll(".nvl-editor__bar button, .nvl-head button")].map(b=>b.textContent.trim()).filter(Boolean).slice(0,12))')))
ws.close(); process.exit(0)
