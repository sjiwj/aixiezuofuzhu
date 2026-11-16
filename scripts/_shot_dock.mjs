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
// 展开挂件看完整效果
await ev('(function(){var b=document.querySelector(".nvl-dock__title");if(b)b.click();return "ok"})()')
await wait(800)
const shot = await call('Page.captureScreenshot', { format: 'png' })
if (shot.result && shot.result.data) { fs.writeFileSync('D:/NovelApp/_tmp/dock-fixed.png', Buffer.from(shot.result.data, 'base64')); console.log('shot saved') }
ws.close(); process.exit(0)
