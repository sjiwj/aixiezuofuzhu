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
  var nav = document.querySelector("[data-sidebar-scrollport] nav");
  var items = [];
  if (nav) { [].slice.call(nav.children).forEach(function(e){ var r=e.getBoundingClientRect(); if (r.height > 0) items.push((e.textContent||"").trim().slice(0,8)); }); }
  return {
    nav_visible: items,
    newSession_visible: (function(){var b=document.querySelector("button[aria-label='新建会话']");if(!b)return "no-el";return getComputedStyle(b).display!=="none"})() ,
    projHeader_visible: (function(){var d=document.querySelector("div:has(> div > button[aria-label='添加项目'])");if(!d)return "no-el";return getComputedStyle(d).display!=="none"})() ,
    conv_hidden: (function(){var d=document.querySelector("div:has(> [data-conversation-region])");if(!d)return "no-el";return getComputedStyle(d).display==="none"})()
  };
})()`), null, 1))
ws.close(); process.exit(0)
