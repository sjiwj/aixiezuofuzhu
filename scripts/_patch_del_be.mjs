
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('/api/file/delete')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'

const routeOld = "            elif u.path == '/api/file/new':" + eol + "                self._new_file(data)"
const routeNew = [
  "            elif u.path == '/api/file/new':",
  "                self._new_file(data)",
  "            elif u.path == '/api/file/delete':",
  "                self._delete_file(data)",
  "            elif u.path == '/api/project/delete':",
  "                self._delete_project(data)",
].join(eol)
if (!s.includes(routeOld)) throw new Error('route anchor fail')
s = s.split(routeOld).join(routeNew)

const methodAnchor = "    def _chat(self, data):"
const methods = [
  "    # 删除：一律先进 data/.trash/<时间戳>/，客户后悔能捞回来",
  "    def _trash_dir(self):",
  "        stamp = time.strftime('%Y%m%d-%H%M%S')",
  "        d = os.path.join(DATA_ROOT, '.trash', stamp)",
  "        os.makedirs(d, exist_ok=True)",
  "        return d, stamp",
  "",
  "    # POST /api/file/delete {path} —— 只允许删「章节」里的正文",
  "    def _delete_file(self, data):",
  "        norm, full = safe_rel(data.get('path', ''), need_ext=ALLOWED_EXT)",
  "        if not os.path.isfile(full):",
  "            self._json({'ok': False, 'error': 'not found', 'path': norm}, 404)",
  "            return",
  "        if '/章节/' not in norm:",
  "            self._json({'ok': False, 'error': '只允许从「章节」里删除正文文件'}, 400)",
  "            return",
  "        try:",
  "            trash, stamp = self._trash_dir()",
  "            target = os.path.join(trash, norm.replace('/', os.sep))",
  "            os.makedirs(os.path.dirname(target), exist_ok=True)",
  "            shutil.move(full, target)",
  "        except Exception as e:",
  "            self._json({'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}, 500)",
  "            return",
  "        try:",
  "            _b = ST.book_of_path(norm)",
  "            _c = ST.chapter_no(norm)",
  "            if _b and _c:",
  "                ST.set_stage(_b, _c, 'draft', reason='文件已删除', source='manual', action='confirm', force=True)",
  "        except Exception:",
  "            pass",
  "        self._json({'ok': True, 'path': norm, 'trash': '.trash/' + stamp}, 200)",
  "",
  "    # POST /api/project/delete {name} —— 整本书移进 .trash",
  "    def _delete_project(self, data):",
  "        name = safe_name(data.get('name')).strip()",
  "        d = os.path.join(PROJECTS, name)",
  "        if not os.path.isdir(d):",
  "            self._json({'ok': False, 'error': 'not found', 'name': name}, 404)",
  "            return",
  "        try:",
  "            trash, stamp = self._trash_dir()",
  "            shutil.move(d, os.path.join(trash, name))",
  "        except Exception as e:",
  "            self._json({'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}, 500)",
  "            return",
  "        self._json({'ok': True, 'name': name, 'trash': '.trash/' + stamp}, 200)",
  "",
].join(eol)
if (!s.includes(methodAnchor)) throw new Error('method anchor fail')
s = s.replace(methodAnchor, methods + methodAnchor)
fs.writeFileSync(p, s, 'utf8')
console.log('server.py: +file/delete +project/delete')
