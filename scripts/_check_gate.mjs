const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR:' + JSON.stringify(r.result.exceptionDetails).slice(0,260); return r.result && r.result.result && r.result.result.value }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const click = (n) => ev('(() => { const b=[...document.querySelectorAll("button")].find(x=>(x.textContent||"").trim().startsWith(' + JSON.stringify(n) + ')); if(!b) return "miss"; b.click(); return "ok" })()')

// 1) 门禁详情
console.log('审稿 =', await click('审稿')); await wait(1200)
console.log('详情 =', await ev('(() => { const b=[...document.querySelectorAll("button")].find(x=>(x.textContent||"").trim()==="详情"); if(!b) return "miss"; b.click(); return "ok" })()'))
await wait(700)
const g = String(await ev('(document.body.innerText||"").replace(/\\s+/g," ")'))
console.log('GATE =', JSON.stringify(g.slice(0, 600)))
console.log('objectObject =', g.includes('[object Object]'))

// 2) 删除章节
console.log('项目 =', await click('项目')); await wait(900)
console.log('books =', JSON.stringify(await ev('([...document.querySelectorAll(".nvl-tree__bookname")].map(e=>(e.textContent||"").trim()))')))
console.log('chapters =', JSON.stringify(await ev('([...document.querySelectorAll(".nvl-tree__chapter")].map(e=>(e.textContent||"").trim()))')))
ws.close(); process.exit(0)
