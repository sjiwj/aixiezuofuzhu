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

// 精确点 BUTTON.z0mANW_panelRow
async function clickPanel(label) {
  const r = await ev('var bs=Array.from(document.querySelectorAll("button.z0mANW_panelRow"));var t=bs.find(function(x){return (x.textContent||"").trim()==="' + label + '";});if(t){t.click();"ok"}else{"not found: "+bs.map(function(x){return (x.textContent||"").trim();}).join(",")}');
  return r;
}

for (const label of ["项目", "设定库", "拆书库", "码字"]) {
  const clicked = await clickPanel(label);
  await new Promise(r2 => setTimeout(r2, 2500));
  const info = await ev('var m=document.querySelector(".nvl-split__main")||document.querySelector(".nvl-pane")||document.querySelector("[class*=split]");var txt=m?m.innerText:"";JSON.stringify({api:document.body.dataset.activePanel||"",len:txt.length,head:txt.slice(0,40)})');
  console.log("  " + label + "  click=" + clicked + "  " + info);
}

ws.close();
process.exit(0);
