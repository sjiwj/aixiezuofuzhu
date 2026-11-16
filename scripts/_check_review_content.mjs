const list = await fetch("http://127.0.0.1:9700/json").then(r => r.json()).catch(() => null);
const pageId = list[0].webSocketDebuggerUrl.split("/").pop();
const ws = new WebSocket("ws://127.0.0.1:9700/devtools/page/" + pageId);
let id = 0;
const pending = new Map();
const send = (m, p) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
ws.addEventListener("message", e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } });
await new Promise(res => ws.addEventListener("open", res));
await send("Runtime.enable");
await new Promise(r => setTimeout(r, 3000));

async function ev(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r && r.exceptionDetails) return "EXC";
  return r && r.result ? String(r.result.value) : "";
}

// 审稿
await ev('var bs=Array.from(document.querySelectorAll("button.z0mANW_panelRow"));var t=bs.find(function(x){return (x.textContent||"").trim()==="审稿";});if(t)t.click();');
await new Promise(r => setTimeout(r, 2500));
console.log("=== 审稿面板全文 ===");
console.log(await ev('var m=document.querySelector(".nvl-pane");return m?m.innerText:"(no pane)"'));

console.log("");
console.log("=== 审稿的 Picker ===");
console.log(await ev('JSON.stringify(Array.from(document.querySelectorAll(".nvl-picker")).map(function(p){return {txt:(p.innerText||"").replace(/\n/g," ").slice(0,50), id:(p.id||"")};}))'));

// 拆书库
console.log("");
await ev('var bs=Array.from(document.querySelectorAll("button.z0mANW_panelRow"));var t=bs.find(function(x){return (x.textContent||"").trim()==="拆书库";});if(t)t.click();');
await new Promise(r => setTimeout(r, 2500));
console.log("=== 拆书库面板全文 ===");
console.log(await ev('var m=document.querySelector(".nvl-pane");return m?m.innerText:"(no pane)"'));

ws.close();
process.exit(0);
