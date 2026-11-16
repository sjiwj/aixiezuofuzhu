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
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") {
    logs.push("[" + m.params.type + "] " + (m.params.args||[]).map(a=>String(a.value||a.description||"")).join(" ").slice(0,150));
  }
  if (m.method === "Runtime.exceptionThrown") {
    logs.push("[EXC] " + String((m.params.exceptionDetails.exception||{}).description||"").slice(0,150));
  }
});
await new Promise(res => ws.addEventListener("open", res));
await send("Runtime.enable");
await new Promise(r => setTimeout(r, 4000));

async function ev(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r && r.exceptionDetails) return "EXC";
  return r && r.result ? String(r.result.value) : "";
}

for (const label of ["项目", "码字", "设定库", "拆书库", "审稿"]) {
  logs.length = 0;
  await ev('var bs=Array.from(document.querySelectorAll("button.z0mANW_panelRow"));var t=bs.find(function(x){return (x.textContent||"").trim()==="' + label + '";});if(t)t.click();');
  await new Promise(r => setTimeout(r, 2500));
  const info = await ev('var m=document.querySelector(".nvl-pane")||document.querySelector(".nvl-split__main");var txt=m?m.innerText:"";JSON.stringify({api:document.body.dataset.activePanel||"",len:txt.length,head:txt.slice(0,35).replace(/\n/g," ")})');
  console.log("  " + label + "  " + info + (logs.length ? "  ERR:" + logs[0].slice(0,80) : ""));
}

ws.close();
process.exit(0);
