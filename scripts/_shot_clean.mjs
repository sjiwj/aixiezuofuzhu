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
// 关设置弹窗
await ev('(function(){var b=[].slice.call(document.querySelectorAll("button")).filter(function(x){return (x.textContent||"").trim()==="\u00d7" || (x.getAttribute("aria-label")||"").indexOf("\u5173")>=0});if(b.length)b[0].click();return "ok"})()')
await wait(800)
// 强制浅色
await ev('(function(){document.documentElement.dataset.nvlTheme="light";return "light"})()')
await wait(600)
// 进码字
await ev('(function(){var bs=[].slice.call(document.querySelectorAll("button,a,[role=tab]"));for(var i=0;i<bs.length;i++){if((bs[i].textContent||"").trim()==="\u7801\u5b57"){bs[i].click();return "ok"}}return "no"})()')
await wait(3500)
const s = await call('Page.captureScreenshot', { format: 'png' })
if (s.result && s.result.data) { fs.writeFileSync('D:/NovelApp/_tmp/ui-book.png', Buffer.from(s.result.data, 'base64')); console.log('shot saved') }
console.log('text font =', await ev('(function(){var t=document.querySelector(".nvl-textarea");if(!t)return "no";var cs=getComputedStyle(t);return cs.fontFamily.split(",")[0]+" | "+cs.fontSize+" | lh "+cs.lineHeight+" | max-w "+cs.maxWidth})()'))
ws.close(); process.exit(0)
