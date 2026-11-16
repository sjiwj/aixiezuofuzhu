const list = await fetch("http://127.0.0.1:9690/json").then(r => r.json()).catch(() => null);
if (!list) { console.log("no cdp"); process.exit(1); }
const pageId = list[0].webSocketDebuggerUrl.split("/").pop();
const ws = new WebSocket("ws://127.0.0.1:9690/devtools/page/" + pageId);
let id = 0;
const pending = new Map();
const send = (m, p) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
ws.addEventListener("message", e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } });
await new Promise(res => ws.addEventListener("open", res));
await send("Runtime.enable");
await new Promise(r => setTimeout(r, 6000));

async function ev(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r && r.exceptionDetails) return "EXC:" + (r.exceptionDetails.text || "").slice(0, 60);
  return r && r.result ? String(r.result.value) : "";
}

// 关弹层
await ev('var ds=document.querySelectorAll(".nvl-modal");Array.from(ds).forEach(function(d){var b=d.querySelector("button");if(b)b.click();});ds.length');

const panels = ["项目", "码字", "设定库", "拆书库", "审稿"];
for (let i = 0; i < panels.length; i++) {
  const label = panels[i];
  await ev('var bs=Array.from(document.querySelectorAll("button,[role=button]"));var t=bs.find(function(x){return (x.textContent||"").trim()==="' + label + '";});if(t)t.click();');
  await new Promise(r => setTimeout(r, 2000));
  const info = await ev('var m=document.querySelector(".nvl-split__main")||document.querySelector(".nvl-pane");var txt=m?m.innerText:"";JSON.stringify({api:document.body.dataset.activePanel||"",len:txt.length,head:txt.slice(0,40)})');
  console.log("  " + label + "  " + info);
}

ws.close();
process.exit(0);
