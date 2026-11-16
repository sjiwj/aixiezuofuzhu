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
const css = `
/* 整块对话区固定到右侧 380px（用 :has 选到真正的内容容器） */
div:has(> [data-conversation-region]) {
  position: fixed !important; right: 0 !important; top: 0 !important; bottom: 0 !important;
  left: auto !important; width: 380px !important; height: auto !important;
  z-index: 30; background: var(--nvl-paper, #fff);
  border-left: 1px solid var(--nvl-rule, #e4e4e7); overflow: auto;
}
`
console.log('inject =', await ev('(function(){var s=document.getElementById("nvl-try-dock");if(!s){s=document.createElement("style");s.id="nvl-try-dock";document.head.appendChild(s)}s.textContent=' + JSON.stringify(css) + ';return "ok"})()'))
await new Promise((r) => setTimeout(r, 1500))
console.log('rect =', JSON.stringify(await ev('(function(){var d=document.querySelector("div:has(> [data-conversation-region])");if(!d)return "none";var r=d.getBoundingClientRect();return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}})()')))
const s = await call('Page.captureScreenshot', { format: 'png' })
if (s.result && s.result.data) { fs.writeFileSync('D:/NovelApp/_tmp/ui-dock-try2.png', Buffer.from(s.result.data, 'base64')); console.log('shot saved') }
ws.close(); process.exit(0)
