const list = await fetch("http://127.0.0.1:9690/json").then(r => r.json()).catch(() => null);
if (!list) { console.log("no cdp"); process.exit(1); }
const pageId = list[0].webSocketDebuggerUrl.split("/").pop();
const ws = new WebSocket("ws://127.0.0.1:9690/devtools/page/" + pageId);
let id = 0;
const pending = new Map();
const errs = [];
const send = (m, p) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
ws.addEventListener("message", e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") {
    errs.push((m.params.args||[]).map(a=>String(a.value||a.description||"")).join(" ").slice(0,120));
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

const labels = ["项目", "码字", "设定库", "拆书库", "审稿"];
for (let i = 0; i < labels.length; i++) {
  const label = labels[i];
  errs.length = 0;
  const clicked = await ev('var bs=Array.from(document.querySelectorAll("button.z0mANW_panelRow"));var t=bs.find(function(x){return (x.textContent||"").trim()==="' + label + '";});if(t){t.click();"ok"}else{"no"}');
  await new Promise(r => setTimeout(r, 2500));
  const info = await ev('var m=document.querySelector(".nvl-pane")||document.querySelector(".nvl-split")||document.body;var txt=m.innerText||"";JSON.stringify({api:document.body.dataset.activePanel||"",len:txt.length})');
  const err = errs.length ? " ERR:" + errs[0].slice(0,60) : "";
  console.log("  " + label + " click=" + clicked + "  " + info + err);
}

ws.close();
process.exit(0);
