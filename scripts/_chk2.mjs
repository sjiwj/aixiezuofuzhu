const list = await fetch("http://127.0.0.1:9610/json").then(r => r.json()).catch(() => null);
if (!list) { console.log("no cdp"); process.exit(1); }
const pageId = list[0].webSocketDebuggerUrl.split("/").pop();
const ws = new WebSocket("ws://127.0.0.1:9610/devtools/page/" + pageId);
let id = 0;
const pending = new Map();
const send = (m, p) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
ws.addEventListener("message", ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } });
await new Promise(res => ws.addEventListener("open", res));
await send("Runtime.enable");
await new Promise(r => setTimeout(r, 6000));
const ev = async (e) => {
  const r = await send("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true });
  if (r && r.exceptionDetails) return "EXC";
  return r && r.result ? String(r.result.value) : "";
};
console.log("  左栏: " + await ev('Array.from(document.querySelectorAll("button,[role=button]")).filter(function(x){var t=(x.textContent||"").trim();return ["项目","码字","设定库","拆书库","审稿"].indexOf(t)>=0;}).map(function(x){return (x.textContent||"").trim();}).join(" / ")'));
console.log("  挂件 tabs: " + await ev('Array.from(document.querySelectorAll(".nvl-dock__tab")).map(function(x){return (x.textContent||"").trim();}).join(" / ")'));
console.log("  「去项目里写」还在吗: " + await ev('document.body.innerText.indexOf("去「项目」里写")>=0 ? "还在（应删）" : "已删 OK"'));
console.log("  版本号: " + await ev('(document.body.innerText.match(/v0\.\d+\.\d+/)||["未找到"])[0]'));
ws.close();
process.exit(0);
