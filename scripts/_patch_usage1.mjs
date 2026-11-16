
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('def log_usage')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

// 1) 记账函数 + 汇总函数（插在 atomic_write 之前）
const anchor = "def atomic_write(full, content):"
if (!s.includes(anchor)) throw new Error('atomic_write anchor')
const fns = [
  "# ---------------- 用量记账（供「我的账号」聚合，网关 session 只对有账号的人有效） ----------------",
  "",
  "def _usage_path():",
  "    return os.path.join(DATA_ROOT, 'usage.jsonl')",
  "",
  "",
  "def log_usage(kind, book, chapter, billing, extra=None):",
  "    \"\"\"每次模型调用落一行到 data/usage.jsonl；失败只记日志，不影响主流程。\"\"\"",
  "    try:",
  "        rec = {",
  "            'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),",
  "            'kind': str(kind or ''),",
  "            'book': str(book or ''),",
  "            'chapter': str(chapter or ''),",
  "            'prompt_tokens': int((billing or {}).get('prompt_tokens') or 0),",
  "            'completion_tokens': int((billing or {}).get('completion_tokens') or 0),",
  "            'total_tokens': int((billing or {}).get('total_tokens') or 0),",
  "            'cny': round(float((billing or {}).get('total_cny') or (billing or {}).get('cny') or 0), 6),",
  "        }",
  "        if isinstance(extra, dict):",
  "            rec.update(extra)",
  "        with open(_usage_path(), 'a', encoding='utf-8') as f:",
  "            f.write(json.dumps(rec, ensure_ascii=False) + chr(10))",
  "        return rec",
  "    except Exception as e:",
  "        _log('用量记账失败：%s' % e)",
  "        return None",
  "",
  "",
  "def usage_summary(days=30):",
  "    \"\"\"读 usage.jsonl，聚合今天/本月/近 N 天/按类型。文件不存在返回空壳而不是报错。\"\"\"",
  "    p = _usage_path()",
  "    empty = {'ok': True, 'entries': 0, 'today': {'calls': 0, 'tokens': 0, 'cny': 0.0},",
  "             'month': {'calls': 0, 'tokens': 0, 'cny': 0.0},",
  "             'window': {'days': days, 'calls': 0, 'tokens': 0, 'cny': 0.0},",
  "             'total': {'calls': 0, 'tokens': 0, 'cny': 0.0},",
  "             'by_kind': {}, 'path': p}",
  "    if not os.path.exists(p):",
  "        return empty",
  "    today = time.strftime('%Y-%m-%d')",
  "    month = time.strftime('%Y-%m')",
  "    cutoff = time.time() - int(days) * 86400",
  "    out = dict(empty)",
  "    out['by_kind'] = {}",
  "    n = 0",
  "    try:",
  "        with open(p, encoding='utf-8', errors='replace') as f:",
  "            for line in f:",
  "                line = line.strip()",
  "                if not line:",
  "                    continue",
  "                try:",
  "                    r = json.loads(line)",
  "                except ValueError:",
  "                    continue",
  "                n += 1",
  "                ts = str(r.get('ts') or '')",
  "                tk = int(r.get('total_tokens') or 0)",
  "                cy = float(r.get('cny') or 0)",
  "                def bump(k):",
  "                    out[k]['calls'] += 1",
  "                    out[k]['tokens'] += tk",
  "                    out[k]['cny'] = round(out[k]['cny'] + cy, 6)",
  "                bump('total')",
  "                if ts[:10] == today:",
  "                    bump('today')",
  "                if ts[:7] == month:",
  "                    bump('month')",
  "                try:",
  "                    import calendar as _cal",
  "                    _ = _cal",
  "                    tstruct = time.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')",
  "                    if time.mktime(tstruct) >= cutoff:",
  "                        bump('window')",
  "                except Exception:",
  "                    pass",
  "                k = str(r.get('kind') or 'other')",
  "                b = out['by_kind'].setdefault(k, {'calls': 0, 'tokens': 0, 'cny': 0.0})",
  "                b['calls'] += 1",
  "                b['tokens'] += tk",
  "                b['cny'] = round(b['cny'] + cy, 6)",
  "    except OSError:",
  "        return empty",
  "    out['entries'] = n",
  "    return out",
  "",
  "",
].join(eol)
s = s.replace(anchor, fns + anchor)

// 2) 写章 usage 之后记账
const w = "                  'usage_estimated': bool(billing.get('usage_estimated'))})"
const wNew = [
  "                  'usage_estimated': bool(billing.get('usage_estimated'))})",
  "            log_usage('write', book, ch, billing)",
].join(eol)
if (!s.includes(w)) throw new Error('write usage anchor')
s = s.replace(w, wNew)
fs.writeFileSync(p, s, 'utf8')
console.log('server.py: +log_usage +usage_summary, 写章记账')
