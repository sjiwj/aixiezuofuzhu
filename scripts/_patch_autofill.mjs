
import fs from 'node:fs'
const p = 'D:/NovelApp/core/server.py'
let s = fs.readFileSync(p, 'utf8')
if (s.includes('自动补角色卡')) { console.log('ALREADY'); process.exit(0) }
const eol = s.includes('\r\n') ? '\r\n' : '\n'
const anchor = "                extras[key] = p"
if (!s.includes(anchor)) throw new Error('extras anchor')
const add = [
  "                extras[key] = p",
  "        # 调用方没传时自动补：角色卡 / 世界地图 / 上一章",
  "        # （时间线、力量体系、伏笔、角色状态由 reviewers.py 按章节路径自己找）",
  "        try:",
  "            _bk = ST.book_of_path(norm)",
  "            _cn = ST.chapter_no(norm)",
  "            _sd = os.path.join(PROJECTS, _bk, '设定库') if _bk else ''",
  "            if 'chars' not in extras and _sd:",
  "                _p = os.path.join(_sd, '角色卡.md')",
  "                if os.path.isfile(_p):",
  "                    extras['chars'] = _p",
  "            if 'map' not in extras and _sd:",
  "                _p = os.path.join(_sd, '世界地图.md')",
  "                if os.path.isfile(_p):",
  "                    extras['map'] = _p",
  "            if 'prev' not in extras and _bk and _cn:",
  "                _dir = os.path.join(PROJECTS, _bk, '章节')",
  "                _prev = ''",
  "                try:",
  "                    for _f in sorted(os.listdir(_dir)):",
  "                        if not _f.endswith('.md') or '.bak' in _f:",
  "                            continue",
  "                        _n = _f.split('-')[0]",
  "                        if _n.isdigit() and int(_n) < int(_cn):",
  "                            _prev = os.path.join(_dir, _f)",
  "                except OSError:",
  "                    _prev = ''",
  "                if _prev:",
  "                    extras['prev'] = _prev",
  "        except Exception:",
  "            pass",
].join(eol)
s = s.replace(anchor, add)
fs.writeFileSync(p, s, 'utf8')
console.log('server.py: 自动补 chars/map/prev')
