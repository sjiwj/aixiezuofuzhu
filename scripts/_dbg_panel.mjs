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
// 左侧导航项：找「码字」按钮
console.log(JSON.stringify(await ev('(function(){var out=[];var all=[].slice.call(document.querySelectorAll("button,a,[role=button],[role=tab],[role=menuitem]"));for(var i=0;i<all.length;i++){var t=(all[i].textContent||"").trim();if(t && t.length<12 && ["\u7801\u5b57","\u9879\u76ee","\u65b0\u4f1a\u8bdd","\u8bbe\u5b9a\u5e93"].indexOf(t)>=0){out.push({t:t,cls:String(all[i].className||"").slice(0,40),tag:all[i].tagName})}}return out})()'), null, 1))
ws.close(); process.exit(0)
