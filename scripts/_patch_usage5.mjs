
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
const eol = s.includes('\r\n') ? '\r\n' : '\n'
let L = s.split(eol)

// 1) 删掉插错位置的段（_polish 的 send 里 6 行）
let removed = 0
for (let i = 0; i < L.length; i++) {
  if (L[i].includes("if isinstance(ev, dict) and ev.get('type') == 'team_done':")) {
    // 该块应为 6 行：if / try / log / except / pass / 结束
    if ((L[i + 3] || '').includes('except Exception:') && (L[i + 5] || '').trim() !== '') {
      L.splice(i, 6)
      removed++
      break
    }
  }
}
fs.writeFileSync(p, L.join(eol), 'utf8')
console.log('removed misplaced block:', removed)

// 2) 在审稿循环里加记账
s = fs.readFileSync(p, 'utf8')
const target = [
  "                                   cfg_override=cfg_override):",
  "                self.wfile.write(('data: ' + json.dumps(ev, ensure_ascii=False) + '\\n\\n').encode('utf-8'))",
].join(eol)
if (!s.includes(target)) throw new Error('review loop anchor')
const neu = [
  "                                   cfg_override=cfg_override):",
  "                if isinstance(ev, dict) and ev.get('type') == 'team_done':",
  "                    try:",
  "                        _t = ev.get('totals') or {}",
  "                        log_usage('review', book, chapter, {'total_tokens': _t.get('tokens'), 'total_cny': _t.get('cny')})",
  "                    except Exception:",
  "                        pass",
  "                self.wfile.write(('data: ' + json.dumps(ev, ensure_ascii=False) + '\\n\\n').encode('utf-8'))",
].join(eol)
s = s.split(target).join(neu)
fs.writeFileSync(p, s, 'utf8')
console.log('review logging inserted')
