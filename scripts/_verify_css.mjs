import fs from 'node:fs'
const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }

const checks = await ev(`(function(){
  function cs(sel, prop, fallback) {
    var e = document.querySelector(sel);
    if (!e) return "NO-EL";
    var v = getComputedStyle(e)[prop];
    return v === undefined ? "UNDEF" : v;
  }
  function csCls(sub, prop) {
    var e = [].slice.call(document.querySelectorAll("div")).filter(function(x){ return String(x.className||"").indexOf(sub)>=0 })[0];
    if (!e) return "NO-EL";
    return getComputedStyle(e)[prop];
  }
  return {
    theme: document.documentElement.getAttribute("data-nvl-theme"),
    dsTheme: document.documentElement.getAttribute("data-ds-theme-source"),
    bodyBg: getComputedStyle(document.body).backgroundColor,
    frameBg: csCls("_frame", "backgroundColor"),
    sidebarColBg: csCls("sidebarCol", "backgroundColor"),
    quietBarsBg: csCls("quietBars", "backgroundColor"),
    accountBg: cs(".nvl-account", "backgroundColor"),
    accountColor: cs(".nvl-account", "color"),
    linkColor: cs(".nvl-account__link", "color"),
    debtBorder: cs(".nvl-debt", "borderLeftWidth"),
    debtBorderColor: cs(".nvl-debt", "borderLeftColor"),
    textareaFont: (cs(".nvl-textarea", "fontFamily") || "").split(",")[0],
    textareaBg: cs(".nvl-textarea", "backgroundColor"),
    textareaLh: cs(".nvl-textarea", "lineHeight"),
    convHidden: (function(){ var d=document.querySelector("div:has(> [data-conversation-region])"); if(!d) return "NO-EL"; return getComputedStyle(d).display; })(),
    sidebarListArea: cs("[data-sidebar-list-area]", "display"),
    newSessionBtn: (function(){ var b=document.querySelector("button[aria-label='新建会话']:not(:has(.nvl-brandname))"); if(!b) return "NO-EL"; return getComputedStyle(b).display; })(),
    brandVisible: (function(){ var b=document.querySelector(".nvl-brandname"); if(!b) return "NO-EL"; var r=b.getBoundingClientRect(); return r.height>0 ? "visible" : "hidden"; })(),
    dockRight: cs(".nvl-dock", "right"),
    asstBottom: cs(".nvl-asst", "bottom")
  };
})()`)
console.log(JSON.stringify(checks, null, 1))
ws.close(); process.exit(0)
