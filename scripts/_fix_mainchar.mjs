
import fs from 'node:fs'
const p = 'D:/NovelApp/core/write_context.py'
let s = fs.readFileSync(p, 'utf8')
if (!s.includes("'甲' in n")) { console.log('ALREADY'); process.exit(0) }
const old = [
  "    main_state = None",
  "    for n, s in (states or []):",
  "        if '甲' in n or '主角' in n:",
  "            main_state = (n, s)",
  "            break",
].join('\n')
if (!s.includes(old)) throw new Error('main_state anchor')
const neu = [
  "    # 主角判定：先看「主角」标注，再退到状态表第一节（不认角色名，",
  "    # 否则换一本书就找不到主角——之前写死了某本书的主角名）",
  "    main_state = None",
  "    for n, s in (states or []):",
  "        if '主角' in n:",
  "            main_state = (n, s)",
  "            break",
  "    if not main_state and states:",
  "        main_state = states[0]",
].join('\n')
s = s.split(old).join(neu)
fs.writeFileSync(p, s, 'utf8')
console.log('write_context: 主角判定去硬编码')
