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
  var cs = getComputedStyle(document.documentElement);
  var out = { htmlAttrs: {}, bodyBg: getComputedStyle(document.body).backgroundColor, colorScheme: cs.colorScheme, vars: {} };
  for (var i=0; i<document.documentElement.attributes.length; i++) {
    var a = document.documentElement.attributes[i];
    if (a.name.indexOf("data-") === 0 || a.name === "class") out.htmlAttrs[a.name] = a.value.slice(0,60);
  }
  ["--dsh-bg","--dsh-fg","--dsh-surface","--dsh-border","--dsh-boot-bg","--dsh-muted"].forEach(function(k){
    var v = cs.getPropertyValue(k).trim();
    if (v) out.vars[k] = v;
  });
  return out;
})()`), null, 1))
ws.close(); process.exit(0)
