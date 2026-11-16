const list = await fetch("http://127.0.0.1:9690/json").then(r => r.json()).catch(() => null);
const pageId = list[0].webSocketDebuggerUrl.split("/").pop();
const ws = new WebSocket("ws://127.0.0.1:9690/devtools/page/" + pageId);
let id = 0;
const pending = new Map();
const send = (m, p) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
ws.addEventListener("message", e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } });
await new Promise(res => ws.addEventListener("open", res));
await send("Runtime.enable");
await new Promise(r => setTimeout(r, 3000));

async function ev(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r && r.exceptionDetails) return "EXC:" + (r.exceptionDetails.text || "").slice(0, 80);
  return r && r.result ? String(r.result.value) : "";
}

// 找所有含「设定库」的可点元素
console.log("=== 含「设定库」的元素 ===");
console.log(await ev('JSON.stringify(Array.from(document.querySelectorAll("button,[role=button],[role=tab],a,div")).filter(function(x){return (x.textContent||"").trim()==="设定库";}).map(function(x){return {tag:x.tagName, cls:(x.className||"").toString().slice(0,40), role:x.getAttribute("role"), h:Math.round(x.getBoundingClientRect().height), w:Math.round(x.getBoundingClientRect().width)};}))'));

console.log("");
console.log("=== 含「拆书库」的元素 ===");
console.log(await ev('JSON.stringify(Array.from(document.querySelectorAll("button,[role=button],[role=tab],a,div")).filter(function(x){return (x.textContent||"").trim()==="拆书库";}).map(function(x){return {tag:x.tagName, cls:(x.className||"").toString().slice(0,40), role:x.getAttribute("role"), h:Math.round(x.getBoundingClientRect().height), w:Math.round(x.getBoundingClientRect().width)};}))'));

console.log("");
console.log("=== 当前 body.dataset ===");
console.log(await ev('JSON.stringify({api:document.body.dataset.activePanel||""})'));

ws.close();
process.exit(0);
