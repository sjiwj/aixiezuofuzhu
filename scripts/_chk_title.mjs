const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR:'+JSON.stringify(r.result.exceptionDetails).slice(0,200); return r.result && r.result.result && r.result.result.value }
console.log(JSON.stringify(await ev(`(function(){
  var t = [].slice.call(document.querySelectorAll("*")).filter(function(e){ return e.children.length===0 && (e.textContent||"").trim()==="小说工作台" });
  if (!t.length) return "title-not-found";
  var e = t[0], chain = [];
  for (var i=0; i<8 && e; i++) {
    var r = e.getBoundingClientRect();
    chain.push({ tag:e.tagName.toLowerCase(), cls:String(e.className||"").slice(0,34), y:Math.round(r.y), h:Math.round(r.height), disp:getComputedStyle(e).display, vis:getComputedStyle(e).visibility });
    e = e.parentElement;
  }
  return chain;
})()`), null, 1))
ws.close(); process.exit(0)
