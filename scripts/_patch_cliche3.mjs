
import fs from 'node:fs'
const p = 'D:/NovelApp/core/coordinator.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('cliche_ban_block')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

// 1) 函数：插在 WORKER_SYSTEM 之后
const anchor = "_SPECIAL_TOKEN_RE = re.compile("
if (!s.includes(anchor)) throw new Error('anchor')
const fn = [
  "def cliche_ban_block():",
  "    \"\"\"写作层禁令：词表来自 config/cliche.json —— 与质检 scripts/l1_l2_check.py 共用同一份，",
  "    改词表不用改代码，两处同时生效。\"\"\"",
  "    cands = [os.path.join(ROOT, 'config', 'cliche.json')]",
  "    try:",
  "        import coordinator as _self  # noqa: F401  (占位，避免循环导入问题)",
  "    except Exception:",
  "        pass",
  "    data = None",
  "    for p in cands:",
  "        try:",
  "            with open(p, encoding='utf-8-sig') as f:",
  "                data = json.load(f)",
  "            break",
  "        except Exception:",
  "            data = None",
  "    if not isinstance(data, dict):",
  "        return ''",
  "    groups = data.get('groups') or {}",
  "    if not groups:",
  "        return ''",
  "    lines = ['', '【这一章不许用的句式（质检会打回，写完自己先删干净）】']",
  "    idx = 0",
  "    for key, g in groups.items():",
  "        if not isinstance(g, dict):",
  "            continue",
  "        ph = [str(x) for x in (g.get('phrases') or [])][:14]",
  "        pats = list(g.get('patterns') or [])",
  "        standalone = [str(x) for x in (g.get('standalone') or [])][:8]",
  "        idx += 1",
  "        lines.append('%d. %s' % (idx, g.get('label') or key))",
  "        if ph:",
  "            lines.append('   禁用：' + '、'.join(ph))",
  "        if standalone:",
  "            lines.append('   不许单独成句：' + '、'.join(standalone))",
  "        if pats:",
  "            lines.append('   不许写这类比较：比之前/比刚才/比上次 + 重/轻/稳/平/强 之类')",
  "        hint = g.get('hint')",
  "        if hint:",
  "            lines.append('   换成：' + str(hint))",
  "    lines.append('总则：不许用短句互评（“稳”“我认”“行”）、不许用比较词代替具体刻度、')",
  "    lines.append('不许用“我记下了”代替动作。字数不够就补场面（环境/动作/物件），不要补评语。')",
  "    return '\\n'.join(lines)",
  "",
  "",
].join(eol)
s = s.replace(anchor, fn + anchor)

// 2) 注入：writing 层 system 之后
const inject = [
  "    system = layer.get('system') or WORKER_SYSTEM.get(key)",
  "    if key == 'writing':",
  "        _ban = cliche_ban_block()",
  "        if _ban:",
  "            system = ((system or '') + '\\n' + _ban).strip()",
].join(eol)
const oldInject = "    system = layer.get('system') or WORKER_SYSTEM.get(key)"
if (!s.includes(oldInject)) throw new Error('inject anchor')
s = s.replace(oldInject, inject)

fs.writeFileSync(p, s, 'utf8')
console.log('coordinator: +cliche_ban_block +writing 注入')
