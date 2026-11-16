// 前端面板冒烟：逐个点左侧面板，断言「真的切了、没崩、有内容」
// 用法:
//   node scripts/ui_smoke.mjs --port 9680
//   NOVELAPP_CDP_PORT=9680 node scripts/ui_smoke.mjs
// 需要 NovelApp 以 --remote-debugging-port=<port> 运行
import fs from 'node:fs'

function argPort() {
  const i = process.argv.indexOf('--port')
  if (i > 0 && process.argv[i + 1]) return process.argv[i + 1]
  return null
}
const PORT = argPort() || process.env.NOVELAPP_CDP_PORT || process.env.CDP_PORT || 9650

// [导航按钮文案, 期望 activePanel（frontend 钩子）, 特征词, 类型]
// 类型 panel = 切面板（要求文本变化）；dialog = 弹层（要求出现 role=dialog）
const PANELS = [
  ['项目', 'projects', ['项目'], 'panel'],
  ['码字', 'writing', ['码字', '正文', '汉字'], 'panel'],
  ['设定库', 'library', ['设定', '角色卡'], 'panel'],
  ['拆书库', 'breakdown', ['拆书', '书单'], 'panel'],
  ['审稿', 'review', ['审稿', '评'], 'panel'],
  ['设置', 'settings', ['设置'], 'dialog'],
]
const MIN_PANEL_CHARS = 20

const list = await (await fetch('http://127.0.0.1:' + PORT + '/json/list')).json().catch(() => null)
if (!list) { console.log('SKIP  no CDP on ' + PORT); process.exit(0) }
const page = list.find((t) => t.type === 'page')
if (!page) { console.log('SKIP  no page target'); process.exit(0) }
const ws = new WebSocket(page.webSocketDebuggerUrl)
let id = 0
const pending = new Map()
const exceptions = []
function call(m, p) { return new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: p || {} })) }) }
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params && m.params.exceptionDetails
    exceptions.push(((d && (d.text || (d.exception && d.exception.description))) || 'exception').slice(0, 160))
  }
  if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) }
})
await new Promise((r) => ws.addEventListener('open', r))
await call('Runtime.enable')

async function evaluate(expression) {
  const r = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (r.result && r.result.exceptionDetails) return null
  return r.result && r.result.result && r.result.result.value
}

const errsExpr = "(() => { const o = {}; Object.keys(window).forEach((k) => { if (/Err$/.test(k) && window[k]) o[k] = String(window[k]).slice(0, 120) }); return JSON.stringify(o) })()"
const textExpr = '(document.body.innerText || "").replace(/\\s+/g, " ")'
const panelExpr = '(document.body.dataset && document.body.dataset.activePanel) || null'

async function closeDialogs() {
  const open = await evaluate("!!document.querySelector('[role=dialog], [aria-modal=true], dialog[open]')")
  if (!open) return
  const closed = await evaluate("(() => { const d=[...document.querySelectorAll('button')].find(b=>(b.textContent||'').trim()==='关闭'); if (d) { d.click(); return 'clicked' } document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})); return 'esc' })()")
  await new Promise((r) => setTimeout(r, 500))
  return closed
}

await closeDialogs()               // 起始先关掉残留弹层
let fails = 0
let warns = 0
let prevText = null
for (const [name, expectPanel, expectWords, kind] of PANELS) {
  const clickExpr = "(() => { const b = [...document.querySelectorAll('button')].find((x) => (x.textContent || '').trim().startsWith(" + JSON.stringify(name) + ")); if (!b) return 'no-button'; b.click(); return 'clicked' })()"
  await closeDialogs()               // 弹层会拦住后面的面板点击
  const clicked = await evaluate(clickExpr)
  await new Promise((r) => setTimeout(r, 900))

  const errs = JSON.parse((await evaluate(errsExpr)) || '{}')
  const panel = await evaluate(panelExpr)
  const text = String((await evaluate(textExpr)) || '')
  const panelExceptions = exceptions.splice(0, exceptions.length)

  const keyword = expectWords.some((k) => text.includes(k))
  const rich = text.length >= MIN_PANEL_CHARS
  const isDialog = kind === 'dialog'
  const dialogOpen = await evaluate("!!document.querySelector('[role=dialog], [aria-modal=true], dialog[open]')")
  const differs = isDialog ? true : (prevText === null || text !== prevText)
  const hookOk = isDialog ? true : (panel === null ? null : panel === expectPanel)

  const ok = clicked === 'clicked' && Object.keys(errs).length === 0 && panelExceptions.length === 0
    && keyword && rich && differs && hookOk !== false && (!isDialog || dialogOpen)
  if (!ok) fails++
  if (hookOk === null) warns++

  console.log((ok ? 'PASS  ' : 'FAIL  ') + name.padEnd(4) +
    ' clicked=' + clicked +
    ' errs=' + JSON.stringify(errs) +
    ' exc=' + panelExceptions.length +
    ' keyword=' + keyword +
    ' chars=' + text.length +
    ' differs=' + differs + (isDialog ? ' dialog=' + dialogOpen : '') +
    ' panel=' + (panel === null ? 'HOOK-MISSING' : panel + (hookOk ? '' : '≠' + expectPanel)))
  if (!isDialog) prevText = text
}
await closeDialogs()               // 结束再关一次，别把弹层留给下一轮
console.log()
console.log('结果: ' + (PANELS.length - fails) + '/' + PANELS.length + ' PASS' +
  (warns ? '（' + warns + ' 项缺 data-active-panel 钩子，未强制）' : ''))
ws.close()
process.exit(fails ? 1 : 0)
