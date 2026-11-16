const list = await (await fetch('http://127.0.0.1:9650/json/list')).json()
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0; const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')
const ev = async (x) => { const r = await call('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true }); if (r.result && r.result.exceptionDetails) return 'ERR:' + JSON.stringify(r.result.exceptionDetails).slice(0,200); return r.result && r.result.result && r.result.result.value }
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
// 直接测接口（页面内，带 token）
const out = await ev(`(async function(){
  try {
    var base = apiBase().replace(/\\/+$/, "");
    var tk = await nvlToken();
    var r = await fetch(base + "/api/debt?book=" + encodeURIComponent("\u957f\u751f\u5f53\u94fa") + "&chapter=008", { headers: tk ? {"X-Novelapp-Token": tk} : {} });
    var j = await r.json();
    return JSON.stringify({status: r.status, ok: j.ok, must: (j.must_touch||[]).length, summary: j.summary});
  } catch (e) { return "EX:" + e.message; }
})()`)
console.log('direct api =', out)
// 看码字面板当前有没有选中章节
console.log('editor path =', JSON.stringify(String(await ev('(function(){var p=document.querySelector(".nvl-editor__path");return p?p.textContent:"no-path-el"})()'))))
console.log('has editor =', await ev('document.querySelectorAll(".nvl-editor__bar").length'))
ws.close(); process.exit(0)
