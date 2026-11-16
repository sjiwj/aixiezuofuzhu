
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('/api/file/rename')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

const routeOld = "            elif u.path == '/api/file/delete':" + eol + "                self._delete_file(data)"
const routeNew = [
  "            elif u.path == '/api/file/delete':",
  "                self._delete_file(data)",
  "            elif u.path == '/api/file/rename':",
  "                self._rename_file(data)",
].join(eol)
if (!s.includes(routeOld)) throw new Error('route')
s = s.split(routeOld).join(routeNew)

const anchor = "    # POST /api/file/delete {path} —— 只允许删「章节」里的正文"
const method = [
  "    # POST /api/file/rename {path, to} —— 同目录改名（章节错别字更正）",
  "    def _rename_file(self, data):",
  "        norm, full = safe_rel(data.get('path', ''), need_ext=ALLOWED_EXT)",
  "        if not os.path.isfile(full):",
  "            self._json({'ok': False, 'error': 'not found', 'path': norm}, 404)",
  "            return",
  "        to = str(data.get('to') or '').strip()",
  "        if not to:",
  "            self._json({'ok': False, 'error': '新名字不能为空'}, 400)",
  "            return",
  "        if '/' in to or chr(92) in to or to in ('.', '..'):",
  "            self._json({'ok': False, 'error': '新名字里不能带路径'}, 400)",
  "            return",
  "        if not to.lower().endswith('.md'):",
  "            to = to + '.md'",
  "        target = os.path.join(os.path.dirname(full), to)",
  "        if _canon(target) != _canon(full) and os.path.exists(target):",
  "            self._json({'ok': False, 'error': 'exists', 'to': to}, 200)",
  "            return",
  "        try:",
  "            os.rename(full, target)",
  "        except OSError as e:",
  "            self._json({'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}, 500)",
  "            return",
  "        new_rel = norm.rsplit('/', 1)[0] + '/' + to",
  "        # 章节状态跟着搬家：旧编号复位，新编号继承",
  "        try:",
  "            _b = ST.book_of_path(norm)",
  "            _old = ST.chapter_no(norm)",
  "            _new = ST.chapter_no(new_rel)",
  "            if _b and _old and _new and _old != _new:",
  "                _st = ST.get_stage(_b, _old) or 'draft'",
  "                ST.set_stage(_b, _new, _st, reason='章节已重命名', source='manual', action='confirm', force=True)",
  "                ST.set_stage(_b, _old, 'draft', reason='章节已重命名', source='manual', action='confirm', force=True)",
  "        except Exception:",
  "            pass",
  "        self._json({'ok': True, 'path': new_rel, 'from': norm, 'to': to}, 200)",
  "",
].join(eol)
if (!s.includes(anchor)) throw new Error('method anchor')
s = s.replace(anchor, method + anchor)
fs.writeFileSync(p, s, 'utf8')
console.log('server.py: +file/rename')
