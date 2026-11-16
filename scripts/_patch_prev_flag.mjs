
import fs from 'node:fs'
const p = 'D:/NovelApp/core/reviewers.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('prev_injected')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
// review_start / team_done 事件里补 prev_injected
s = s.split("'chars_injected': bool(cards_matched), 'map_injected': bool(map_text),").join(
  "'chars_injected': bool(cards_matched), 'map_injected': bool(map_text), 'prev_injected': bool(prev_text),")
s = s.split("'chars_injected': bool(cards_matched), 'map_injected': bool(map_text),").join(
  "'chars_injected': bool(cards_matched), 'map_injected': bool(map_text), 'prev_injected': bool(prev_text),")
fs.writeFileSync(p, s, 'utf8')
const n = (s.match(/prev_injected/g) || []).length
console.log('reviewers.py prev_injected count =', n)
