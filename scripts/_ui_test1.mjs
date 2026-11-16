
const list = await fetch("http://127.0.0.1:9620/json").then(r => r.json()).catch(() => null);
if (!list) { console.log("no cdp"); process.exit(1); }
const pageId = list[0].webSocketDebuggerUrl.split("/").pop();
const ws = new WebSocket("ws://127.0.0.1:9620/devtools/page/" + pageId);
let id = 0;
const pending = new Map();
const send = (m, p) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
ws.addEventListener("message", ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } });
await new Promise(res => ws.addEventListener("open", res));
await send("Runtime.enable");
await new Promise(r => setTimeout(r, 8000));

async function ev(e) {
  const r = await send("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true });
  if (r && r.exceptionDetails) return "EXC:" + (r.exceptionDetails.text || "").slice(0, 80);
  return r && r.result ? String(r.result.value) : "";
}

// 1. 进项目
console.log("1. 点项目: " + await ev('(function(){var b=Array.from(document.querySelectorAll("button,[role=button]")).find(function(x){return (x.textContent||"").trim()==="项目";});if(b){b.click();return "ok";}return "no";})()'));
await new Promise(r => setTimeout(r, 3000));

// 2. 项目面板头部按钮
console.log("2. 头部按钮: " + await ev('JSON.stringify(Array.from(document.querySelectorAll(".nvl-head__title")).map(function(x){return (x.textContent||"").trim();}).slice(0,3))'));
console.log("   按钮: " + await ev('(function(){var hs=Array.from(document.querySelectorAll(".nvl-head"));for(var i=0;i<hs.length;i++){var t=(hs[i].querySelector(".nvl-head__title")||{}).textContent||"";if(t==="项目"){return Array.from(hs[i].querySelectorAll("button")).map(function(b){return (b.textContent||"").trim();}).join(" / ");}}return "没找到项目头部";})()'));

// 3. 点「新建」看浮层
console.log("");
console.log("3. 点新建: " + await ev('(function(){var bs=Array.from(document.querySelectorAll("button"));var b=bs.find(function(x){return (x.textContent||"").trim()==="新建";});if(b){b.click();return "ok";}return "no";})()'));
await new Promise(r => setTimeout(r, 1500));
console.log("   浮层: " + await ev('JSON.stringify({modal:!!document.querySelector(".nvl-modal"), input:!!document.querySelector(".nvl-modal input"), text:(document.querySelector(".nvl-modal")||{}).innerText||""})'));

// 关闭浮层
await ev('(function(){var b=Array.from(document.querySelectorAll(".nvl-modal button"));var c=b.find(function(x){return (x.textContent||"").trim()==="取消";});if(c){c.click();return "ok";}return "no";})()');
await new Promise(r => setTimeout(r, 800));

// 4. 设定库
console.log("");
console.log("4. 点设定库: " + await ev('(function(){var b=Array.from(document.querySelectorAll("button,[role=button]")).find(function(x){return (x.textContent||"").trim()==="设定库";});if(b){b.click();return "ok";}return "no";})()'));
await new Promise(r => setTimeout(r, 3000));
console.log("   列表项: " + await ev('JSON.stringify(Array.from(document.querySelectorAll(".nvl-tree__chapter")).slice(0,5).map(function(x){return (x.textContent||"").replace(/\s+/g," ").trim().slice(0,30);}))'));

ws.close();
process.exit(0);
