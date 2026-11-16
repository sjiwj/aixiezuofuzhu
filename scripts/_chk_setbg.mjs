const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
await ev('(function(){var bs=[].slice.call(document.querySelectorAll("button,[role=button],a"));for(var i=0;i<bs.length;i++){if((bs[i].textContent||"").trim()==="\u8bbe\u7f6e"){bs[i].click();return "ok"}}return "no"})()')
await wait(2200)
console.log(JSON.stringify(await ev(`(function(){
  // 找设置面板的容器（含「设置」标题 + 「通用设置」的那个 div）
  var all = [].slice.call(document.querySelectorAll("div"));
  var panel = all.filter(function(e){
    var t = (e.textContent||"");
    return t.length > 200 && t.length < 6000 && t.indexOf("通用设置") >= 0 && t.indexOf("字号大小") >= 0;
  }).sort(function(a,b){ return a.textContent.length - b.textContent.length })[0];
  if (!panel) return "no-panel";
  var chain = [];
  for (var i=0;i<6 && panel;i++){
    var cs = getComputedStyle(panel);
    var r = panel.getBoundingClientRect();
    chain.push({ tag: panel.tagName.toLowerCase(), cls: String(panel.className||"").slice(0,36),
                 bg: cs.backgroundColor, color: cs.color,
                 w: Math.round(r.width), h: Math.round(r.height) });
    panel = panel.parentElement;
  }
  return chain;
})()`), null, 1))
ws.close(); process.exit(0)
