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
await ev('(function(){document.documentElement.dataset.nvlTheme="light";return "ok"})()')
await wait(600)
console.log('paper =', JSON.stringify(await ev('getComputedStyle(document.documentElement).getPropertyValue("--nvl-paper").trim()')))
console.log('ink   =', JSON.stringify(await ev('getComputedStyle(document.documentElement).getPropertyValue("--nvl-ink").trim()')))
console.log('radius=', JSON.stringify(await ev('getComputedStyle(document.documentElement).getPropertyValue("--nvl-radius-1").trim()')))
// 切到码字面板再截图
await ev('(function(){var b=[].slice.call(document.querySelectorAll("button")).filter(function(x){return (x.textContent||"").trim().indexOf("码字")===0})[0];if(b)b.click();return "ok"})()')
await wait(1200)
const shot = await call('Page.captureScreenshot', { format: 'png' })
if (shot.result && shot.result.data) {
  fs.writeFileSync('D:/NovelApp/_tmp/theme-light.png', Buffer.from(shot.result.data, 'base64'))
  console.log('screenshot saved')
}
ws.close(); process.exit(0)
