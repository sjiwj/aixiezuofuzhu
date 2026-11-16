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
const clickNav = async (label) => {
  await ev('(function(){var bs=[].slice.call(document.querySelectorAll("button,a,[role=tab]"));for(var i=0;i<bs.length;i++){if((bs[i].textContent||"").trim()==="' + label + '"){bs[i].click();return "ok"}}return "no"})()')
  await wait(1200)
}
const getMode = async () => {
  const r = await ev(`(async function(){try{var tk=await nvlToken();var r=await fetch(apiBase().replace(/\\/+$/,"")+"/novelapp/mode",{headers:tk?{"X-Novelapp-Token":tk}:{}});var j=await r.json();return j.mode+" | tools="+(j.tools||[]).length+" | auto="+j.auto}catch(e){return "EX:"+e.message}})()`)
  return r
}
console.log('start      :', await getMode())
await clickNav('\u7801\u5b57')
console.log('after writing:', await getMode())
await clickNav('\u9879\u76ee')
console.log('after projects:', await getMode())
await clickNav('\u8bbe\u5b9a\u5e93')
console.log('after library:', await getMode())
ws.close(); process.exit(0)
