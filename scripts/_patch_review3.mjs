
import fs from 'node:fs'
const p = 'D:/NovelApp/plugin/lib/src/parts/070-body.js'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('stopReview = useCallback')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)
const T = (n) => '\t'.repeat(n)
const find = (frag, from) => { for (let i = from || 0; i < L.length; i++) if (L[i].includes(frag)) return i; return -1 }

// G. stopReview 定义（插在 start 的 useCallback 结束之后）
const startIdx = find('const start = useCallback(async function () {')
if (startIdx < 0) throw new Error('start')
// start 结束：从其内部找 }, [ 开头的行（依赖数组）
let end = -1
for (let k = startIdx; k < startIdx + 90; k++) {
  const t = (L[k] || '').trim()
  if (t.startsWith('}, [')) { end = k; break }
}
if (end < 0) throw new Error('start end')
const stopFn = [
  '',
  T(3) + 'const stopReview = useCallback(function () {',
  T(4) + 'if (acRef.current) { try { acRef.current.abort(); } catch (e) { /* ignore */ } acRef.current = null; }',
  T(4) + 'setStatus("idle");',
  T(4) + 'setError("已停止：这次审稿没跑完，已经出来的意见留在上面（不扣未产生的费用）");',
  T(3) + '}, []);',
]
L.splice(end + 1, 0, ...stopFn)
console.log('G ok after', end + 1)

// H. head 停止按钮（在「开始审稿」按钮之前）
const startBtn = find('title: canReview ? "" : (stageHint || "这一章现在不能审") }, "开始审稿")')
if (startBtn < 0) throw new Error('start button')
L.splice(startBtn, 0,
  T(5) + 'status === "running" ? h("button", { className: "nvl-btn", onClick: stopReview, title: "停止这次审稿（已出的意见保留）" }, "停止") : null,'
)
console.log('H ok', startBtn + 1)

fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('WROTE G/H')
