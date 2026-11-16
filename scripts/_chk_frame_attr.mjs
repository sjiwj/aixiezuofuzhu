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
  var f = [].slice.call(document.querySelectorAll("div")).filter(function(e){ return String(e.className||"").indexOf("_frame")>=0 })[0];
  if (!f) return "no-frame";
  var attrs = {};
  for (var i=0;i<f.attributes.length;i++){ attrs[f.attributes[i].name] = f.attributes[i].value.slice(0,50); }
  var cs = getComputedStyle(f);
  return { attrs: attrs, bg: cs.backgroundColor, color: cs.color,
           cssVars: ["--dsh-bg","--dsh-fg","--dsh-sidebar-bg","--dsh-surface","--dsh-border","--dsh-canvas","--dsh-elevated"]
             .map(function(k){ return k + "=" + cs.getPropertyValue(k).trim() }).filter(function(s){ return s.indexOf("=") !== s.length-1 }) };
})()`), null, 1))
ws.close(); process.exit(0)
