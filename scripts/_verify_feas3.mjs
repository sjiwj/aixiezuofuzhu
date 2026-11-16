import fs from 'node:fs'
const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable'); await call('Page.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
// 1) 点「项目」
await ev('(function(){var bs=[].slice.call(document.querySelectorAll("button,a,[role=tab]"));for(var i=0;i<bs.length;i++){if((bs[i].textContent||"").trim()==="\u9879\u76ee"){bs[i].click();return "ok"}}return "no"})()')
await wait(3000)
// 2) 展开挂件
await ev('(function(){var b=document.querySelector(".nvl-dock__title");if(b){b.click();return "opened"}return "no-title"})()')
await wait(4000)
console.log('dock text  =', JSON.stringify(String(await ev('(function(){var d=document.querySelector(".nvl-dock");return d?(d.textContent||"").replace(/\s+/g," ").slice(0,200):"none"})()'))))
console.log('feasible   =', await ev('document.querySelectorAll(".nvl-dock__feasible").length'))
console.log('feas text  =', JSON.stringify(String(await ev('(function(){var d=document.querySelector(".nvl-dock__feasible");return d?d.textContent:"none"})()'))))
const shot = await call('Page.captureScreenshot', { format: 'png' })
if (shot.result && shot.result.data) fs.writeFileSync('D:/NovelApp/_tmp/feas-fact.png', Buffer.from(shot.result.data, 'base64'))
ws.close(); process.exit(0)
