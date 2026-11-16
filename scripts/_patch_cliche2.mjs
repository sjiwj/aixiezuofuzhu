
import fs from 'node:fs'
const p = 'D:/NovelApp/scripts/l1_l2_check.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes("check_cliche(text, path, cfg)")) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

// 1) coverage：加 cliche 两条
const covOld = [
  "    if c2.get('dialogue_tag_max_consecutive') is None:",
  "        checks.append(('dialogue_tag', 'skipped', '缺少 dialogue_tag_max_consecutive 配置'))",
  "    else:",
  "        checks.append(('dialogue_tag', 'checked', ''))",
  "    return coverage_of(checks)",
].join(eol)
const covNew = [
  "    if c2.get('dialogue_tag_max_consecutive') is None:",
  "        checks.append(('dialogue_tag', 'skipped', '缺少 dialogue_tag_max_consecutive 配置'))",
  "    else:",
  "        checks.append(('dialogue_tag', 'checked', ''))",
  "    cl = cfg.get('cliche') or {}",
  "    groups = cl.get('groups') or {}",
  "    if not groups:",
  "        checks.append(('cliche', 'skipped', '缺少 config/cliche.json 或 groups 为空'))",
  "    else:",
  "        checks.append(('cliche', 'checked', ''))",
  "        win = int((cl.get('limits') or {}).get('cross_chapter_window', 5))",
  "        if chapter_path and prev_chapter_texts(chapter_path, win):",
  "            checks.append(('cliche_cross_chapter', 'checked', ''))",
  "        else:",
  "            checks.append(('cliche_cross_chapter', 'skipped', '这一章没有可比的上一章，跨章重复查不了'))",
  "    return coverage_of(checks)",
].join(eol)
if (!s.includes(covOld)) throw new Error('coverage anchor')
s = s.split(covOld).join(covNew)

// 2) coverage 函数签名加 chapter_path
s = s.replace('def coverage_l1_l2(text, cfg):', 'def coverage_l1_l2(text, cfg, chapter_path=None):')

// 3) main：合入 check_cliche
const mainOld = [
  "    l1, stat1 = check_l1(text, cfg)",
  "    l2, stat2 = check_l2(text, cfg)",
  "    all_issues = l1 + l2",
  "    stats = {**stat1, **stat2, 'root': BASE, 'rules': os.path.abspath(rules_path)}",
  "    coverage = coverage_l1_l2(text, cfg)",
].join(eol)
const mainNew = [
  "    l1, stat1 = check_l1(text, cfg)",
  "    l2, stat2 = check_l2(text, cfg)",
  "    l3, stat3 = check_cliche(text, path, cfg)",
  "    all_issues = l1 + l2 + l3",
  "    stats = {**stat1, **stat2, **stat3, 'root': BASE, 'rules': os.path.abspath(rules_path)}",
  "    coverage = coverage_l1_l2(text, cfg, path)",
].join(eol)
if (!s.includes(mainOld)) throw new Error('main anchor')
s = s.split(mainOld).join(mainNew)

fs.writeFileSync(p, s, 'utf8')
console.log('wired cliche into main + coverage')
