// K1 串书探针：换项目后，码字/设定库是否跟着换（ui_smoke 覆盖不到）
// 用法: node scripts/k1_probe.mjs --port 9650
const PORT = (() => { const i = process.argv.indexOf('--port'); return (i > 0 && process.argv[i + 1]) || process.env.NOVELAPP_CDP_PORT || '9650' })()

const list = await (await fetch('http://127.0.0.1:' + PORT + '/json/list')).json().catch(() => null)
if (!list) { console.log('SKIP no CDP on ' + PORT); process.exit(0) }
const page = list.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0
const pending = new Map()
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) }
})
await new Promise((r) => ws.addEventListener('open', r))
const call = (method, params) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params: params || {} })) })
await call('Runtime.enable')

async function ev(expression) {
  const r = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (r.result && r.result.exceptionDetails) return { __err: r.result.exceptionDetails.text }
  return r.result && r.result.result && r.result.result.value
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

const clickPanel = (name) => ev('(() => { const b = [...document.querySelectorAll("button")].find((x) => (x.textContent || "").trim().startsWith(' + JSON.stringify(name) + ')); if (!b) return "miss"; b.click(); return "ok" })()')
const clickBook = (name) => ev('(() => { const els = [...document.querySelectorAll(".nvl-tree__bookname")]; const el = els.find((e) => (e.textContent || "").trim().replace(/^[v>]\\s*/, "").startsWith(' + JSON.stringify(name) + ')); if (!el) return "miss"; el.click(); return "ok" })()')

async function snap(tag) {
  const s = await ev('(() => { const b = document.body.innerText || ""; return {'
    + 'currentBook: localStorage.getItem("novelapp.currentBook"),'
    + 'lastFile: localStorage.getItem("novelapp.lastFile"),'
    + 'panel: (document.body.dataset || {}).activePanel || null,'
    + 'headTitle: ([...document.querySelectorAll(".nvl-head__title")].map(e => (e.textContent || "").trim()) || []).slice(0, 3),'
    + 'headDim: ([...document.querySelectorAll(".nvl-head .nvl-dim")].map(e => (e.textContent || "").trim()) || []).slice(0, 3),'
    + 'picker: ([...document.querySelectorAll(".nvl-picker")].map(e => (e.textContent || "").trim()) || []).slice(0, 4),'
    + 'hasK1B: b.includes("K1B-独特标记") || b.includes("K1B-世界观-独特标记"),'
    + 'books: ([...document.querySelectorAll(".nvl-tree__bookname")].map(e => (e.textContent || "").trim()))'
    + '} })()')
  console.log(tag.padEnd(18) + JSON.stringify(s))
  return s
}

await clickPanel('项目'); await wait(900)
await snap('INIT/项目')

console.log('--- 切到 _K1B（有章节）---')
console.log('click _K1B =', await clickBook('_K1B')); await wait(1600)
await snap('after 项目点K1B')
await clickPanel('码字'); await wait(1000); await snap('码字面板')
await clickPanel('设定库'); await wait(1200); await snap('设定库面板')

console.log('--- 切到 _K1C（空书，无章节）---')
await clickPanel('项目'); await wait(900)
console.log('click _K1C =', await clickBook('_K1C')); await wait(1600)
await snap('after 项目点K1C')
await clickPanel('码字'); await wait(1000); await snap('码字面板')
await clickPanel('设定库'); await wait(1200); await snap('设定库面板')

console.log('--- 切回 <书名> ---')
await clickPanel('项目'); await wait(900)
console.log('click <书名> =', await clickBook('<书名>')); await wait(1600)
await snap('after 点<书名>')
await clickPanel('码字'); await wait(1000); await snap('码字面板')
await clickPanel('设定库'); await wait(1200); await snap('设定库面板')

ws.close()
process.exit(0)
