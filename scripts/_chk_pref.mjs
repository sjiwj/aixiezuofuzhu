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
  var out = { ls: {}, ss: {} };
  try {
    for (var i = 0; i < localStorage.length; i++) {
      var k = localStorage.key(i);
      if (/theme|appear|prefer/i.test(k)) out.ls[k] = String(localStorage.getItem(k)).slice(0, 80);
    }
  } catch (e) {}
  try {
    for (var j = 0; j < sessionStorage.length; j++) {
      var k2 = sessionStorage.key(j);
      if (/theme|appear|prefer/i.test(k2)) out.ss[k2] = String(sessionStorage.getItem(k2)).slice(0, 80);
    }
  } catch (e) {}
  return out;
})()`), null, 1))
ws.close(); process.exit(0)
