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
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
// 打开设置
await ev('(function(){var bs=[].slice.call(document.querySelectorAll("button,[role=button],a"));for(var i=0;i<bs.length;i++){if((bs[i].textContent||"").trim()==="\u8bbe\u7f6e"){bs[i].click();return "ok"}}return "no"})()')
await wait(2500)
console.log(JSON.stringify(await ev(`(function(){
  var out = [];
  [].slice.call(document.querySelectorAll("*")).forEach(function(e){
    if (e.children.length) return;
    var t = (e.textContent||"").trim();
    if (t === "外观" || t === "浅色" || t === "深色" || t === "跟随系统") {
      var r = e.getBoundingClientRect();
      var cs = getComputedStyle(e);
      var p = e.parentElement;
      out.push({ t:t, tag:e.tagName.toLowerCase(), cls:String(e.className||"").slice(0,30),
                 y:Math.round(r.y), h:Math.round(r.height), disp:cs.display,
                 pDisp: p ? getComputedStyle(p).display : "", pCls: p ? String(p.className||"").slice(0,30) : "" });
    }
  });
  return out;
})()`), null, 1))
const s = await call('Page.captureScreenshot', { format: 'png' })
if (s.result && s.result.data) { fs.writeFileSync('D:/NovelApp/_tmp/ui-set2.png', Buffer.from(s.result.data, 'base64')); console.log('shot saved') }
ws.close(); process.exit(0)
