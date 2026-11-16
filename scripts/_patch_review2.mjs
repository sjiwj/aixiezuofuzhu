
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('stopReview')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// D1. reviewer_done 存 text / verdict_label
let i = find('status: "done",', find('if (type === "reviewer_done")'))
if (i < 0) throw new Error('reviewer_done upsert')
const oldBlock = L.slice(i, i + 6).join('\n')
if (!oldBlock.includes('verdict: ev.verdict')) throw new Error('upsert body mismatch: ' + oldBlock)
// 直接给 upsert 对象加两个字段：找 verdict: ev.verdict 行
for (let k = i; k < i + 8; k++) {
  if (L[k] && L[k].includes('verdict: ev.verdict,')) {
    L[k] = L[k].replace('verdict: ev.verdict,', 'verdict: ev.verdict, verdictLabel: ev.verdict_label, text: ev.text || "",')
    break
  }
}
console.log('D1 ok')

// D2. 卡片：verdict 文案用后端标签 + 展开理由
i = find('VERDICT_TEXT[v] || String(r.verdict || "")')
if (i < 0) throw new Error('card verdict')
L[i] = L[i].replace('VERDICT_TEXT[v] || String(r.verdict || "")', 'r.verdictLabel || VERDICT_TEXT[v] || String(r.verdict || "")')
console.log('D2 ok', i + 1)

// D3. 卡片底部插入理由 details（在 r.issues 渲染之前）
i = find('(r.issues && r.issues.length)', find('const cards = reviewers.map'))
if (i < 0) throw new Error('card issues')
const why = [
  T(5) + '(r.text && String(r.text).trim())',
  T(6) + '? h("details", { className: "nvl-rev__why" },',
  T(7) + 'h("summary", null, "看它的理由（" + (r.verdictLabel || VERDICT_TEXT[v] || "") + "）"),',
  T(7) + 'h("pre", { className: "nvl-ai-reason", style: { maxHeight: "260px", overflow: "auto", borderBottom: "0", whiteSpace: "pre-wrap" } }, String(r.text)))',
  T(6) + ': null,',
]
L.splice(i, 0, ...why)
console.log('D3 ok', i + 1)

// E. 合并结论：门禁 skipped 对象 + 加「理由」行
i = find('g.skipped.join("；")')
if (i >= 0) { L[i] = L[i].replace('g.skipped.join("；")', 'g.skipped.map(fmtGateItem).join("；")'); console.log('E1 ok', i + 1) }
i = find('h("span", { className: "nvl-sum__k" }, "合并结论"),')
if (i < 0) throw new Error('sum row anchor')
// 在该行所属的 h("div", { className: "nvl-sum__row", key: "v" }, 之前插入「理由」行
let rowStart = i
for (let k = i; k > i - 6; k--) { if (L[k] && L[k].includes('nvl-sum__row')) { rowStart = k; break } }
const whyRow = [
  T(5) + 'h("div", { className: "nvl-sum__row", key: "why" },',
  T(6) + 'h("span", { className: "nvl-sum__k" }, "理由"),',
  T(6) + 'h("span", { className: "nvl-sum__v" }, mergeReason(m, q, g))',
  T(5) + '),',
]
L.splice(rowStart, 0, ...whyRow)
console.log('E2 ok', rowStart + 1)

// F. 停止审稿按钮 + abortRef
i = find('const [gateOpen, setGateOpen] = useState(false);')
if (i < 0) throw new Error('gateOpen state')
L.splice(i + 1, 0, T(3) + 'const acRef = useRef(null);')
i = find('setStatus("running");', find('const start = useCallback'))
if (i < 0) throw new Error('start running')
L.splice(i + 1, 0,
  T(4) + 'const ac = new AbortController();',
  T(4) + 'acRef.current = ac;')
i = find('const res = await streamReview(target, "vote", function (ev) {')
if (i < 0) throw new Error('streamReview call')
L[i] = L[i]  // 调用结束在后续行 }, ...); 需要改参数，找对应 "});" 行
// 找到 streamReview 调用结束：向后找 '}, ' 开头且含 ');' 的行
let end = -1
for (let k = i; k < i + 80; k++) { if ((L[k] || '').trim() === '});') { end = k; break } }
if (end < 0) throw new Error('streamReview close')
L[end] = T(4) + '}, null, ac.signal);'
console.log('F ok', i + 1, end + 1)

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE D/E/F')
