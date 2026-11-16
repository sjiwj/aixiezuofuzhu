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
await new Promise(r => setTimeout(r, 5000));
const r = await send("Runtime.evaluate", { expression: "(function(){var b=document.body.innerText;return JSON.stringify({go:b.indexOf(\"去\u300c\u9879\u76ee\u300d\u91cc\u5199\")>=0, polish:b.indexOf(\"\u6da6\u8272\")>=0, tabs:Array.from(document.querySelectorAll(\".nvl-dock__tab\")).map(function(x){return (x.textContent||\"\").trim();})})})()", returnByValue: true });
console.log(r.result.value);
ws.close();
process.exit(0);
