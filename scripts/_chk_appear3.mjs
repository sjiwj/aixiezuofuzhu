const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }
console.log('theme =', await ev('document.documentElement.getAttribute("data-nvl-theme")'))
console.log('dsTheme =', await ev('document.documentElement.getAttribute("data-ds-theme-source")'))
console.log('colorScheme =', await ev('getComputedStyle(document.documentElement).colorScheme'))
// 找「外观」字样和那几个主题按钮
console.log(JSON.stringify(await ev(`(function(){
  var out = [];
  var all = [].slice.call(document.querySelectorAll("*"));
  all.forEach(function(e){
    if (e.children.length) return;
    var t = (e.textContent||"").trim();
    if (t === "外观" || t === "浅色" || t === "深色" || t === "跟随系统") {
      var r = e.getBoundingClientRect();
      out.push({ t: t, tag: e.tagName.toLowerCase(), cls: String(e.className||"").slice(0,40), y: Math.round(r.y), h: Math.round(r.height), disp: getComputedStyle(e).display });
    }
  });
  return out;
})()`), null, 1))
ws.close(); process.exit(0)
