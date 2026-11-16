const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }
// 宿主的「外观」分组：看它的完整结构和里面的按钮
console.log(JSON.stringify(await ev(`(function(){
  var g = document.querySelector(".aujaXa_group");
  if (!g) return "no-group";
  var out = { cls: String(g.className), children: [] };
  [].slice.call(g.children).forEach(function(c){
    out.children.push({ tag: c.tagName.toLowerCase(), cls: String(c.className||"").slice(0,40), txt: (c.textContent||"").trim().slice(0,40) });
  });
  // 组里的按钮（含 aria-label）
  var btns = [].slice.call(g.querySelectorAll("button")).map(function(b){
    return { txt: (b.textContent||"").trim().slice(0,10), label: b.getAttribute("aria-label")||"", cls: String(b.className||"").slice(0,30) };
  });
  out.buttons = btns;
  return out;
})()`), null, 1))
ws.close(); process.exit(0)
