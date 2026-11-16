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

// 点「角色卡」分支行右侧的 +
console.log('分支+ =', await ev('(() => { const rows=[...document.querySelectorAll(".nvl-tree__bookname")]; const row=rows.find(r=>(r.textContent||"").includes("角色卡")); if(!row) return "no-row"; const b=row.querySelector("button"); if(!b) return "no-btn"; b.click(); return "ok" })()'))
await wait(700)
console.log('dialog =', await ev('(() => { const d=document.querySelector("[role=dialog]"); return d ? (d.textContent||"").trim().slice(0,40) : "no-dialog" })()'))
console.log('fill+ok =', await ev('(() => { const d=document.querySelector("[role=dialog]"); if(!d) return "no-dialog"; const i=d.querySelector("input"); i.value="主角"; i.dispatchEvent(new Event("input",{bubbles:true})); const ok=[...d.querySelectorAll("button")].find(b=>(b.textContent||"").trim()==="确定"); ok.click(); return "ok" })()'))
await wait(1800)
console.log('AFTER =', JSON.stringify(String(await ev('(document.body.innerText||"").replace(/\\s+/g," ").slice(0,300)'))))
ws.close(); process.exit(0)
