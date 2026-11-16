const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }
// 谁给它 display:none？遍历匹配的 CSS 规则
console.log(JSON.stringify(await ev(`(function(){
  var b = document.querySelector("button.z0mANW_brand") || [].slice.call(document.querySelectorAll("button")).filter(function(x){return String(x.className||"").indexOf("brand")>=0})[0];
  if (!b) return "no-brand-btn";
  var hits = [];
  [].slice.call(document.styleSheets).forEach(function(ss){
    var rules; try { rules = ss.cssRules } catch(e){ return }
    if (!rules) return;
    [].slice.call(rules).forEach(function(r){
      if (!r.selectorText) return;
      try { if (b.matches(r.selectorText) && r.style && r.style.display) hits.push({ sel: r.selectorText.slice(0,80), disp: r.style.display }); } catch(e){}
    });
  });
  return { cls: String(b.className), inlineDisp: b.style.display, rules: hits };
})()`), null, 1))
ws.close(); process.exit(0)
