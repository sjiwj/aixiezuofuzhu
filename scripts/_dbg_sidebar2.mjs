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
// 侧栏结构
console.log(JSON.stringify(await ev(`(function(){
  var sp = document.querySelector("[data-sidebar-scrollport]");
  if (!sp) return "no-scrollport";
  var out = [];
  function walk(e, d) {
    if (d > 4 || out.length > 24) return;
    var r = e.getBoundingClientRect();
    if (r.height > 4 && r.width > 4) {
      out.push({ d: d, t: e.tagName.toLowerCase(), c: String(e.className||"").slice(0,32),
                 txt: (e.children.length === 0 ? (e.textContent||"").trim().slice(0,14) : ""),
                 y: Math.round(r.y), h: Math.round(r.height),
                 disp: getComputedStyle(e).display });
    }
    [].slice.call(e.children).forEach(function(ch){ walk(ch, d+1) });
  }
  walk(sp, 0);
  return out;
})()`), null, 1))
const s = await call('Page.captureScreenshot', { format: 'png' })
if (s.result && s.result.data) { fs.writeFileSync('D:/NovelApp/_tmp/ui-sidebar.png', Buffer.from(s.result.data, 'base64')); console.log('shot saved') }
ws.close(); process.exit(0)
