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
await new Promise(r => setTimeout(r, 3000));
const ev = async (e) => {
  const r = await send("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true });
  if (r && r.exceptionDetails) return "EXC";
  return r && r.result ? String(r.result.value) : "";
};
// 点「项目」
console.log("点项目: " + await ev('(function(){var b=Array.from(document.querySelectorAll("button,[role=button]")).find(function(x){return (x.textContent||"").trim()==="项目";});if(b){b.click();return "ok";}return "no";})()'));
await new Promise(r => setTimeout(r, 3000));
console.log("挂件: " + await ev('JSON.stringify({dock:!!document.querySelector(".nvl-dock"), tabs:Array.from(document.querySelectorAll(".nvl-dock__tab")).map(function(x){return (x.textContent||"").trim();}), title:(document.querySelector(".nvl-dock__title")||{}).textContent||""})'));
// 点码字
console.log("点码字: " + await ev('(function(){var b=Array.from(document.querySelectorAll("button,[role=button]")).find(function(x){return (x.textContent||"").trim()==="码字";});if(b){b.click();return "ok";}return "no";})()'));
await new Promise(r => setTimeout(r, 3000));
console.log("码字区: " + await ev('JSON.stringify({ta:!!document.querySelector(".nvl-textarea"), len:((document.querySelector(".nvl-textarea")||{}).value||"").length, buttons:Array.from(document.querySelectorAll("button")).filter(function(x){var t=(x.textContent||"").trim();return t.indexOf("润色")>=0||t.indexOf("替换")>=0;}).map(function(x){return (x.textContent||"").trim();})})'));
ws.close();
process.exit(0);
