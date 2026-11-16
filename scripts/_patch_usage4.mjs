
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('/api/usage/summary')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

// 1) 路由：插在 /api/qc 之前
const rOld = "            elif u.path == '/api/qc':"
const rNew = [
  "            elif u.path == '/api/usage/summary':",
  "                try:",
  "                    _days = int((q.get('days') or ['30'])[0] or 30)",
  "                except (TypeError, ValueError):",
  "                    _days = 30",
  "                self._json(usage_summary(_days), 200)",
  "            elif u.path == '/api/qc':",
].join(eol)
if (!s.includes(rOld)) throw new Error('qc route')
s = s.replace(rOld, rNew)

// 2) 审稿记账：iter_team 循环里 team_done 时记一笔
const loopOld = "            for ev in RV.iter_team(text, norm, mode=mode,"
if (!s.includes(loopOld)) throw new Error('iter_team')
// 在循环体内找 send 语句后插入（用 events 的 type 判断）
const sendOld = "                self.wfile.write(('data: ' + json.dumps(ev, ensure_ascii=False) + '\\n\\n').encode('utf-8'))"
const sendNew = [
  "                if isinstance(ev, dict) and ev.get('type') == 'team_done':",
  "                    try:",
  "                        _t = ev.get('totals') or {}",
  "                        log_usage('review', _b_rev, _ch_rev, {'total_tokens': _t.get('tokens'), 'total_cny': _t.get('cny')})",
  "                    except Exception:",
  "                        pass",
  sendOld,
].join(eol)
if (!s.includes(sendOld)) throw new Error('send anchor')
s = s.replace(sendOld, sendNew)
fs.writeFileSync(p, s, 'utf8')
console.log('server.py: +usage route + review 记账（需要 _b_rev/_ch_rev 变量）')
