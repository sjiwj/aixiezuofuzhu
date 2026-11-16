import fs from 'node:fs'
const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const dump = async (tag) => {
  console.log(tag + ' html.class =', JSON.stringify(await ev('document.documentElement.className')))
  console.log(tag + ' html.dataset =', JSON.stringify(await ev('JSON.stringify(document.documentElement.dataset)')))
  console.log(tag + ' body.class =', JSON.stringify(await ev('document.body.className')))
  console.log(tag + ' body.bg =', JSON.stringify(await ev('getComputedStyle(document.body).backgroundColor')))
}
await dump('before')
// 点 DSH 设置里的「浅色」
await ev('(function(){var b=[].slice.call(document.querySelectorAll("button")).filter(function(x){var t=(x.textContent||"").trim();return t==="\u6d45\u8272"})[0];if(b)b.click();return b?"clicked":"miss"})()')
await wait(1500)
await dump('after ')
ws.close(); process.exit(0)
