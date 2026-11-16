
import fs from 'node:fs'
const p = 'D:/NovelApp/scripts/l3_l4_check.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('stale_after')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

s = s.replace('def check_foreshadow(text, chapter_path):', 'def check_foreshadow(text, chapter_path, stale_after=5):')
s = s.replace('        if buried and ch_no and (ch_no - buried) >= 5:', '        if buried and ch_no and (ch_no - buried) >= stale_after:')
s = s.replace('def check_gate3(text, chapter_path):', 'def check_gate3(text, chapter_path, cfg=None):')
s = s.replace('    i3, s3 = check_foreshadow(text, chapter_path)',
              '    g3cfg = (cfg or {}).get("gate3") or {}\n    i3, s3 = check_foreshadow(text, chapter_path, int(g3cfg.get("foreshadow_stale_after", 5) or 5))')
s = s.replace('    g3_issues, g3_stats = check_gate3(text, path)',
              '    g3_issues, g3_stats = check_gate3(text, path, rules)')
fs.writeFileSync(p, s, 'utf8')
console.log('stale_after configurable')
