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
console.log('open settings:', await ev('(function(){var bs=[].slice.call(document.querySelectorAll("button,[role=button],a"));for(var i=0;i<bs.length;i++){var t=(bs[i].textContent||"").trim();if(t==="\u8bbe\u7f6e"){bs[i].click();return "ok"}}return "no"})()'))
await wait(2000)
console.log(JSON.stringify(await ev(`(function(){
  var out = {};
  ["浅色","深色","跟随系统","外观"].forEach(function(l){
    var els = [].slice.call(document.querySelectorAll("button,[role=button]")).filter(function(b){ return (b.textContent||"").trim() === l });
    if (!els.length) { out[l] = "no-el"; return; }
    var e = els[0], p = e.parentElement, gp = p ? p.parentElement : null;
    out[l] = { disp: getComputedStyle(e).display, parentDisp: p ? getComputedStyle(p).display : "", gpDisp: gp ? getComputedStyle(gp).display : "" };
  });
  return out;
})()`), null, 1))
const s = await call('Page.captureScreenshot', { format: 'png' })
if (s.result && s.result.data) { fs.writeFileSync('D:/NovelApp/_tmp/ui-settings.png', Buffer.from(s.result.data, 'base64')); console.log('shot saved') }
ws.close(); process.exit(0)
