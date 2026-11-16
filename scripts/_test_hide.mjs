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
console.log('conv region display =', await ev('(function(){var d=document.querySelector("div:has(> [data-conversation-region])");if(!d)return "none";var cs=getComputedStyle(d);return cs.display+" / w="+Math.round(d.getBoundingClientRect().width)})()'))
// 点「新会话」验证会不会冒出来
await ev('(function(){var bs=[].slice.call(document.querySelectorAll("button,a,[role=button],[role=tab]"));for(var i=0;i<bs.length;i++){if((bs[i].textContent||"").trim()==="\u65b0\u4f1a\u8bdd"){bs[i].click();return "clicked"}}return "no-btn"})()')
await wait(2500)
console.log('after click display =', await ev('(function(){var d=document.querySelector("div:has(> [data-conversation-region])");if(!d)return "none";var cs=getComputedStyle(d);return cs.display+" / w="+Math.round(d.getBoundingClientRect().width)})()'))
const s = await call('Page.captureScreenshot', { format: 'png' })
if (s.result && s.result.data) { fs.writeFileSync('D:/NovelApp/_tmp/ui-hide-test.png', Buffer.from(s.result.data, 'base64')); console.log('shot saved') }
ws.close(); process.exit(0)
