import fs from 'node:fs'
const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable'); await call('Page.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }
// 先看对话区内部结构，找出被裁的原因
console.log(JSON.stringify(await ev('(function(){var d=document.querySelector("[data-conversation-region]");if(!d)return "none";var out=[];for(var i=0;i<d.children.length;i++){var e=d.children[i];var r=e.getBoundingClientRect();out.push({t:e.tagName.toLowerCase(),c:String(e.className||"").slice(0,44),y:Math.round(r.y),h:Math.round(r.height)})}return out})()'), null, 1))
console.log('parent =', JSON.stringify(await ev('(function(){var d=document.querySelector("[data-conversation-region]");if(!d)return "none";var p=d.parentElement;var cs=p?getComputedStyle(p):null;var r=p?p.getBoundingClientRect():null;return{tag:p?p.tagName.toLowerCase():"?",cls:p?String(p.className||"").slice(0,50):"",x:r?Math.round(r.x):0,y:r?Math.round(r.y):0,w:r?Math.round(r.width):0,h:r?Math.round(r.height):0,overflow:cs?cs.overflow:"?",pos:cs?cs.position:"?"}})()')))
ws.close(); process.exit(0)
