const list = await fetch("http://127.0.0.1:9700/json").then(r => r.json()).catch(() => null);
if (!list) { console.log("no cdp"); process.exit(1); }
const pageId = list[0].webSocketDebuggerUrl.split("/").pop();
const ws = new WebSocket("ws://127.0.0.1:9700/devtools/page/" + pageId);
let id = 0;
const pending = new Map();
const send = (m, p) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
ws.addEventListener("message", e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } });
await new Promise(res => ws.addEventListener("open", res));
await send("Runtime.enable");
await new Promise(r => setTimeout(r, 5000));

async function ev(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r && r.exceptionDetails) return "EXC";
  return r && r.result ? String(r.result.value) : "";
}

const labels = ["项目", "码字", "设定库", "拆书库", "审稿"];
for (let i = 0; i < labels.length; i++) {
  const label = labels[i];
  await ev('var bs=Array.from(document.querySelectorAll("button.z0mANW_panelRow"));var t=bs.find(function(x){return (x.textContent||"").trim()==="' + label + '";});if(t)t.click();');
  await new Promise(r => setTimeout(r, 2000));
  const info = await ev('var m=document.querySelector(".nvl-pane")||document.body;var txt=m.innerText||"";JSON.stringify({api:document.body.dataset.activePanel||"",len:txt.length})');
  console.log("  " + label + "  " + info);
}

console.log("");
console.log("=== 审稿面板头部 ===");
await ev('var bs=Array.from(document.querySelectorAll("button.z0mANW_panelRow"));var t=bs.find(function(x){return (x.textContent||"").trim()==="审稿";});if(t)t.click();');
await new Promise(r => setTimeout(r, 2500));
console.log(await ev('var h=document.querySelector(".nvl-head");return h?h.innerText.replace(/\n/g," | "):"(no head)"'));
console.log("");
console.log("=== Picker 数量 ===");
console.log(await ev('document.querySelectorAll(".nvl-picker").length'));

ws.close();
process.exit(0);
