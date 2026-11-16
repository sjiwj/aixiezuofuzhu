
import fs from 'node:fs'
const p = 'D:/NovelApp/scripts/l3_l4_check.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes("('L3-items'")) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

s = s.replace('def coverage_l3_l4(l3_stats, days_found, season_stats, rules):',
              'def coverage_l3_l4(l3_stats, days_found, season_stats, rules, g3_stats=None):')

// 在 return coverage_of(checks) 之前插三条
const tail = '    return coverage_of(checks)'
const idx = s.lastIndexOf(tail)
if (idx < 0) throw new Error('coverage tail')
const add = [
  '    g3 = g3_stats or {}',
  '    if not g3.get("items_checked"):',
  '        checks.append(("L3-items", "skipped", "书里没有 设定库/角色状态.md 或没写「身上物品」"))',
  '    else:',
  '        checks.append(("L3-items", "checked", ""))',
  '    if not g3.get("realms"):',
  '        checks.append(("L3-power", "skipped", "书里没有 设定库/力量体系.md 或表格为空"))',
  '    else:',
  '        checks.append(("L3-power", "checked", ""))',
  '    if not g3.get("foreshadow"):',
  '        checks.append(("L3-foreshadow", "skipped", "书里没有 设定库/伏笔.md 或表格为空"))',
  '    else:',
  '        checks.append(("L3-foreshadow", "checked", ""))',
  '',
].join(eol)
s = s.slice(0, idx) + add + s.slice(idx)

// main 调用传参
s = s.replace('    coverage = coverage_l3_l4(l3_stats, days_found, season_stats, rules)',
              '    coverage = coverage_l3_l4(l3_stats, days_found, season_stats, rules, g3_stats)')

fs.writeFileSync(p, s, 'utf8')
console.log('coverage +3')
