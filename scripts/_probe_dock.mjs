import fs from 'node:fs'
const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable'); await call('Page.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR:' + JSON.stringify(r.result.exceptionDetails).slice(0,180); return r.result && r.result.result && r.result.result.value }
console.log('dock exists =', await ev('document.querySelectorAll(".nvl-dock").length'))
console.log('dock html =', JSON.stringify(String(await ev('(function(){var d=document.querySelector(".nvl-dock");return d?(d.textContent||"").replace(/\s+/g," ").slice(0,300):"none"})()'))))
console.log('dock rect =', JSON.stringify(await ev('(function(){var d=document.querySelector(".nvl-dock");if(!d)return null;var r=d.getBoundingClientRect();var cs=getComputedStyle(d);return {w:Math.round(r.width),h:Math.round(r.height),x:Math.round(r.x),y:Math.round(r.y),bg:cs.backgroundColor,color:cs.color,display:cs.display,z:cs.zIndex}})()')))
const shot = await call('Page.captureScreenshot', { format: 'png' })
if (shot.result && shot.result.data) { fs.writeFileSync('D:/NovelApp/_tmp/dock-bug.png', Buffer.from(shot.result.data, 'base64')); console.log('shot saved') }
ws.close(); process.exit(0)
