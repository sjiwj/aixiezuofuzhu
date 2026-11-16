const list = await fetch("http://127.0.0.1:9690/json").then(r => r.json()).catch(() => null);
const pageId = list[0].webSocketDebuggerUrl.split("/").pop();
const ws = new WebSocket("ws://127.0.0.1:9690/devtools/page/" + pageId);
let id = 0;
const pending = new Map();
const logs = [];
const send = (m, p) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
ws.addEventListener("message", e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
  if (m.method === "Runtime.consoleAPICalled") {
    const args = (m.params.args || []).map(a => String(a.value || a.description || "")).join(" ");
    logs.push("[" + m.params.type + "] " + args.slice(0, 250));
  }
  if (m.method === "Runtime.exceptionThrown") {
    logs.push("[EXC] " + String((m.params.exceptionDetails.exception||{}).description||m.params.exceptionDetails.text||"").slice(0,250));
  }
});
await new Promise(res => ws.addEventListener("open", res));
await send("Runtime.enable");
await new Promise(r => setTimeout(r, 2000));

async function ev(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r && r.exceptionDetails) return "EXC:" + (r.exceptionDetails.text || "").slice(0, 80);
  return r && r.result ? String(r.result.value) : "";
}

console.log("=== 启动时 console 日志 ===");
logs.slice(-30).forEach(l => console.log("  " + l));
logs.length = 0;

console.log("");
console.log("=== 左栏有几个面板按钮 ===");
console.log(await ev('JSON.stringify(Array.from(document.querySelectorAll("button.z0mANW_panelRow")).map(function(x){return (x.textContent||"").trim();}))'));

console.log("");
console.log("=== 点设定库，看 console ===");
await ev('var bs=Array.from(document.querySelectorAll("button.z0mANW_panelRow"));var t=bs.find(function(x){return (x.textContent||"").trim()==="设定库";});if(t)t.click();');
await new Promise(r => setTimeout(r, 3000));
logs.slice(-15).forEach(l => console.log("  " + l));
console.log("  api=" + await ev('document.body.dataset.activePanel||"(空)"'));

ws.close();
process.exit(0);
