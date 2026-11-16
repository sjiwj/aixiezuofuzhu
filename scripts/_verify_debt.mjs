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
// 1) 点「码字」
await ev('(function(){var bs=[].slice.call(document.querySelectorAll("button"));var b=bs.filter(function(x){return (x.textContent||"").trim()==="\u7801\u5b57"})[0];if(b)b.click();return "ok"})()')
await wait(3000)
// 2) 如果没有编辑器，点章节标题
const has = await ev('document.querySelectorAll(".nvl-editor__bar").length')
if (!has) {
  await ev('(function(){var els=[].slice.call(document.querySelectorAll("*")).filter(function(x){var t=(x.textContent||"").trim();return t.indexOf("\u7b2c")===0 && t.indexOf("\u7ae0")>0 && x.children.length===0});if(els.length)els[0].click();return "clicked"})()')
  await wait(3000)
}
console.log('editor bar =', await ev('document.querySelectorAll(".nvl-editor__bar").length'))
console.log('debt boxes =', await ev('document.querySelectorAll(".nvl-debt").length'))
console.log('debt text  =', JSON.stringify(String(await ev('(function(){var d=document.querySelector(".nvl-debt");return d?(d.textContent||"").replace(/\s+/g," ").slice(0,160):"none"})()'))))
console.log('scene chip =', JSON.stringify(String(await ev('(function(){var d=document.querySelector(".nvl-chip");return d?d.textContent:"none"})()'))))
const shot = await call('Page.captureScreenshot', { format: 'png' })
if (shot.result && shot.result.data) fs.writeFileSync('D:/NovelApp/_tmp/debt-final.png', Buffer.from(shot.result.data, 'base64'))
ws.close(); process.exit(0)
