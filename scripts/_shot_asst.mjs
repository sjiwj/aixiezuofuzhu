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
await ev('(function(){var b=document.querySelector(".nvl-asst__fab");if(b){b.click();return "opened"}return "no-fab"})()')
await wait(1200)
// 发一条消息
await ev('(function(){var t=document.querySelector(".nvl-asst__input-ta");if(!t)return "no-ta";var s=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,"value").set;s.call(t,"这一章的节奏怎么样");t.dispatchEvent(new Event("input",{bubbles:true}));return "set"})()')
await ev('(function(){var b=document.querySelector(".nvl-asst__send");if(b){b.click();return "sent"}return "no-btn"})()')
await wait(30000)
const s = await call('Page.captureScreenshot', { format: 'png' })
if (s.result && s.result.data) { fs.writeFileSync('D:/NovelApp/_tmp/ui-asst.png', Buffer.from(s.result.data, 'base64')); console.log('shot saved') }
console.log('msgs =', await ev('document.querySelectorAll(".nvl-asst__msg").length'))
console.log('last msg =', JSON.stringify(String(await ev('(function(){var ms=document.querySelectorAll(".nvl-asst__msg");return ms.length?ms[ms.length-1].textContent.slice(0,150):"none"})()'))))
ws.close(); process.exit(0)
