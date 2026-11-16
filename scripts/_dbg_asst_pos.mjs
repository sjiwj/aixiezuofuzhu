const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR'; return r.result && r.result.result && r.result.result.value }
console.log(JSON.stringify(await ev('(function(){var a=document.querySelector(".nvl-asst");if(!a)return "none";var cs=getComputedStyle(a);var p=a.parentElement;var pcs=p?getComputedStyle(p):null;return{pos:cs.position,bottom:cs.bottom,right:cs.right,top:cs.top,z:cs.zIndex,parentTag:p?p.tagName:"?",parentTransform:pcs?pcs.transform:"?",parentPos:pcs?pcs.position:"?"}})()')))
// 宿主主区：找聊天输入框的祖先
console.log(JSON.stringify(await ev('(function(){var ta=document.querySelector("textarea");if(!ta)return "no-textarea";var chain=[];var e=ta;for(var i=0;i<8&&e;i++){var r=e.getBoundingClientRect();chain.push({t:e.tagName.toLowerCase(),c:String(e.className||"").slice(0,50),x:Math.round(r.x),w:Math.round(r.width)});e=e.parentElement}return chain})()'), null, 1))
ws.close(); process.exit(0)
