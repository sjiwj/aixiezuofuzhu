
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes("import tier as TIER")) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

// 1) model 解析处插入 tier 覆盖
const old = "        model = layer.get('model') or ''"
if (!s.includes(old)) throw new Error('model anchor')
const neu = [
  "        model = layer.get('model') or ''",
  "        # Step 2 重点章判定：卷末 / 黄金三章 换强模型（配置在 config/writing_tiers.json）",
  "        tier_name, tier_reason, tier_conf = 'normal', '', {}",
  "        try:",
  "            import tier as TIER",
  "            tier_name, tier_reason, tier_conf = TIER.resolve_tier(book, ch)",
  "            if tier_conf.get('model'):",
  "                model = tier_conf['model']",
  "        except Exception:",
  "            pass",
].join(eol)
s = s.replace(old, neu)

// 2) call_cfg 处带上 tier 的 thinking / max_tokens
const old2 = "        call_cfg = {'model': model, 'temperature': layer.get('temperature', 0.8)}"
if (!s.includes(old2)) throw new Error('call_cfg anchor')
const neu2 = [
  "        call_cfg = {'model': model, 'temperature': layer.get('temperature', 0.8)}",
  "        if tier_conf.get('max_tokens'):",
  "            call_cfg['max_tokens'] = int(tier_conf['max_tokens'])",
  "        if tier_conf.get('thinking') is True:",
  "            call_cfg['extra_body'] = {'thinking': {'type': 'enabled'}}",
].join(eol)
s = s.replace(old2, neu2)

// 3) send 定义之后发 tier 事件
const old3 = "        def send(ev):"
const idx = s.indexOf(old3, s.indexOf('def _write_stream'))
if (idx < 0) throw new Error('send def')
// 在 send 定义结束（return True/false 之后）插入——直接插在定义前，用 send 会未定义
// 改为：在「SSE 头已发完」之后、第一次调用 send 之前不易定位，简化：把 tier 事件挂在 done 事件里
const oldDone = "        send({'type': 'done', 'chars': len(body), 'added_chars': len(text), 'mode': mode,"
if (!s.includes(oldDone)) throw new Error('done event')
s = s.replace(oldDone, [
  "        if tier_name != 'normal':",
  "            send({'type': 'tier', 'tier': tier_name, 'reason': tier_reason, 'model': model})",
  oldDone,
].join(eol))
fs.writeFileSync(p, s, 'utf8')
console.log('server.py: +tier 覆盖 +tier 事件')
