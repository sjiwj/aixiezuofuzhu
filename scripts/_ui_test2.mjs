
const list = await fetch("http://127.0.0.1:9620/json").then(r => r.json()).catch(() => null);
const pageId = list[0].webSocketDebuggerUrl.split("/").pop();
const ws = new WebSocket("ws://127.0.0.1:9620/devtools/page/" + pageId);
let id = 0;
const pending = new Map();
const send = (m, p) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
ws.addEventListener("message", ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } });
await new Promise(res => ws.addEventListener("open", res));
await send("Runtime.enable");
await new Promise(r => setTimeout(r, 4000));

async function ev(e) {
  const r = await send("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true });
  if (r && r.exceptionDetails) return "EXC";
  return r && r.result ? String(r.result.value) : "";
}

// 拆书库
console.log("1. 点拆书库: " + await ev('(function(){var b=Array.from(document.querySelectorAll("button,[role=button]")).find(function(x){return (x.textContent||"").trim()==="拆书库";});if(b){b.click();return "ok";}return "no";})()'));
await new Promise(r => setTimeout(r, 3000));
console.log("   列表: " + await ev('JSON.stringify(Array.from(document.querySelectorAll(".nvl-tree__chapter")).map(function(x){return (x.textContent||"").replace(/\s+/g," ").trim().slice(0,30);}))'));

// 点第一条
console.log("   点第一条: " + await ev('(function(){var it=document.querySelector(".nvl-tree__chapter");if(it){it.click();return "ok";}return "no";})()'));
await new Promise(r => setTimeout(r, 2500));
console.log("   预览: " + await ev('JSON.stringify({title:(document.querySelector(".nvl-head__title")||{}).textContent||"", hasContent:!!document.querySelector(".nvl-ai-reason"), bodyLen:((document.querySelector(".nvl-ai-reason")||{}).textContent||"").length})'));

// 设定库点一条看按钮
console.log("");
console.log("2. 回设定库: " + await ev('(function(){var b=Array.from(document.querySelectorAll("button,[role=button]")).find(function(x){return (x.textContent||"").trim()==="设定库";});if(b){b.click();return "ok";}return "no";})()'));
await new Promise(r => setTimeout(r, 2500));
console.log("   点第一条: " + await ev('(function(){var it=document.querySelector(".nvl-tree__chapter");if(it){it.click();return "ok";}return "no";})()'));
await new Promise(r => setTimeout(r, 2500));
console.log("   按钮: " + await ev('(function(){var hs=Array.from(document.querySelectorAll(".nvl-head"));for(var i=0;i<hs.length;i++){var bs=Array.from(hs[i].querySelectorAll("button"));if(bs.length){var ts=bs.map(function(b){return (b.textContent||"").trim();});if(ts.some(function(t){return t.indexOf("复制路径")>=0||t.indexOf("打开")>=0;})){return ts.join(" / ");}}}return "没找到";})()'));

ws.close();
process.exit(0);
