
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('setInjected')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// 1) 门禁文案：inconclusive -> 门禁未启用；note 补人话
let i = find('const GATE_TEXT = { pass: "门禁通过"')
if (i < 0) throw new Error('gate text')
L[i] = T(2) + 'const GATE_TEXT = { pass: "门禁通过", warn: "门禁警告", blocked: "门禁拦截", inconclusive: "门禁未启用" };'
i = find('const note = err || (!configured ? "门禁未配置：敏感词表 / 事实核对项为空" : "");')
if (i < 0) throw new Error('gate note')
L.splice(i, 1,
  T(3) + 'const allSkippedUnconfigured = skipped.length > 0 && skipped.every(function (x) { const s2 = fmtGateItem(x); return s2.indexOf("未配置") >= 0 || s2.indexOf("没有自动核对器") >= 0; });',
  T(3) + 'const note = err || (!configured ? "门禁未配置：敏感词表 / 事实核对项为空" : (st === "inconclusive" && allSkippedUnconfigured ? "这次没做机械检查：没配置敏感词表和核对规则" : ""));'
)
console.log('gate text ok')

// 2) injected state
i = find('const [gateOpen, setGateOpen] = useState(false);')
if (i < 0) throw new Error('gateOpen')
L.splice(i + 1, 0, T(3) + 'const [injected, setInjected] = useState(null);')

// 3) review_start 记录
i = find('const list = ev.reviewers || ev.team || ev.roster || [];', find('const start = useCallback'))
if (i < 0) throw new Error('review_start list')
L.splice(i + 1, 0,
  T(5) + 'setInjected({ chars: !!ev.chars_injected, map: !!ev.map_injected, prev: !!ev.prev_injected, states: Array.isArray(ev.state_chars) ? ev.state_chars : [], ledgers: ev.ledgers || {} });'
)
console.log('injected state ok')

// 4) 渲染：放在 GateBar 之后
i = find('onToggle: function () { setGateOpen(function (v) { return !v; }); }', find('function ReviewPanel'))
if (i < 0) throw new Error('gate bar render')
let close = i
for (let k = i; k < i + 4; k++) { if ((L[k] || '').trim() === '}),') { close = k; break } }
L.splice(close + 1, 0,
  T(6) + 'injected ? h("div", { className: "nvl-review__hint", style: { padding: "2px 14px 8px" } }, "本次带上的资料：" + [',
  T(7) + '"角色卡 " + (injected.chars ? "\u2713" : "\u2014"),',
  T(7) + '"世界地图 " + (injected.map ? "\u2713" : "\u2014"),',
  T(7) + '"上一章 " + (injected.prev ? "\u2713" : "\u2014"),',
  T(7) + '"角色状态 " + (injected.states && injected.states.length ? injected.states.length + " 人" : "\u2014"),',
  T(7) + '"账本 " + Object.keys(injected.ledgers || {}).length + " 个"',
  T(6) + '].join(" · ")) : null,'
)
console.log('render ok')

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE gate + injected')
