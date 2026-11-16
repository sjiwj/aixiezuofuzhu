
const list = await fetch("http://127.0.0.1:9630/json").then(r => r.json()).catch(() => null);
const pageId = list[0].webSocketDebuggerUrl.split("/").pop();
const ws = new WebSocket("ws://127.0.0.1:9630/devtools/page/" + pageId);
let id = 0;
const pending = new Map();
const send = (m, p) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
ws.addEventListener("message", ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } });
await new Promise(res => ws.addEventListener("open", res));
await send("Runtime.enable");
await new Promise(r => setTimeout(r, 3000));

async function ev(e) {
  const r = await send("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true });
  if (r && r.exceptionDetails) return "EXC";
  return r && r.result ? String(r.result.value) : "";
}

// 拆书库
await ev('(function(){var b=Array.from(document.querySelectorAll("button,[role=button]")).find(function(x){return (x.textContent||"").trim()==="拆书库";});if(b)b.click();})()');
await new Promise(r => setTimeout(r, 3000));
await ev('(function(){var it=document.querySelector(".nvl-tree__chapter");if(it)it.click();})()');
await new Promise(r => setTimeout(r, 2500));

console.log("=== 所有 .nvl-head__title ===");
console.log(await ev('JSON.stringify(Array.from(document.querySelectorAll(".nvl-head__title")).map(function(x){return (x.textContent||"").trim();}))'));
console.log("");
console.log("=== 预览区结构 ===");
console.log(await ev('(function(){var main=document.querySelector(".nvl-split__main");if(!main)return "no main";var h=main.querySelector(".nvl-head__title");var pre=main.querySelector(".nvl-ai-reason");return JSON.stringify({title:(h||{}).textContent||"", len:((pre||{}).textContent||"").length, first50:((pre||{}).textContent||"").slice(0,50)});})()'));

ws.close();
process.exit(0);
