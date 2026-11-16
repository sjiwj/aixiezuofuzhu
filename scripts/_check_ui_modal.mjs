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
const click = (n) => ev('(() => { const b=[...document.querySelectorAll("button")].find(x=>(x.textContent||"").trim().startsWith(' + JSON.stringify(n) + ')); if(!b) return "miss"; b.click(); return "ok" })()')

// 删除弹窗（章节）
await click('项目'); await wait(1000)
console.log('del =', await ev('(() => { const row=[...document.querySelectorAll(".nvl-tree__chapter")].find(r=>(r.textContent||"").includes("柴没砍完")); if(!row) return "no-row"; const b=row.querySelector("button"); if(!b) return "no-btn"; b.click(); return "ok" })()'))
await wait(700)
console.log('dialog =', JSON.stringify(await ev('(() => { const d=document.querySelector("[role=dialog]"); if(!d) return "no-dialog"; return { text: (d.textContent||"").trim().slice(0,90), inputs: d.querySelectorAll("input").length, buttons: [...d.querySelectorAll("button")].map(b=>b.textContent.trim()) } })()')))
await ev('(() => { const d=document.querySelector("[role=dialog]"); if(!d) return "no"; const b=[...d.querySelectorAll("button")].find(x=>x.textContent.trim()==="取消"); if(b) b.click(); return "cancel" })()')
await wait(500)

// 移动到分支弹窗
await click('设定库'); await wait(1200)
console.log('move =', await ev('(() => { const row=[...document.querySelectorAll(".nvl-tree__chapter")].find(r=>(r.textContent||"").includes("伏笔")); if(!row) return "no-row"; const b=row.querySelector("button"); if(!b) return "no-btn"; b.click(); return "ok" })()'))
await wait(700)
console.log('choice =', JSON.stringify(await ev('(() => { const d=document.querySelector("[role=dialog]"); if(!d) return "no-dialog"; return { title: (d.querySelector(".nvl-modal__title")||{}).textContent, options: [...d.querySelectorAll("button")].map(b=>b.textContent.trim()) } })()')))
ws.close(); process.exit(0)
