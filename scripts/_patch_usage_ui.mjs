
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('UsageSettingRow')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) 组件：插在 AboutSettingRow 之后
const ab = find('function AboutSettingRow() {')
if (ab < 0) throw new Error('about row')
let ae = -1
for (let k = ab; k < ab + 40; k++) { if ((L[k] || '').trim() === '}' && (L[k + 1] || '').trim() === '') { ae = k; break } }
if (ae < 0) throw new Error('about end')
const comp = [
  '',
  T(2) + '/* 设置 → 通用 → 用量与花费：读 data/usage.jsonl 的本机记账 */',
  T(2) + 'function UsageSettingRow() {',
  T(3) + 'const [busy, setBusy] = useState(false);',
  T(3) + 'const open = async function () {',
  T(4) + 'setBusy(true);',
  T(4) + 'const r = await api("/api/usage/summary?days=30");',
  T(4) + 'setBusy(false);',
  T(4) + 'const d = (r && r.data) || {};',
  T(4) + 'if (!r.ok || d.ok === false) { nvlInfo("用量与花费", "读取失败：" + ((d && d.error) || (r && r.error) || "未知")); return; }',
  T(4) + 'const fmt = function (o) { o = o || {}; return (o.calls || 0) + " 次 · " + (o.tokens || 0) + " tok · ¥" + Number(o.cny || 0).toFixed(4); };',
  T(4) + 'const kinds = Object.keys(d.by_kind || {}).map(function (k) { return "  " + k + "：" + fmt(d.by_kind[k]); });',
  T(4) + 'nvlInfo("用量与花费", [',
  T(5) + '"今天：" + fmt(d.today),',
  T(5) + '"本月：" + fmt(d.month),',
  T(5) + '"近 30 天：" + fmt(d.window),',
  T(5) + '"累计：" + fmt(d.total),',
  T(5) + '"",',
  T(5) + '"按类型（累计）："',
  T(4) + '].concat(kinds.length ? kinds : ["  （暂无记录）"]).concat([',
  T(5) + '"",',
  T(5) + '"说明：这是本机记账（data/usage.jsonl），只统计经过本软件的模型调用；余额以上面显示为准。"',
  T(4) + ']).join("\\n"));',
  T(3) + '};',
  T(3) + 'return h("div", { className: "nvl-setrow" },',
  T(4) + 'h("div", { className: "nvl-setrow__text" },',
  T(5) + 'h("div", { className: "nvl-setrow__title" }, "用量与花费"),',
  T(5) + 'h("div", { className: "nvl-setrow__desc" }, "今天 / 本月 / 累计的调用次数与花费（本机记账，不联网）")',
  T(4) + '),',
  T(4) + 'h("button", { className: "nvl-btn", onClick: open, disabled: busy }, busy ? "读取中…" : "查看")',
  T(3) + ');',
  T(2) + '}',
]
L.splice(ae + 1, 0, ...comp)
console.log('1) 组件 ok')

// 2) 注册：在 #about 注册块之后
const reg = find('safe("settings.general.item #about", function () {')
if (reg < 0) throw new Error('about register')
let regEnd = -1
for (let k = reg; k < reg + 14; k++) { if (L[k] === T(3) + '});') { regEnd = k; break } }
if (regEnd < 0) throw new Error('about register end')
const reg2 = [
  '',
  T(3) + 'safe("settings.general.item #usage", function () {',
  T(4) + 'return ctx.slots.inject("settings.general.item", function () {',
  T(5) + 'return ctx.slots.register({',
  T(6) + 'name: "settings.general.item",',
  T(6) + 'id: "novel-usage-setting",',
  T(6) + 'order: 53',
  T(5) + '}, UsageSettingRow);',
  T(4) + '});',
  T(3) + '});',
]
L.splice(regEnd + 1, 0, ...reg2)
console.log('2) 注册 ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE usage row')
