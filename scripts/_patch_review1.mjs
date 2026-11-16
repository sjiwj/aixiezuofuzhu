
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('mergeReason')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)

function findLine(frag, from) {
  for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i
  return -1
}

// A. streamReview 支持 signal
let i = findLine('async function streamReview(path, mode, handlers, extra) {')
if (i < 0) throw new Error('streamReview sig')
L[i] = L[i].replace('handlers, extra)', 'handlers, extra, signal)')
let j = findLine('"/api/review/run", body, handlers, null)', i)
if (j < 0) throw new Error('streamReview call')
L[j] = L[j].replace('handlers, null)', 'handlers, signal || null)')
console.log('A ok', i + 1, j + 1)

// B. 文件级：fmtGateItem + mergeReason（放 GATE_TEXT 之后）
i = findLine('const GATE_TEXT = { pass: "门禁通过"')
if (i < 0) throw new Error('GATE_TEXT')
const helpers = [
  '',
  T(2) + '/* 门禁明细里可能是字符串也可能是 {id, reason} 对象 —— 直接 join 会渲染成 [object Object] */',
  T(2) + 'function fmtGateItem(x) {',
  T(3) + 'if (x == null) return "";',
  T(3) + 'if (typeof x === "string") return x;',
  T(3) + 'if (typeof x === "number" || typeof x === "boolean") return String(x);',
  T(3) + 'return String(x.message || x.reason || x.name || x.id || "") || JSON.stringify(x);',
  T(2) + '}',
  '',
  T(2) + '/* 合并结论的「为什么」：投票分布 + 质量分 + 门禁 */',
  T(2) + 'function mergeReason(m, q, g) {',
  T(3) + 'const v = String((m && m.verdict) || "");',
  T(3) + 'const votes = (m && m.votes) || {};',
  T(3) + 'const drop = Number(votes.drop || 0)',
  T(3) + 'const keep = Number(votes.keep || 0)',
  T(3) + 'const failed = Number(votes.failed || 0)',
  T(3) + 'const total = Number(votes.reviewers || 0)',
  T(3) + 'const parts = [];',
  T(3) + 'if (v === "fail") parts.push("弃读 " + drop + " / 共 " + total + " 人，过半判弃读");',
  T(3) + 'else if (v === "pass") parts.push("追读 " + keep + " / 共 " + total + " 人，没有弃读票");',
  T(3) + 'else parts.push("意见分歧：弃读 " + drop + " / 追读 " + keep + (failed ? " / 未跑通 " + failed : ""));',
  T(3) + 'if (q && q.score != null) parts.push("质量分 " + q.score + "/" + (q.max != null ? q.max : "-"));',
  T(3) + 'if (g && g.status === "blocked") {',
  T(4) + 'const hits = (g.hits || []).map(function (x) { return fmtGateItem(x); }).filter(Boolean);',
  T(4) + 'parts.push("门禁拦截" + (hits.length ? "：" + hits.join("；") : ""));',
  T(3) + '} else if (g && g.status === "warn") parts.push("门禁有警告");',
  T(3) + 'else if (g && g.status === "inconclusive") parts.push("门禁未定（" + (g.checked != null ? g.checked : "-") + "/" + (g.total != null ? g.total : "-") + "）");',
  T(3) + 'return parts.join("；");',
  T(2) + '}',
]
L.splice(i + 1, 0, ...helpers)
console.log('B ok after', i + 1)

// C. GateBar 明细对象化
i = findLine('if (passed.length) rows.push(["通过", passed.join("、")]);')
if (i < 0) throw new Error('gate rows')
L[i] = T(3) + 'if (passed.length) rows.push(["通过", passed.map(fmtGateItem).join("、")]);'
L[i + 1] = T(3) + 'if (warned.length) rows.push(["警告", warned.map(fmtGateItem).join("、")]);'
L[i + 2] = T(3) + 'if (blocked.length) rows.push(["拦截", blocked.map(fmtGateItem).join("、")]);'
L[i + 3] = T(3) + 'if (skipped.length) rows.push(["跳过", skipped.map(fmtGateItem).join("；")]);'
console.log('C ok', i + 1)

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE A/B/C')
