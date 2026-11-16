const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }
console.log(JSON.stringify(await ev(`(function(){
  var t = [].slice.call(document.querySelectorAll("*")).filter(function(e){ return e.children.length===0 && /余额|充值/.test(e.textContent||"") });
  return t.slice(0,4).map(function(e){
    var cs = getComputedStyle(e);
    var p = e.parentElement, pcs = p ? getComputedStyle(p) : null;
    return { txt: (e.textContent||"").trim().slice(0,12), tag: e.tagName.toLowerCase(),
             cls: String(e.className||"").slice(0,30),
             color: cs.color, bg: pcs ? pcs.backgroundColor : "",
             pcls: p ? String(p.className||"").slice(0,30) : "" };
  });
})()`), null, 1))
ws.close(); process.exit(0)
