# -*- coding: utf-8 -*-
"""本地服务：给三栏界面提供 API

路由清单（详见 docs/API.md）：
  GET  /                      web/index.html
  GET  /api/tree              项目树
  GET  /api/file?path=        读文件（默认全量；可选 offset/limit 分块）
  GET  /api/config            读配置
  GET  /api/stats?path=       字数统计（文件 / 目录 / 全部 project）
  POST /api/chat              对话（SSE 流）
  POST /api/project           新建项目
  POST /api/save              保存文件（原子写 + 缩水保护）
  POST /api/file/new          新建文件（同名返回 exists）

写操作一律限制在 projects/ 下，.. 穿越 / 绝对路径 / 盘符 / 符号链接外逃全部拒绝。
"""
import json, os, re, shutil, sqlite3, subprocess, sys, tempfile, threading, time, webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, parse_qs

def _resolve_root():
    """PyInstaller frozen 时根目录 = exe 所在目录（web/config/scripts 被拷到旁边）；
    源码运行时 = core/ 的上一级。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


ROOT = _resolve_root()
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.join(ROOT, 'core'))
import coordinator as CO
import precheck_input                    # 第 2 保险：写前粗筛（区别于 precheck 的写后机检）
from errors import human, report          # v1.0.1 错误普通话化：界面只显示中文，原文进日志
import yamlite
import reviewers as RV
import stages as ST
import history as HI                     # 版本历史（快照 / diff / 回滚）
import shelf as SH                       # 冷冻架（弃坑设计）
import paid_gate as PG                   # 付费闸 + 本地账本（task-5，append-only）

CFG = CO.load_cfg()

def projects_root():
    """客户项目目录。优先级与插件 projectsRoot() 对齐：
    NOVELAPP_PROJECTS > NOVELAPP_DATA/projects > %APPDATA%/novelapp-desktop/data/projects > <ROOT>/projects
    """
    p = os.environ.get('NOVELAPP_PROJECTS')
    if p:
        return os.path.abspath(p)
    d = os.environ.get('NOVELAPP_DATA')
    if d:
        return os.path.join(os.path.abspath(d), 'projects')
    if os.environ.get('APPDATA'):
        return os.path.join(os.environ['APPDATA'], 'novelapp-desktop', 'data', 'projects')
    return os.path.join(ROOT, 'projects')


PROJECTS = projects_root()
DATA_ROOT = os.path.dirname(PROJECTS)   # 数据目录（projects 的父级）：对外相对路径的统一基准


def _rel_to_data(full):
    """绝对路径 -> 相对数据目录的 posix 路径（形如 projects/<书>/…）。
    客户数据在 %APPDATA%（C:）而程序在 D: 时，relpath 跨盘会抛 ValueError，
    这里退化成「路径末段以 projects/ 开头」的截取，绝不因为盘符不同就 500。"""
    try:
        rel = os.path.relpath(full, DATA_ROOT)
    except ValueError:
        norm = os.path.normpath(full).replace('\\', '/')
        idx = norm.find('/projects/')
        if idx >= 0:
            return norm[idx + 1:]
        return os.path.basename(norm)
    return rel.replace('\\', '/')


MAX_BODY = 16 * 1024 * 1024          # POST body 上限

# ==== SEC-GUARD-BEGIN（v1.0.1 N1/N2）====
# 入口防护：只认回环 Host、只认同源 Origin、写请求只收 JSON。
# 目的：挡住 DNS rebinding（假 Host 打到本机）与 CSRF（恶意站点跨站写文件）。
_LOOPBACK_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})
# 局域网 / 自定义部署才需要：set NOVELAPP_ALLOW_HOSTS=192.168.1.10,nas.local
_EXTRA_HOSTS = frozenset(
    h.strip().lower() for h in (os.environ.get('NOVELAPP_ALLOW_HOSTS') or '').split(',') if h.strip())
_WRITE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})
_SESSION_TOKEN = ''


def _host_key(raw):
    """Host 头 -> 纯主机名（小写、去端口、去 IPv6 方括号）。解析不了返回 ''。"""
    s = (raw or '').strip().lower()
    if not s:
        return ''
    if s.startswith('['):
        end = s.find(']')
        return s[1:end] if end > 0 else ''
    if s.count(':') == 1:
        s = s.rsplit(':', 1)[0]
    return s


def _allowed_host(name):
    return name in _LOOPBACK_HOSTS or name in _EXTRA_HOSTS


def _origin_same(origin, server_port):
    """Origin 是否同源：http(s) + 回环主机 + 本服务端口。Origin: null 一律拒。"""
    try:
        o = urlparse(origin)
    except Exception:
        return False
    scheme = (o.scheme or '').lower()
    if scheme not in ('http', 'https'):
        return False
    if not _allowed_host((o.hostname or '').lower()):
        return False
    port = o.port
    if port is None:
        port = 443 if scheme == 'https' else 80
    return port == server_port


def _session_token():
    """进程内随机令牌：没有 NOVELAPP_BACKEND_TOKEN 时用它给界面注入 chat 令牌。"""
    global _SESSION_TOKEN
    if not _SESSION_TOKEN:
        _SESSION_TOKEN = 'nvls-' + os.urandom(16).hex()
    return _SESSION_TOKEN
# ==== SEC-GUARD-END ====
MAX_SAVE_CHARS = 5_000_000           # 单文件写入上限（约 500 万字，超限明确报错，绝不静默截断）
ALLOWED_EXT = ('.md', '.txt', '.json')
SHRINK_GUARD = 0.5                   # 新内容不足原文件一半时需 force

_BAD_NAME = re.compile(r'[<>:"|?*\x00-\x1f/\\]')
_CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')


def _log(msg):
    """轻量日志：写 <data_dir>/logs/server.log；写不了就算了。"""
    try:
        base = CO.data_dir()
        d = os.path.join(base, 'logs')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'server.log'), 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + str(msg) + chr(10))
    except Exception as e:
        try:
            _lg = os.path.join(os.environ.get('NOVELAPP_DATA') or '', 'logs')
            os.makedirs(_lg, exist_ok=True)
            with open(os.path.join(_lg, 'prompt-log-error.log'), 'a', encoding='utf-8') as _f:
                _f.write('%s %s\n' % (type(e).__name__, e))
        except Exception:
            pass


def _peer_closed(conn):
    """客户端是否已断开。

    Windows 上两种情况都要覆盖：客户端正常关闭（FIN）与带未读数据关闭（RST）。
    select 对 RST 有时只标记 exceptional，所以这里直接做一次非阻塞 recv：
      - 返回 b''        → 对端已关（FIN）
      - 抛 BlockingIOError/WSAEWOULDBLOCK → 还活着
      - 抛其它 OSError  → 连接已坏（RST）
    """
    try:
        conn.setblocking(False)
    except Exception:
        return True
    try:
        data = conn.recv(1, 0x2)          # MSG_PEEK
        return data == b''
    except (BlockingIOError, InterruptedError):
        return False
    except OSError:
        return True
    finally:
        try:
            conn.setblocking(True)
        except Exception:
            pass


class ClientGone(Exception):
    """客户端已断开：SSE 写失败后抛出，用来立刻停流并跳过 commit。"""


class PathError(ValueError):
    """路径校验失败"""


# ---------------- 路径校验 ----------------

def _canon(p):
    r"""规范成可比较的绝对路径：解析符号链接 + 去掉 \\?\ 前缀 + 统一大小写。

    注意：realpath 会把 C:\temp 变成 C:\Temp（磁盘真实大小写），
    直接与 abspath 的结果比较会误判越界，所以两边都必须走这里。
    """
    rp = os.path.realpath(p)
    if rp.startswith('\\\\?\\'):
        rp = rp[4:]
    return os.path.normcase(os.path.abspath(rp))


def safe_rel(rel, need_ext=None):
    """把请求里的相对路径规范成 projects/ 下的 posix 相对路径，越界直接抛 PathError。"""
    if not isinstance(rel, str) or not rel.strip():
        raise PathError('path 不能为空')
    raw = rel.strip().replace('\\', '/')
    if '\x00' in raw:
        raise PathError('path 含 NUL')
    if raw.startswith('/') or re.match(r'^[A-Za-z]:', raw):
        raise PathError('禁止绝对路径')
    parts = [p for p in raw.split('/') if p not in ('', '.')]
    if any(p == '..' for p in parts):
        raise PathError('禁止 .. 穿越')
    norm = '/'.join(parts)
    if not norm:
        raise PathError('path 不能为空')
    if not (norm == 'projects' or norm.startswith('projects/')):
        raise PathError('路径必须在 projects/ 下')
    if need_ext and os.path.splitext(norm)[1].lower() not in need_ext:
        raise PathError('只允许 %s 文件' % '/'.join(need_ext))

    # norm 形如 projects/<书>/…：基准目录必须是「数据目录」（PROJECTS 的父级），
    # 不能是 ROOT（程序目录）——否则客户数据在 APPDATA 时每条路径都会被判越界。
    data_root = os.path.dirname(PROJECTS)
    full = os.path.abspath(os.path.join(data_root, norm))
    # realpath 解析符号链接/大小写后比较，防「外壳路径」逃逸到 projects/ 之外
    real_full = _canon(full)
    real_base = _canon(PROJECTS)
    if real_full != real_base and not real_full.startswith(real_base + os.sep):
        raise PathError('路径越界')
    return norm, full


def safe_name(name):
    """项目名校验：不能带路径分隔符和 Windows 非法字符。"""
    if not isinstance(name, str):
        raise PathError('name 必须是字符串')
    n = name.strip()
    if not n:
        raise PathError('name 不能为空')
    if len(n) > 40:
        raise PathError('name 太长（上限 40 字）')
    if _BAD_NAME.search(n):
        raise PathError('name 含非法字符（<>:"|?* / \\ 或控制符）')
    if n in ('.', '..') or n.startswith('.'):
        raise PathError('name 不能以 . 开头')
    return n


# ---------------- 树与统计 ----------------

def tree(path='projects', depth=3):
    """生成项目树"""
    p = os.path.join(DATA_ROOT, path)
    if not os.path.isdir(p):
        return []
    out = []
    for name in sorted(os.listdir(p)):
        if name.startswith('.'):
            continue
        full = os.path.join(p, name)
        rel = _rel_to_data(full)
        if os.path.isdir(full):
            out.append({'type': 'dir', 'name': name, 'path': rel,
                        'children': tree(rel, depth - 1) if depth > 0 else []})
        else:
            out.append({'type': 'file', 'name': name, 'path': rel,
                        'size': os.path.getsize(full)})
    return out


def stats_text(text):
    """字数口径：chars_cn=汉字数，chars_all=全文字符数，paragraphs=非空段数，lines=行数。"""
    if text == '':
        return {'chars_cn': 0, 'chars_all': 0, 'paragraphs': 0, 'lines': 0}
    lines = text.count('\n') + (0 if text.endswith('\n') else 1)
    paras = [p.strip() for p in re.split(r'\n[ \t]*\n', text)]
    return {'chars_cn': len(_CJK.findall(text)),
            'chars_all': len(text),
            'paragraphs': sum(1 for p in paras if p),
            'lines': lines}


def stats_path(full):
    """文件给文件统计，目录给递归合计。"""
    if os.path.isfile(full):
        with open(full, encoding='utf-8', errors='replace') as f:
            out = stats_text(f.read())
        out.update({'path': _rel_to_data(full), 'files': 1})
        return out
    if not os.path.isdir(full):
        raise PathError('路径不存在')
    total = {'chars_cn': 0, 'chars_all': 0, 'paragraphs': 0, 'lines': 0, 'files': 0}
    for dirpath, dirnames, files in os.walk(full):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for f in sorted(files):
            if not f.lower().endswith('.md'):
                continue
            try:
                with open(os.path.join(dirpath, f), encoding='utf-8', errors='replace') as fh:
                    st = stats_text(fh.read())
            except OSError:
                continue
            for k in ('chars_cn', 'chars_all', 'paragraphs', 'lines'):
                total[k] += st[k]
            total['files'] += 1
    total['path'] = _rel_to_data(full)
    return total


# ---------------- 项目脚手架 ----------------

def project_files(name, genre, author):
    genre = (genre or '未定').strip() or '未定'
    author = (author or '').strip()
    today = datetime.now().strftime('%Y-%m-%d')
    info = ['# %s' % name, '',
            '- 题材：%s' % genre,
            '- 作者：%s' % (author or '（待填）'),
            '- 状态：写作中',
            '- 创建：%s' % today,
            '- 当前进度：第 1 章', '']
    setting = {
        '力量体系.md': '# 力量体系\n\n（待填）\n\n| 境界 | 特征 | 战力 |\n|---|---|---|\n| | | |\n',
        '势力.md': '# 势力\n\n（待填）\n\n| 势力 | 立场 | 首领 | 与主角关系 |\n|---|---|---|---|\n| | | | |\n',
        '角色.md': '# 角色\n\n（待填）\n\n| 角色 | 身份 | 目标 | 与主角关系 |\n|---|---|---|---|\n| | | | |\n',
        '地点.md': '# 地点\n\n（待填）\n\n| 地点 | 归属 | 距主城 | 备注 |\n|---|---|---|---|\n| | | | |\n',
    }
    outline = {
        '全书大纲.md': '# %s · 全书大纲\n\n- 题材：%s\n- 主线：\n- 结局走向：\n' % (name, genre),
        '分卷大纲.md': '# %s · 分卷大纲\n\n## 第一卷\n\n- 起：\n- 承：\n- 转：\n- 合：\n' % name,
    }
    return info, setting, outline


def create_project(name, genre='', author=''):
    n = safe_name(name)
    root = os.path.join(PROJECTS, n)
    if os.path.exists(root):
        return None, 'exists'
    for sub in ('章节', '设定库', '大纲', 'reports'):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    info, setting, outline = project_files(n, genre, author)
    with open(os.path.join(root, '项目信息.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(info))
    for fn, body in setting.items():
        with open(os.path.join(root, '设定库', fn), 'w', encoding='utf-8', newline='\n') as f:
            f.write(body)
    for fn, body in outline.items():
        with open(os.path.join(root, '大纲', fn), 'w', encoding='utf-8', newline='\n') as f:
            f.write(body)
    return 'projects/' + n, None


# ---------------- 配置热重载（mtime 比对） ----------------
#
# 客户会直接改 config/coordinator.json（使用说明第八节就让他这么干），
# 但进程内的 CFG 是启动时读的，不改就永远旧值。这里在请求入口做一次
# 便宜的 stat 比对：mtime/size 变了才重读；读坏就保留旧配置 + 记日志。

CFG_LOCK = threading.Lock()
CFG_STATE = {'sig': None, 'error': None, 'reloads': 0, 'checked_at': None}


def _cfg_sig():
    try:
        st = os.stat(CFG_PATH)
    except OSError:
        return ('missing',)
    return (st.st_mtime_ns, st.st_size)


def _log_config(msg):
    try:
        os.makedirs(CO.LOG_DIR, exist_ok=True)
        with open(os.path.join(CO.LOG_DIR, 'config.log'), 'a', encoding='utf-8') as f:
            f.write('[%s] %s\n' % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg))
    except OSError:
        pass


def ensure_cfg_fresh(force=False):
    """请求入口调一次：文件变了才重读；读失败保留旧配置，绝不抛异常。"""
    global CFG
    sig = _cfg_sig()
    if not force and CFG_STATE['sig'] is not None and sig == CFG_STATE['sig']:
        return CFG
    with CFG_LOCK:
        # 拿到锁再确认一次，避免并发请求重复重载
        if not force and CFG_STATE['sig'] is not None and sig == CFG_STATE['sig']:
            return CFG
        if sig[0] == 'missing':
            CFG_STATE.update({'sig': sig, 'error': 'config_missing'})
            _log_config('配置文件不存在，继续使用内存里的旧配置')
            return CFG
        try:
            with open(CFG_PATH, encoding='utf-8-sig') as f:
                new = json.load(f)
            if not isinstance(new, dict):
                raise ValueError('顶层不是 JSON 对象')
        except Exception as e:
            CFG_STATE.update({'sig': sig, 'error': report(e)})
            _log_config('重载失败，保留旧配置：%s' % CFG_STATE['error'])
            return CFG
        CFG = new
        CFG_STATE.update({'sig': sig, 'error': None, 'reloads': CFG_STATE['reloads'] + 1,
                          'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        _log_config('已重载配置 model=%s endpoint=%s' % (
            (new.get('coordinator') or {}).get('model'),
            (new.get('coordinator') or {}).get('endpoint')))
        return CFG


def reload_cfg():
    """强制重载（save 之后、/api/config/reload 用）。"""
    return ensure_cfg_fresh(force=True)


# ---------------- 配置引导（setup） ----------------

SETUP_PROVIDERS = [
    {'id': 'deepseek', 'name': 'DeepSeek', 'endpoint': 'https://api.deepseek.com/v1',
     'model': 'deepseek-flash', 'key_url': 'https://platform.deepseek.com/api_keys',
     'note': '便宜，适合日常'},
    {'id': 'moonshot', 'name': 'Kimi', 'endpoint': 'https://api.moonshot.cn/v1',
     'model': 'kimi-k3', 'key_url': 'https://platform.moonshot.cn/console/api-keys',
     'note': '质量好，稍贵'},
    {'id': 'ollama', 'name': '本地 Ollama', 'endpoint': 'http://127.0.0.1:11434/v1',
     'model': 'qwen2.5:7b', 'api_key': 'ollama', 'note': '免费，需要先装 Ollama'},
]
CFG_PATH = os.path.join(ROOT, 'config', 'coordinator.json')
CFG_BAK = CFG_PATH + '.bak'
OLLAMA_TAGS = 'http://127.0.0.1:11434/api/tags'
# 明显不是真 key 的占位写法
_KEY_PLACEHOLDER = re.compile(r'(?i)^(x{3,}|sk-x+.*|your.*|placeholder|todo|changeme|change-me|none|null|test|demo|123+|\.\.\.)$')


def mask_key(k):
    """api_key 脱敏：只漏前 6 后 4，短 key 全遮。"""
    if not isinstance(k, str) or not k:
        return ''
    if len(k) <= 10:
        return '*' * len(k)
    return k[:6] + '*' * min(8, max(3, len(k) - 10)) + k[-4:]


def key_valid(k):
    """能不能用来真调模型：非空、非占位符、长度合理。"""
    if not isinstance(k, str):
        return False
    v = k.strip()
    if len(v) < 6:
        return False
    if _KEY_PLACEHOLDER.match(v):
        return False
    if 'x' * 6 in v.lower() and len(v) < 24:      # sk-xxxxxxxx 这类
        return False
    return True


def load_cfg_fresh():
    """每次现读，不走启动时缓存（save 之后要立刻生效）。"""
    try:
        with open(CFG_PATH, encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return {}


def save_search_enabled(enabled):
    """POST /api/settings/search —— 写 config/coordinator.json 的 search.enabled。

    联网搜索默认关闭（Bing RSS 只允许个人非商业用途），客户自己点开才写 true。
    只改 search 这一段，别的一律原样保留：读不到/读坏了就报错退出，绝不用一份空配置覆盖客户的。
    """
    cfg = load_cfg_fresh()
    if not isinstance(cfg, dict) or not cfg:
        return {'ok': False, 'error': 'config_unreadable',
                'hint': '读不到 %s，没有写入（先修好这个文件）' % CFG_PATH}
    cur = cfg.get('search')
    if not isinstance(cur, dict):
        cur = {}
    cur['enabled'] = bool(enabled)
    cfg['search'] = cur
    os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
    backup = None
    if os.path.exists(CFG_PATH):
        shutil.copy2(CFG_PATH, CFG_BAK)
        backup = CFG_BAK
    tmp = CFG_PATH + '.tmp~'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CFG_PATH)
    reload_cfg()                     # 立刻生效，不用重启进程
    return {'ok': True, 'enabled': bool(enabled), 'config_path': CFG_PATH, 'backup': backup}



# ---------------- 会话归档（2026-11-10）----------------
# DSH 把归档标记写在 data/storages/workspace.json 的 global.archivedSessionIds 里，
# 但它的界面只把归档会话藏起来，没有「显示已归档 / 恢复」的入口。这里补后端。
def _workspace_file():
    # 归档标记在数据目录下（projects 的父级），不是 resources 里
    return os.path.join(DATA_ROOT, 'storages', 'workspace.json')


def _read_workspace():
    p = _workspace_file()
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _session_title(sid):
    """标题从 KV 里捞；没有就用「会话 + 修改时间」。会话本体是 zstd，不在服务端解压。"""
    title, mt = '', 0.0
    fp = os.path.join(DATA_ROOT, 'storages', sid + '.json')
    try:
        with open(fp, encoding='utf-8') as f:
            blob = f.read()
        import re as _re
        m = _re.search(r'"title"\s*:\s*"([^"]{1,80})"', blob)
        if m:
            title = m.group(1)
        mt = os.path.getmtime(fp)
    except Exception:
        pass
    if not mt:
        # 会话目录：data/sessions/<workspace-key>/<sid>/session.v4.jsonl.zstd
        base = os.path.join(DATA_ROOT, 'sessions')
        try:
            for wsdir in os.listdir(base):
                cand = os.path.join(base, wsdir, sid, 'session.v4.jsonl.zstd')
                if os.path.isfile(cand):
                    mt = os.path.getmtime(cand)
                    break
        except OSError:
            pass
    if not title:
        import time as _t
        title = '会话 ' + (_t.strftime('%m-%d %H:%M', _t.localtime(mt)) if mt else sid[-6:])
    return title, mt


def list_sessions():
    ws = _read_workspace()
    if not ws:
        return {'ok': False, 'error': 'workspace.json 读不到'}
    g = ws.get('global') or {}
    arch = set(g.get('archivedSessionIds') or [])
    ids = []
    for w in (ws.get('tables') or {}).get('workspaces', {}).values():
        for sid in (w.get('sessionIds') or []):
            if sid not in ids:
                ids.append(sid)
    out = []
    for sid in ids:
        title, mt = _session_title(sid)
        out.append({'id': sid, 'title': title or sid[:8], 'archived': sid in arch,
                    'mtime': mt})
    out.sort(key=lambda r: r.get('mtime') or 0, reverse=True)
    return {'ok': True, 'sessions': out, 'archived': len(arch)}


def set_session_archived(sid, archived):
    ws = _read_workspace()
    if not ws:
        return {'ok': False, 'error': 'workspace.json 读不到'}
    sid = str(sid or '').strip()
    if not sid:
        return {'ok': False, 'error': 'id 不能为空'}
    g = ws.setdefault('global', {})
    cur = [x for x in (g.get('archivedSessionIds') or []) if x != sid]
    if archived:
        cur.append(sid)
    g['archivedSessionIds'] = cur
    p = _workspace_file()
    try:
        shutil.copy2(p, p + '.bak-arch')
    except OSError:
        pass
    tmp = p + '.tmp~'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(ws, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, p)
    return {'ok': True, 'id': sid, 'archived': bool(archived),
            'archived_count': len(cur)}

def save_agent_settings(data):
    """POST /api/settings/agent —— 写 config/coordinator.json 的 agent 段。

    只动白名单里的键（subagents / parallel_subagents），其余原样保留；
    同一套"读不到就别写"的保护，避免空配置覆盖客户文件。
    """
    data = data if isinstance(data, dict) else {}
    allowed = ('subagents', 'parallel_subagents', 'assistant_timeout')
    cfg = load_cfg_fresh()
    if not isinstance(cfg, dict) or not cfg:
        return {'ok': False, 'error': 'config_unreadable',
                'hint': '读不到 %s，没有写入（先修好这个文件）' % CFG_PATH}
    cur = cfg.get('agent')
    if not isinstance(cur, dict):
        cur = {}
    for k in allowed:
        if k in data:
            cur[k] = int(data[k]) if k == 'assistant_timeout' else bool(data.get(k))
    cfg['agent'] = cur
    os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
    backup = None
    if os.path.exists(CFG_PATH):
        shutil.copy2(CFG_PATH, CFG_BAK)
        backup = CFG_BAK
    tmp = CFG_PATH + '.tmp~'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CFG_PATH)
    reload_cfg()
    return {'ok': True, 'agent': cur, 'config_path': CFG_PATH, 'backup': backup}


def mask_cfg(cfg):
    """给前端看的配置：api_key 全部脱敏。"""
    out = json.loads(json.dumps(cfg or {}, ensure_ascii=False))
    co = out.get('coordinator')
    if isinstance(co, dict) and 'api_key' in co:
        co['api_key'] = mask_key(co.get('api_key'))
        co['api_key_set'] = bool((co.get('api_key') or '').strip())
    ws = out.get('workers')
    if isinstance(ws, dict):
        for name, w in ws.items():
            if isinstance(w, dict) and 'api_key' in w:
                w['api_key'] = mask_key(w.get('api_key'))
    return out


def probe_ollama(timeout=2.0):
    """探测本地 Ollama：/api/tags 拿模型列表，2 秒超时。"""
    info = {'detected': False, 'models': [], 'endpoint': OLLAMA_TAGS}
    t0 = time.time()
    try:
        with request.urlopen(OLLAMA_TAGS, timeout=timeout) as r:
            data = json.loads(r.read().decode('utf-8', 'replace'))
    except Exception as e:
        info['error'] = report(e, where='probe_ollama')
        info['ms'] = int((time.time() - t0) * 1000)
        return info
    models = []
    for m in (data.get('models') or []):
        if isinstance(m, dict):
            name = m.get('name') or m.get('model')
            if name:
                models.append(name)
    info.update({'detected': True, 'models': models[:50],
                 'count': len(models), 'ms': int((time.time() - t0) * 1000)})
    return info


def setup_status():
    ensure_cfg_fresh()                 # 先确保内存配置是最新的
    cfg = load_cfg_fresh()             # 磁盘上的（权威）
    co = cfg.get('coordinator') or {}
    rt = (CFG.get('coordinator') or {})
    return {
        'configured': key_valid(co.get('api_key')),
        'current': {
            'model': co.get('model') or '',
            'endpoint': co.get('endpoint') or '',
            'api_key': mask_key(co.get('api_key')),
            'api_key_set': bool((co.get('api_key') or '').strip()),
            'temperature': co.get('temperature'),
        },
        'providers': SETUP_PROVIDERS,
        'local_ollama': probe_ollama(),
        'runtime': {                    # 进程内存里真正在用的（模型调用看这个）
            'model': rt.get('model') or '',
            'endpoint': rt.get('endpoint') or '',
            'api_key': mask_key(rt.get('api_key')),
            'configured': key_valid(rt.get('api_key')),
            'in_sync': (rt.get('model') == co.get('model')
                        and rt.get('endpoint') == co.get('endpoint')),
        },
        'auto_reload': {                # 热重载状态：改完配置这里会跳
            'enabled': True,
            'reloads': CFG_STATE['reloads'],
            'last_error': CFG_STATE['error'],
            'checked_at': CFG_STATE['checked_at'],
        },
        'config_path': CFG_PATH,
        'has_backup': os.path.exists(CFG_BAK),
    }


def _clean_endpoint(ep):
    if not isinstance(ep, str):
        raise PathError('endpoint 必须是字符串')
    v = ep.strip().rstrip('/')
    if not re.match(r'^https?://[^\s/]+', v):
        raise PathError('endpoint 必须是 http:// 或 https:// 开头')
    return v


def _classify_http_error(e):
    """把上游 HTTP 错误翻译成前端能显示的分类。"""
    code = getattr(e, 'code', 0)
    try:
        raw = e.read()
    except Exception:
        raw = b''
    detail = ' '.join(raw[:400].decode('utf-8', 'replace').split()) if raw else ''
    low = detail.lower()
    if code in (401, 403):
        return {'error': 'unauthorized', 'http': code,
                'hint': 'api_key 无效、过期或没有该模型权限', 'detail': detail[:300]}
    if code == 404:
        return {'error': 'not_found', 'http': code,
                'hint': 'endpoint 路径不对（多数服务商要带 /v1）', 'detail': detail[:300]}
    if code == 400 and ('model' in low or 'not exist' in low or 'not found' in low):
        return {'error': 'model_not_found', 'http': code,
                'hint': 'endpoint 通了，但模型名不存在', 'detail': detail[:300]}
    if code == 429:
        return {'error': 'rate_limited', 'http': code,
                'hint': '请求太频繁或额度用尽', 'detail': detail[:300]}
    if code == 400:
        return {'error': 'bad_request', 'http': code,
                'hint': '请求被上游拒绝，看 detail', 'detail': detail[:300]}
    return {'error': 'http_%s' % code, 'http': code,
            'hint': '上游返回 %s' % code, 'detail': detail[:300]}


def setup_test(endpoint, api_key, model, timeout=15.0):
    """发一个最小 chat 请求验证连通性；错误分类：连不上 / 401 / 404 / 模型不存在 / 其它。"""
    ep = _clean_endpoint(endpoint)
    model = (model or '').strip()
    if not model:
        raise PathError('model 不能为空')
    key = (api_key or '').strip()
    if not key:
        if re.match(r'^https?://(127\.0\.0\.1|localhost)(:\d+)?', ep):
            key = 'ollama'                      # 本地服务通常不校验 key
        else:
            raise PathError('api_key 不能为空')

    body = {'model': model,
            'messages': [{'role': 'user', 'content': 'ping'}],
            'max_tokens': 5, 'temperature': 0, 'stream': False}
    req = request.Request(ep + '/chat/completions',
                          data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                          headers={'Content-Type': 'application/json',
                                   'Authorization': 'Bearer ' + key},
                          method='POST')
    t0 = time.time()
    try:
        with request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except HTTPError as e:
        return {'ok': False, 'model': model, 'endpoint': ep, 'masked_key': mask_key(key),
                'ms': int((time.time() - t0) * 1000), **_classify_http_error(e)}
    except URLError as e:
        return {'ok': False, 'error': 'connect_failed', 'model': model, 'endpoint': ep,
                'masked_key': mask_key(key), 'ms': int((time.time() - t0) * 1000),
                'hint': '连不上，检查 endpoint 或网络', 'detail': str(getattr(e, 'reason', e))[:300]}
    except Exception as e:
        return {'ok': False, 'error': 'request_failed', 'model': model, 'endpoint': ep,
                'masked_key': mask_key(key), 'ms': int((time.time() - t0) * 1000),
                'hint': report(e, where='setup_test'), 'detail': ''}

    ms = int((time.time() - t0) * 1000)
    try:
        data = json.loads(raw.decode('utf-8', 'replace'))
    except Exception:
        head = ' '.join(raw[:200].decode('utf-8', 'replace').split())
        return {'ok': False, 'error': 'not_json', 'model': model, 'endpoint': ep,
                'masked_key': mask_key(key), 'ms': ms,
                'hint': 'endpoint 返回的不是 JSON（像是把网址写成了官网首页）', 'detail': head[:300]}
    if data.get('error'):
        err = data['error']
        msg = err.get('message') if isinstance(err, dict) else str(err)
        return {'ok': False, 'error': 'upstream_error', 'model': model, 'endpoint': ep,
                'masked_key': mask_key(key), 'ms': ms, 'hint': '上游返回 error',
                'detail': str(msg)[:300]}
    choices = data.get('choices') or []
    if not choices:
        return {'ok': False, 'error': 'bad_response', 'model': model, 'endpoint': ep,
                'masked_key': mask_key(key), 'ms': ms, 'hint': '响应里没有 choices',
                'detail': json.dumps(data, ensure_ascii=False)[:300]}
    msg = choices[0].get('message') or {}
    content = msg.get('content')
    if isinstance(content, list):
        content = ''.join(p.get('text', '') if isinstance(p, dict) else str(p) for p in content)
    reply = CO.sanitize_worker_text(content or '')[:200]
    return {'ok': True, 'model': model, 'endpoint': ep, 'masked_key': mask_key(key),
            'ms': ms, 'reply': reply or '(空回复，但连接正常)'}


def setup_save(endpoint, api_key, model, gateway=None):
    """写配置：备份 + 原子写；coordinator 与 workers 四层同时更新。"""
    ep = _clean_endpoint(endpoint)
    model = (model or '').strip()
    key = (api_key or '').strip()
    if not model:
        raise PathError('model 不能为空')
    if not key:
        if re.match(r'^https?://(127\.0\.0\.1|localhost)(:\d+)?', ep):
            key = 'ollama'
        else:
            raise PathError('api_key 不能为空')

    cfg = load_cfg_fresh()
    if not isinstance(cfg, dict):
        cfg = {}
    co = cfg.get('coordinator')
    if not isinstance(co, dict):
        co = {}
    co.update({'model': model, 'endpoint': ep, 'api_key': key})
    cfg['coordinator'] = co
    workers = cfg.get('workers')
    if not isinstance(workers, dict):
        workers = {}
    for role in ('research', 'thinking', 'writing', 'quality'):
        w = workers.get(role)
        if not isinstance(w, dict):
            w = {}
        w.update({'model': model, 'endpoint': ep, 'api_key': key})
        workers[role] = w
    cfg['workers'] = workers

    # 可选：同时落网关配置（POST /api/setup/save 带 gateway 字段时）
    if isinstance(gateway, dict):
        gw = cfg.get('gateway')
        if not isinstance(gw, dict):
            gw = {}
        for k in ('enabled', 'base', 'downstream_key', 'fee_rate', 'model_map', 'pricing_ttl'):
            if k in gateway and gateway[k] is not None:
                gw[k] = gateway[k]
        cfg['gateway'] = gw

    os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
    backup = None
    if os.path.exists(CFG_PATH):
        shutil.copy2(CFG_PATH, CFG_BAK)
        backup = CFG_BAK
    tmp = CFG_PATH + '.tmp~'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CFG_PATH)
    reload_cfg()
    gw_now = CO.gateway_cfg(cfg)
    return {'ok': True, 'configured': key_valid(key), 'backup': backup,
            'config_path': CFG_PATH,
            'current': {'model': model, 'endpoint': ep, 'api_key': mask_key(key)},
            'gateway': {'enabled': bool(gw_now['enabled']), 'base': gw_now.get('base'),
                        'has_key': bool(gw_now.get('downstream_key')),
                        'need_login': bool(gw_now.get('need_login'))}}


# ---------------- 账户 / 用量（代理 new-api） ----------------
#
# 前端不直连 new-api：登录在这里换成后端 session，余额/明细都走后端代理。
# new-api v1.0.0-rc.47 的登录返回 data.access_token（JWT），后续 /api/user/self、
# /api/log/self 都要 Authorization: Bearer <JWT>（session cookie 不够）。
# session 只存内存（进程重启需要重新登录，符合"会话"语义）。

SESSION_TTL = 7 * 24 * 3600
import secrets as _secrets
import sqlite3
import threading

# 2026-11-07：session 从内存 dict 改为 SQLite 落盘。
# 原来进程一重启所有客户被踢下线，客户会当成 bug。
_SESSION_DB_LOCK = threading.Lock()
_SESSION_DB = {"path": None}


def _session_db_path():
    return os.path.join(DATA_ROOT, "sessions.db")


def _session_db():
    path = _session_db_path()
    if _SESSION_DB["path"] != path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _SESSION_DB["path"] = path
    conn = sqlite3.connect(path, timeout=5)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sessions ("
        "sid TEXT PRIMARY KEY, token TEXT, username TEXT, user_id TEXT,"
        "created REAL, last_seen REAL, expires_at TEXT)"
    )
    conn.commit()
    return conn


def _prune_sessions():
    cutoff = time.time() - SESSION_TTL
    try:
        with _SESSION_DB_LOCK:
            conn = _session_db()
            conn.execute("DELETE FROM sessions WHERE created < ?", (cutoff,))
            conn.commit()
            conn.close()
    except Exception:
        pass


def _session_put(sid, sess):
    try:
        with _SESSION_DB_LOCK:
            conn = _session_db()
            conn.execute(
                "INSERT OR REPLACE INTO sessions"
                "(sid,token,username,user_id,created,last_seen,expires_at)"
                "VALUES(?,?,?,?,?,?,?)",
                (sid, sess.get("token") or "", sess.get("username") or "",
                 str(sess.get("user_id") or ""),
                 float(sess.get("created") or time.time()),
                 time.time(), str(sess.get("expires_at") or "")),
            )
            conn.commit()
            conn.close()
    except Exception:
        pass


def _session_get(sid):
    try:
        with _SESSION_DB_LOCK:
            conn = _session_db()
            row = conn.execute(
                "SELECT token,username,user_id,created,last_seen,expires_at"
                " FROM sessions WHERE sid=?", (sid,)).fetchone()
            if row:
                conn.execute("UPDATE sessions SET last_seen=? WHERE sid=?",
                             (time.time(), sid))
                conn.commit()
            conn.close()
    except Exception:
        return None
    if not row:
        return None
    if time.time() - float(row[3] or 0) > SESSION_TTL:
        return None
    return {"token": row[0], "username": row[1], "user_id": row[2],
            "created": row[3], "last_seen": row[4], "expires_at": row[5]}


def _session_count():
    try:
        with _SESSION_DB_LOCK:
            conn = _session_db()
            n = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            conn.close()
            return int(n or 0)
    except Exception:
        return 0


def _session_clear():
    try:
        with _SESSION_DB_LOCK:
            conn = _session_db()
            conn.execute("DELETE FROM sessions")
            conn.commit()
            conn.close()
    except Exception:
        pass


def _get_session(handler=None, sid=None, q=None, body=None):
    _prune_sessions()
    if not sid:
        if body:
            sid = body.get("session")
        if not sid and q:
            sid = (q.get("session") or [""])[0]
        if not sid and handler is not None:
            sid = (handler.headers.get("X-Novela-Session")
                   or (handler.headers.get("Authorization") or "").replace("Bearer ", "").strip())
    return (sid, _session_get(sid)) if sid else (None, None)


# 挂件里的"问客户"：工具调用阻塞在一个 Event 上，答案由 /api/assistant/answer 塞进来
_ASK_WAIT = {}


def uuid_hex():
    import uuid as _uuid
    return _uuid.uuid4().hex[:12]


def _fee_rate_of(cfg_dict):
    """服务费率：0 是合法值（= 按官方价收），不能用 `or 0.05` 兜底把 0 吞掉。"""
    v = (cfg_dict or {}).get('fee_rate')
    return float(v) if v is not None else 0.0


def _balance_payload(data, sess):
    quota = float(data.get('quota') or 0)
    used = float(data.get('used_quota') or 0)
    pricing = CO.gateway_pricing()
    fee_rate = _fee_rate_of(CO.gateway_cfg(CFG))
    return {'ok': True,
            'username': data.get('username') or sess.get('username'),
            'quota': quota, 'used_quota': used,
            'balance_cny': CO.quota_to_cny(quota, pricing),
            'used_cny': CO.quota_to_cny(used, pricing),
            'request_count': data.get('request_count'),
            'fee_rate': fee_rate}


def account_login(username, password):
    if not isinstance(username, str) or not isinstance(password, str) or not username.strip() or not password:
        raise PathError('username / password 不能为空')
    resp = _gw_open('POST', '/api/user/login',
                    {'username': username.strip(), 'password': password})
    if not resp.get('success'):
        msg = str(resp.get('message') or '')
        low = msg.lower()
        if resp.get('_http') == 429 or 'too many' in low or 'rate' in low:
            return {'ok': False, 'error': 'rate_limited',
                    'hint': '网关限流（连续输错密码会触发），过几分钟再试', 'detail': msg[:200]}
        if resp.get('_http') in (401, 403) or 'incorrect' in low or 'unauthorized' in low or 'banned' in low:
            return {'ok': False, 'error': 'unauthorized', 'detail': msg[:200]}
        if resp.get('error') == 'connect_failed':
            return {'ok': False, 'error': 'connect_failed', 'detail': msg[:200]}
        return {'ok': False, 'error': 'login_failed', 'detail': msg[:200]}

    data = resp.get('data') or {}
    token = data.get('access_token') or data.get('accessToken') or ''
    user = data.get('user') or {}
    sid = _secrets.token_hex(16)
    sess = {'token': token, 'username': username.strip(),
            'user_id': user.get('id') or data.get('id'),
            'created': time.time(), 'expires_at': data.get('access_expires_at')}
    _session_put(sid, sess)

    info = _gw_open('GET', '/api/user/self', token=token) if token else {'success': False}
    payload = {'ok': True, 'session': sid,
               'username': (info.get('data') or {}).get('username') or sess['username'],
               'expires_in': SESSION_TTL, 'token_type': data.get('token_type')}
    if info.get('success'):
        payload.update(_balance_payload(info.get('data') or {}, sess))
    else:
        payload.update({'quota': user.get('quota'), 'used_quota': user.get('used_quota'),
                        'balance_cny': None, 'warn': '登录成功但读取余额失败：%s' % str(info.get('message') or '')[:120]})
    return payload


def account_balance(sid):
    _sid, sess = _get_session(sid=sid)
    if not sess:
        return {'ok': False, 'error': 'no_session', 'hint': '先 POST /api/account/login'}
    info = _gw_open('GET', '/api/user/self', token=sess.get('token'))
    if not info.get('success'):
        code = info.get('_http')
        return {'ok': False,
                'error': 'session_expired' if code in (401, 403) else 'gateway_error',
                'hint': '重新登录' if code in (401, 403) else '网关返回异常',
                'detail': str(info.get('message') or '')[:200]}
    return _balance_payload(info.get('data') or {}, sess)


def account_usage(sid, limit=20):
    _sid, sess = _get_session(sid=sid)
    if not sess:
        return {'ok': False, 'error': 'no_session', 'hint': '先 POST /api/account/login'}
    limit = max(1, min(int(limit or 20), 100))
    resp = _gw_open('GET', '/api/log/self?p=0&page_size=%d&type=2' % limit, token=sess.get('token'))
    if not resp.get('success'):
        code = resp.get('_http')
        return {'ok': False,
                'error': 'session_expired' if code in (401, 403) else 'gateway_error',
                'hint': '重新登录' if code in (401, 403) else '网关返回异常',
                'detail': str(resp.get('message') or '')[:200]}
    data = resp.get('data')
    if isinstance(data, dict):            # rc.47: {page,page_size,total,items}
        items = data.get('items') or []
        total = data.get('total')
    else:
        items = data or []
        total = len(items)
    pricing = CO.gateway_pricing()
    fee_rate = _fee_rate_of(CO.gateway_cfg(CFG))
    rows = []
    for it in items:
        try:
            quota = float(it.get('quota') or 0)
        except (TypeError, ValueError):
            quota = 0.0
        cny = CO.quota_to_cny(quota, pricing)
        official = round(cny / (1 + fee_rate), 6)
        rows.append({'time': it.get('created_at'),
                     'model': it.get('model_name'),
                     'prompt_tokens': int(it.get('prompt_tokens') or 0),
                     'completion_tokens': int(it.get('completion_tokens') or 0),
                     'quota': quota,
                     'official_cny': official,
                     'fee_cny': round(cny - official, 6),
                     'total_cny': cny,
                     'token_name': it.get('token_name'),
                     'request_id': it.get('request_id')})
    return {'ok': True, 'count': len(rows), 'total': total, 'usage': rows,
            'quota_per_unit': pricing.get('quota_per_unit'),
            'price': pricing.get('price'), 'fee_rate': fee_rate}


# ---------------- 客户专属令牌（登录 → 签发 → 注入 DSH） ----------------
#
# new-api 的 POST /api/token/ 只回 {"success":true}，列表里的 key 是遮罩的，
# 所以单机部署（网关和客户端同一台机器）直接从 new-api.db 读明文：
#   base 指向 127.0.0.1/localhost → 单机模式，读 gateway.db_path
#   否则 → 远程模式 → 返回 need_remote（等远程签发接口）

USER_TOKEN_FILE = None   # 见下方初始化：统一走 data_dir()/config
CO.USER_TOKEN_PATH = None
USER_TOKEN_FILE = CO.user_token_path()
CO.migrate_legacy_token()
USER_TOKEN_FILE = CO.user_token_path()


def _gateway_is_local(g=None):
    g = g or CO.gateway_cfg(CFG)
    return bool(re.match(r'^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?', str(g.get('base') or '')))


def gateway_db_key(token_id=None, name=None):
    """从 new-api.db 读令牌明文。用副本读，避免和运行中的网关抢锁。"""
    g = CO.gateway_cfg(CFG)
    path = g.get('db_path') or ''
    if not path or not os.path.isfile(path):
        return None, 'db_missing'
    tmpdir = tempfile.mkdtemp(prefix='novelapp_gwdb_')
    try:
        dst = os.path.join(tmpdir, 'na.db')
        shutil.copy2(path, dst)
        for suf in ('-wal', '-shm'):
            if os.path.exists(path + suf):
                try:
                    shutil.copy2(path + suf, dst + suf)
                except OSError:
                    pass
        con = sqlite3.connect(dst, timeout=5)
        try:
            cur = con.cursor()
            row = None
            if token_id is not None:
                row = cur.execute('select key from tokens where id=?', (token_id,)).fetchone()
            if not row and name:
                row = cur.execute('select key from tokens where name=? order by id desc limit 1',
                                  (name,)).fetchone()
        finally:
            con.close()
    except Exception as e:
        return None, report(e)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if not row or not row[0]:
        return None, 'not_in_db'
    return str(row[0]), None


def _gw_token_items(jwt):
    resp = _gw_open('GET', '/api/token/?p=0&size=100', token=jwt)
    if not resp.get('success'):
        return []
    data = resp.get('data')
    if isinstance(data, dict):
        return data.get('items') or []
    return data or []


def _harden(path):
    """尽力把文件权限收到当前用户（Windows 用 icacls，其它平台 chmod 600）。"""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if os.name == 'nt':
        try:
            user = os.environ.get('USERNAME') or ''
            if user:
                subprocess.run(['icacls', path, '/inheritance:r', '/grant:r', user + ':F'],
                               capture_output=True, timeout=10)
        except Exception:
            pass


def save_user_token(payload):
    os.makedirs(os.path.dirname(USER_TOKEN_FILE), exist_ok=True)
    tmp = USER_TOKEN_FILE + '.tmp~'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, USER_TOKEN_FILE)
    _harden(USER_TOKEN_FILE)
    return USER_TOKEN_FILE


def load_user_token():
    try:
        with open(USER_TOKEN_FILE, encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def account_setup(username, password):
    """登录网关 → 找到/创建 novelapp-<用户名> 令牌 → 取明文 → 存本地。"""
    login = account_login(username, password)
    if not login.get('ok'):
        return login
    sid = login.get('session')
    sess = _session_get(sid) or {}
    jwt = sess.get('token') or ''
    uname = login.get('username') or username
    if not jwt:
        return {'ok': False, 'error': 'no_jwt', 'detail': '登录成功但没拿到 JWT'}
    g = CO.gateway_cfg(CFG)
    if not _gateway_is_local(g):
        return {'ok': False, 'need_remote': True, 'error': 'remote_mode',
                'hint': '网关不是本机（%s），需要远程签发接口' % g.get('base')}

    token_name = 'novelapp-%s' % uname
    items = _gw_token_items(jwt)
    target = next((t for t in items
                   if t.get('name') == token_name and int(t.get('status') or 1) == 1), None)
    created = False
    if not target:
        resp = _gw_open('POST', '/api/token/',
                        {'name': token_name, 'remain_quota': 0,
                         'unlimited_quota': True, 'expired_time': -1}, token=jwt)
        if not resp.get('success'):
            return {'ok': False, 'error': 'token_create_failed',
                    'detail': str(resp.get('message') or '')[:200]}
        created = True
        items = _gw_token_items(jwt)
        target = next((t for t in items
                       if t.get('name') == token_name and int(t.get('status') or 1) == 1), None)
    if not target:
        return {'ok': False, 'error': 'token_not_found', 'detail': '建了但列表里找不到 %s' % token_name}

    token_id = target.get('id')
    key, err = gateway_db_key(token_id=token_id, name=token_name)
    if not key:
        # 缓存/延迟兜底：按名字再试一次
        time.sleep(0.3)
        key, err = gateway_db_key(name=token_name)
    if not key:
        return {'ok': False, 'error': 'key_unavailable', 'detail': err,
                'hint': '读不到令牌明文，检查 gateway.db_path: %s' % g.get('db_path')}

    tok = key if key.startswith('sk-') else 'sk-' + key
    payload = {'token': tok, 'username': uname, 'token_name': token_name,
               'token_id': token_id, 'gateway_base': g.get('base'),
               'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    save_user_token(payload)
    pricing = CO.gateway_pricing()
    return {'ok': True, 'token': tok, 'masked': mask_key(tok),
            'token_name': token_name, 'token_id': token_id, 'created': created,
            'username': uname, 'quota': login.get('quota'),
            'balance_cny': login.get('balance_cny'),
            'key_source': 'new-api.db',
            'saved_to': USER_TOKEN_FILE,
            'fee_rate': _fee_rate_of(g),
            'quota_per_unit': pricing.get('quota_per_unit')}


def account_token():
    d = load_user_token()
    if not d or not d.get('token'):
        return {'ok': False, 'need_setup': True,
                'hint': '还没有专属令牌，先 POST /api/account/setup'}
    g = CO.gateway_cfg(CFG)
    return {'ok': True, 'token': d.get('token'), 'masked': mask_key(d.get('token')),
            'username': d.get('username'), 'token_name': d.get('token_name'),
            'token_id': d.get('token_id'), 'created': d.get('created'),
            'gateway_base': d.get('gateway_base') or g.get('base'),
            'active': CO.gateway_cfg(CFG).get('key_source') == 'user_token'}


def account_logout():
    removed = False
    try:
        if os.path.exists(USER_TOKEN_FILE):
            os.remove(USER_TOKEN_FILE)
            removed = True
    except OSError:
        pass
    n = _session_count()
    _session_clear()
    return {'ok': True, 'token_removed': removed, 'sessions_cleared': n}


# 2026-11-17 R19：dsh 通道已移除（原 dsh_env / launch_dsh / _dsh_env / 两条 /api/account/dsh* 路由）
# 见 docs/plan/90天-命题-v0.md §7.3 R19；发布包内 grep dsh 必须为 0


# ---------------- 质检（L1/L2 + L3/L4） ----------------

QC_SCRIPTS = {'l1l2': os.path.join('scripts', 'l1_l2_check.py'),
              'l3l4': os.path.join('scripts', 'l3_l4_check.py')}
QC_TIMEOUT = float((CFG.get('qc') or {}).get('timeout', 30))
_QC_ISSUE_RE = re.compile(r'^(❌|⚠️|ℹ️)\s*(ERROR|WARN|INFO)\s+(\S+)\s*(?:\[行\s*(\d+)\])?\s*(.*)$')
_SEV_OF = {'ERROR': 'error', 'WARN': 'warn', 'INFO': 'info'}


def _run_script(script_rel, args, timeout=QC_TIMEOUT):
    """跑质检脚本：返回 (ok, stdout, stderr, info)。异常不外抛。"""
    script = os.path.join(ROOT, script_rel)
    if not os.path.isfile(script):
        return False, '', '', {'error': 'script_missing', 'script': script_rel}
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    env['NOVELAPP_ROOT'] = ROOT       # 质检脚本靠它定位 config/，frozen 下 __file__ 指向 _MEIPASS
    cmd = CO.script_cmd(script_rel, args)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, env=env, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.TimeoutExpired:
        return False, '', '', {'error': 'timeout', 'script': script_rel, 'timeout': timeout}
    except Exception as e:
        return False, '', '', {'error': report(e), 'script': script_rel}
    out = (p.stdout or b'').decode('utf-8', 'replace')
    err = (p.stderr or b'').decode('utf-8', 'replace')
    info = {'script': script_rel, 'exit': p.returncode,
            'ms': int((time.time() - t0) * 1000)}
    if p.returncode not in (0, 1):      # 1 = --strict 有 error 时的正常返回
        info['error'] = 'exit_%d' % p.returncode
        if err.strip():
            info['stderr_tail'] = ' '.join(err.strip().split())[-300:]
    CO.log_qc_run(script_rel, info, err)      # 打包版没控制台，stderr 必须落盘
    return True, out, err, info


def _norm_issue(it, source):
    """统一成 {rule,severity,line,message,snippet,source}。"""
    sev = str(it.get('severity') or 'info').lower()
    if sev not in ('error', 'warn', 'info'):
        sev = 'info'
    line = it.get('line')
    try:
        line = int(line) if line not in (None, '') else None
        if line is not None and line <= 0:
            line = None
    except (TypeError, ValueError):
        line = None
    return {'rule': str(it.get('rule') or 'unknown'),
            'severity': sev,
            'line': line,
            'message': str(it.get('message') or ''),
            'snippet': str(it.get('snippet') or '')[:160],
            'source': source}


def _parse_l1l2_text(text):
    """l1_l2_check.py 没有 --json 输出时的兜底：解析它的人类可读报告。"""
    issues, pending = [], None
    for raw in text.splitlines():
        m = _QC_ISSUE_RE.match(raw.strip())
        if m:
            if pending:
                issues.append(pending)
            pending = {'rule': m.group(3), 'severity': _SEV_OF[m.group(2)],
                       'line': int(m.group(4)) if m.group(4) else None,
                       'message': m.group(5).strip(), 'snippet': ''}
        elif pending and raw.strip().startswith('→'):
            pending['snippet'] = raw.strip().lstrip('→').strip()[:160]
    if pending:
        issues.append(pending)
    return issues


def layers_payload():
    """GET /api/layers：四层配置 + 可选模型清单（UI 下拉直接渲染）。"""
    try:
        data = CO.layers_public()
    except Exception as e:
        return {'ok': False, 'error': report(e), 'layers': [], 'models': []}
    return {'ok': True, **data}


def gate_payload():
    """GET /api/gate：门禁策略 + 数据（词表条数）+ 当前是否可判定。"""
    policy = (RV.load_config() or {}).get('gate') or []
    data = RV.load_gate_data() or {}
    sens = data.get('sensitive') if isinstance(data.get('sensitive'), dict) else {}
    fact = data.get('fact_error') if isinstance(data.get('fact_error'), dict) else {}
    words = [w for w in (sens.get('words') or []) if isinstance(w, str) and w.strip()]
    pats = [p for p in (sens.get('patterns') or []) if isinstance(p, str) and p.strip()]
    rules = [r for r in (fact.get('rules') or []) if isinstance(r, str) and r.strip()]
    probe = RV.run_gate('', '')
    return {'ok': True, 'policy': policy, 'path': RV.GATE_PATH,
            'sensitive': {'words': len(words), 'patterns': len(pats), 'configured': bool(words or pats)},
            'fact_error': {'rules': len(rules), 'configured': bool(rules)},
            'word_count': {'min': (data.get('word_count') or {}).get('min')},
            'status': probe.get('status'), 'skipped': probe.get('skipped'),
            'error': RV._GATE.get('error')}


def reviewers_payload():
    """GET /api/reviewers：审稿团 + 合并模式 + 门禁规则。"""
    path = CO.REVIEWERS_PATH
    try:
        with open(path, encoding='utf-8-sig') as f:
            data = yamlite.loads(f.read())
    except OSError:
        return {'ok': False, 'error': 'no_config', 'detail': path,
                'mode': 'merge', 'reviewers': [], 'gate': []}
    except Exception as e:
        return {'ok': False, 'error': 'parse_error', 'detail': report(e),
                'mode': 'merge', 'reviewers': [], 'gate': []}
    if not isinstance(data, dict):
        return {'ok': False, 'error': 'parse_error', 'detail': '顶层不是映射',
                'mode': 'merge', 'reviewers': [], 'gate': []}
    reviewers = []
    for r in data.get('reviewers') or []:
        if not isinstance(r, dict):
            continue
        reviewers.append({
            'id': r.get('id'), 'name': r.get('name'),
            'enabled': bool(r.get('enabled', True)),
            'model': r.get('model'), 'weight': r.get('weight'),
            'focus': r.get('focus'), 'prompt': r.get('prompt'),
        })
    return {'ok': True, 'mode': data.get('mode') or 'merge', 'reviewers': reviewers,
            'gate': data.get('gate') or [], 'path': path}


def _absorb_verdict(payload, source, bucket):
    """把脚本的 verdict/coverage/source_revision 汇总出来（脚本是唯一判定方）。"""
    if not isinstance(payload, dict):
        return
    bucket[source] = {
        'verdict': payload.get('verdict'),
        'coverage': payload.get('coverage'),
        'source_revision': payload.get('source_revision'),
        'stale': bool(payload.get('stale')),
    }


def run_qc_file(chap_full, norm):
    """跑 L1/L2 + L3/L4，合并成统一结构。"""
    tmpdir = tempfile.mkdtemp(prefix='novelapp_qc_')
    issues, stats, errors = [], {}, []
    verdicts = {}
    try:
        # --- L3/L4：--json 写临时文件，不污染 projects/
        l3_json = os.path.join(tmpdir, 'l3l4.json')
        ok3, out3, err3, info3 = _run_script(QC_SCRIPTS['l3l4'], [chap_full, '--json', l3_json])
        if ok3 and info3.get('error') is None:
            payload = None
            if os.path.exists(l3_json):
                try:
                    with open(l3_json, encoding='utf-8') as f:
                        payload = json.load(f)
                except Exception as e:
                    errors.append({'tool': 'l3l4', 'error': 'json_parse: %s' % e})
            if payload is None:
                errors.append({'tool': 'l3l4', 'error': 'no_json',
                               'stdout_tail': ' '.join(out3.strip().split())[-300:]})
            else:
                for it in payload.get('issues') or []:
                    issues.append(_norm_issue(it, 'l3l4'))
                stats['l3l4'] = payload.get('stats') or {}
                _absorb_verdict(payload, 'l3l4', verdicts)
        else:
            errors.append({'tool': 'l3l4', **{k: v for k, v in info3.items() if k in ('error', 'stderr_tail', 'timeout')}})

        # --- L1/L2：--json 直读 stdout（主路径）；落盘路径也指到临时目录，不写 projects/
        #     兜底顺序：stdout JSON -> 临时文件 -> 解析报告文本（仅旧版脚本才会走到）
        l1_json = os.path.join(tmpdir, 'l1l2.json')
        ok1, out1, err1, info1 = _run_script(QC_SCRIPTS['l1l2'], [chap_full, '--json', l1_json])
        if ok1 and info1.get('error') is None:
            payload, via = None, None
            head = out1.lstrip()
            if head.startswith('{'):
                try:
                    payload, via = json.loads(head), 'json'
                except Exception:
                    payload = None
            if payload is None and os.path.exists(l1_json):
                try:
                    with open(l1_json, encoding='utf-8') as f:
                        payload, via = json.load(f), 'json_file'
                except Exception:
                    payload = None
            if payload is not None:
                for it in payload.get('issues') or []:
                    issues.append(_norm_issue(it, 'l1l2'))
                stats['l1l2'] = payload.get('stats') or {}
                stats['l1l2']['_from'] = via
                _absorb_verdict(payload, 'l1l2', verdicts)
            else:
                parsed = _parse_l1l2_text(out1)
                for it in parsed:
                    issues.append(_norm_issue(it, 'l1l2'))
                stats['l1l2'] = {'_from': 'text', 'issues_parsed': len(parsed)}
        else:
            errors.append({'tool': 'l1l2', **{k: v for k, v in info1.items() if k in ('error', 'stderr_tail', 'timeout')}})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    issues.sort(key=lambda i: (i['line'] if i['line'] is not None else 10 ** 9,
                               {'error': 0, 'warn': 1, 'info': 2}[i['severity']]))
    counts = {'error': 0, 'warn': 0, 'info': 0}
    for i in issues:
        counts[i['severity']] += 1
    with open(chap_full, encoding='utf-8', errors='replace') as f:
        fstats = stats_text(f.read())

    # 汇总裁决：任一 fail -> fail；否则任一 inconclusive -> inconclusive；全 pass 才 pass
    got = [v for v in verdicts.values() if v.get('verdict')]
    if any(v['verdict'] == 'fail' for v in got):
        overall = 'fail'
    elif len(got) < 2 or any(v['verdict'] == 'inconclusive' for v in got):
        overall = 'inconclusive'
    else:
        overall = 'pass'
    cov = {'checked': 0, 'skipped': 0, 'total': 0}
    for v in got:
        c = v.get('coverage') or {}
        for k in cov:
            cov[k] += int(c.get(k) or 0)
    revs = {v.get('source_revision') for v in got if v.get('source_revision')}

    result = {'ok': len(errors) < 2,          # 两边都挂才算整体失败
              'path': norm,
              'verdict': overall,
              'coverage': cov,
              'source_revision': next(iter(revs)) if len(revs) == 1 else None,
              'stale': any(v.get('stale') for v in got),
              'verdicts': verdicts,
              'log': CO.QC_LOG,
              'issues': issues,
              'stats': {'file': fstats, **stats},
              'summary': {'total': len(issues), **counts,
                          'level': 'error' if counts['error'] else ('warn' if counts['warn'] else 'pass')}}
    if errors:
        result['errors'] = errors
        result['ok'] = False if len(errors) >= 2 else True
    return result


# ---------------- 用量记账（供「我的账号」聚合，网关 session 只对有账号的人有效） ----------------

def _usage_path():
    return os.path.join(DATA_ROOT, 'usage.jsonl')


def log_usage(kind, book, chapter, billing, extra=None):
    """每次模型调用落一行到 data/usage.jsonl；失败只记日志，不影响主流程。"""
    try:
        rec = {
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'kind': str(kind or ''),
            'book': str(book or ''),
            'chapter': str(chapter or ''),
            'prompt_tokens': int((billing or {}).get('prompt_tokens') or 0),
            'completion_tokens': int((billing or {}).get('completion_tokens') or 0),
            'total_tokens': int((billing or {}).get('total_tokens') or 0),
            'cny': round(float((billing or {}).get('total_cny') or (billing or {}).get('cny') or 0), 6),
        }
        if isinstance(extra, dict):
            rec.update(extra)
        with open(_usage_path(), 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + chr(10))
        return rec
    except Exception as e:
        _log('用量记账失败：%s' % e)
        return None


def usage_summary(days=30):
    """读 usage.jsonl，聚合今天/本月/近 N 天/按类型。文件不存在返回空壳而不是报错。"""
    p = _usage_path()
    empty = {'ok': True, 'entries': 0, 'today': {'calls': 0, 'tokens': 0, 'cny': 0.0},
             'month': {'calls': 0, 'tokens': 0, 'cny': 0.0},
             'window': {'days': days, 'calls': 0, 'tokens': 0, 'cny': 0.0},
             'total': {'calls': 0, 'tokens': 0, 'cny': 0.0},
             'by_kind': {}, 'path': p}
    if not os.path.exists(p):
        return empty
    today = time.strftime('%Y-%m-%d')
    month = time.strftime('%Y-%m')
    cutoff = time.time() - int(days) * 86400
    out = dict(empty)
    out['by_kind'] = {}
    n = 0
    try:
        with open(p, encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                n += 1
                ts = str(r.get('ts') or '')
                tk = int(r.get('total_tokens') or 0)
                cy = float(r.get('cny') or 0)
                def bump(k):
                    out[k]['calls'] += 1
                    out[k]['tokens'] += tk
                    out[k]['cny'] = round(out[k]['cny'] + cy, 6)
                bump('total')
                if ts[:10] == today:
                    bump('today')
                if ts[:7] == month:
                    bump('month')
                try:
                    import calendar as _cal
                    _ = _cal
                    tstruct = time.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')
                    if time.mktime(tstruct) >= cutoff:
                        bump('window')
                except Exception:
                    pass
                k = str(r.get('kind') or 'other')
                b = out['by_kind'].setdefault(k, {'calls': 0, 'tokens': 0, 'cny': 0.0})
                b['calls'] += 1
                b['tokens'] += tk
                b['cny'] = round(b['cny'] + cy, 6)
    except OSError:
        return empty
    out['entries'] = n
    return out


def _csv_cell(v):
    """CSV 单元：含逗号/引号/换行的值加引号并转义双引号。"""
    s = str(v if v is not None else '')
    if any(ch in s for ch in ',"\r\n'):
        s = '"' + s.replace('"', '""') + '"'
    return s


def usage_export_csv(days=30):
    """读 usage.jsonl，按 ts 过滤最近 days 天，返回带 UTF-8 BOM 的 CSV 文本。
    文件不存在 / 全部记录过期时只返回表头，不报错。"""
    p = _usage_path()
    cutoff = time.time() - int(days) * 86400
    rows = []
    if os.path.exists(p):
        try:
            with open(p, encoding='utf-8', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    ts = str(r.get('ts') or '')
                    try:
                        if time.mktime(time.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')) < cutoff:
                            continue
                    except Exception:
                        continue
                    rows.append([ts,
                                 r.get('kind') or '',
                                 r.get('book') or '',
                                 r.get('chapter') or '',
                                 int(r.get('total_tokens') or 0),
                                 round(float(r.get('cny') or 0), 6)])
        except OSError:
            rows = []
    lines = ['ts,kind,book,chapter,total_tokens,cny']
    for row in rows:
        lines.append(','.join(_csv_cell(x) for x in row))
    return '\ufeff' + '\n'.join(lines) + '\n'

def atomic_write(full, content):
    os.makedirs(os.path.dirname(full), exist_ok=True)
    tmp = full + '.tmp~'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, full)
    return os.path.getsize(full)


def _dump_worker_prompt(role_key, model, system, prompt, call_cfg, source=''):
    """NOVELAPP_LOG_PROMPTS=1 时把真正发给模型的 system/prompt 落盘。"""
    if os.environ.get('NOVELAPP_LOG_PROMPTS') not in ('1', 'true', 'yes'):
        return
    try:
        data_dir = os.environ.get('NOVELAPP_DATA') or os.path.join(
            os.environ.get('APPDATA') or '', 'novelapp-desktop', 'data')
        logs = os.path.join(data_dir, 'logs')
        os.makedirs(logs, exist_ok=True)
        path = os.path.join(logs, 'worker-prompts.jsonl')
        rec = {
            'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
            'source': source,
            'role': role_key,
            'model': model,
            'temperature': (call_cfg or {}).get('temperature'),
            'max_tokens': (call_cfg or {}).get('max_tokens'),
            'system_chars': len(system or ''),
            'prompt_chars': len(prompt or ''),
            'system': system or '',
            'prompt': prompt or '',
        }
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception as e:
        try:
            _lg = os.path.join(os.environ.get('NOVELAPP_DATA') or '', 'logs')
            os.makedirs(_lg, exist_ok=True)
            with open(os.path.join(_lg, 'prompt-log-error.log'), 'a', encoding='utf-8') as _f:
                _f.write('%s %s\n' % (type(e).__name__, e))
        except Exception:
            pass


# ---------------- 灵感展开（照 Laper /v1/script/assist 的契约与预算抄的） ----------------
# 预算直接沿用它的数字：前 12 行 3000 字 / 后 6 行 1200 字 / 人物 12x600 / 账本 20x600
INSPIRE_BUDGET = {
    'seed': 2000,
    'before_lines': 12, 'before_chars': 3000,
    'after_lines': 6, 'after_chars': 1200,
    'cast_count': 12, 'cast_field': 600,
    'ledger_items': 20, 'ledger_value': 600,
    'max_variants': 3,
}


def _clip(text, limit):
    t = str(text or '')
    return t if len(t) <= limit else t[:limit]


def inspire_context(book, chapter):
    """按预算装配上下文：上一章末尾 / 人物卡 / 伏笔账本。缺什么就少给什么。"""
    out = {}
    try:
        import write_context as WC
        prev = WC._prev_chapters(book, str(chapter).zfill(3))
        if prev:
            tail = prev[-1][1]
            lines = tail.split(chr(10))[-INSPIRE_BUDGET['before_lines']:]
            out['before'] = _clip(chr(10).join(lines), INSPIRE_BUDGET['before_chars'])
    except Exception:
        pass
    base = os.path.join(PROJECTS, book, '设定库')
    for key, fname, budget in (
            ('cast', '角色卡.md', INSPIRE_BUDGET['cast_count'] * INSPIRE_BUDGET['cast_field']),
            ('ledger', '伏笔.md', INSPIRE_BUDGET['ledger_items'] * INSPIRE_BUDGET['ledger_value'])):
        try:
            with open(os.path.join(base, fname), encoding='utf-8-sig') as f:
                out[key] = _clip(f.read(), budget)
        except OSError:
            continue
    return out


INSPIRE_RULES = [
    '- 只写这一段（200-400 字），不写章节标题，不写任何说明',
    '- 动作要客观可见，不写心理总结和评价（不要「他心里一沉」这类）',
    '- 对白只写人物真说出口的话，不带括号里的表演指导',
    '- 不新增设定库里没有的人物、地名、物件',
    '- 不写「我记下了」「这句话稳」「比之前的都重」这类评价式短句',
]


def _setting_vocab(book):
    """从设定库收集已知专名（人物/地名/物件），用于机械核对。"""
    base = os.path.join(PROJECTS, book, '设定库')
    vocab = set()
    if not os.path.isdir(base):
        return vocab
    for root, _dirs, files in os.walk(base):
        for fn in files:
            if not fn.endswith('.md'):
                continue
            try:
                with open(os.path.join(root, fn), encoding='utf-8-sig') as f:
                    text = f.read()
            except OSError:
                continue
            for line in text.split(chr(10)):
                st = line.strip()
                if st.startswith('## ') or st.startswith('- **') or st.startswith('| '):
                    for w in re.findall(r'[\u4e00-\u9fa5]{2,6}', st):
                        vocab.add(w)
    return vocab


def inspire_verify(book, text):
    """核对输出里的专名：不在设定库里的按「疑似新增设定」报出来。

    照 Laper 的思路——把「别乱写设定」从软约束变成客户端可判定。
    """
    vocab = _setting_vocab(book)
    if not vocab:
        return {'checked': False, 'reason': '设定库为空，无法核对', 'suspects': []}
    known = set(w for w in vocab if len(w) >= 2 and w in text)
    cand = set()
    for m in re.finditer(r'\u300a([\u4e00-\u9fa5]{2,8})\u300b', text):
        cand.add(m.group(1))
    for m in re.finditer(r'[\u4e00-\u9fa5]{2,3}(?:店|铺|镇|村|庄|岭|沟|庙|坊|院|塔|楼)', text):
        name = m.group(0)
        # 候选里若含某个已知专名（或反之），算已知，不报
        if any(k in name or name in k for k in known):
            continue
        cand.add(name)
    suspects = [w for w in cand if w not in vocab]
    return {'checked': True, 'vocab_size': len(vocab), 'suspects': suspects[:8]}


def inspire_prompt(book, seed, hint, ctx, idx, total):
    """照 Laper 的硬约束思路：规则写死，让模型没得发挥。"""
    head = ('你是《%s》的作者。下面是你刚想到的一句话，请把它展开成一段正文。'
            % (book or '这本书'))
    body = ['【想法】' + str(seed)]
    if hint:
        body.append('【方向】' + str(hint))
    if total > 1:
        body.append('【第 %d 个方案】换一种写法，不要和其他方案重复' % idx)
    if ctx.get('before'):
        body.append('【前情（上一章末尾）】' + chr(10) + ctx['before'])
    if ctx.get('cast'):
        body.append('【人物】' + chr(10) + ctx['cast'])
    if ctx.get('ledger'):
        body.append('【伏笔账本】' + chr(10) + ctx['ledger'])
    return head + chr(10) + chr(10) + chr(10).join(INSPIRE_RULES) + chr(10) + chr(10) + (chr(10) + chr(10)).join(body)


def keep_scene_tag(abs_path):
    """读已有文件的场景标签行，供「整章重写」时拼回文件头。

    2026-11-08：改稿走 replace 会整文件覆盖，标签会丢——写盘前先捞出来。
    """
    try:
        with open(abs_path, encoding='utf-8-sig') as f:
            first = f.readline().strip()
        if first.startswith('<!--') and '\u573a\u666f' in first:
            return first + chr(10)
    except OSError:
        pass
    return ''


def scene_tag_lib():
    """scripts/scene_tag.py：场景标签的解析/写回（命令行与 HTTP 共用同一份实现）。"""
    p = os.path.join(ROOT, 'scripts')
    if p not in sys.path:
        sys.path.insert(0, p)
    import scene_tag as _scene_tag
    return _scene_tag


def _script_lib(name):
    """按名字加载 scripts/ 下的模块（debt_view / completion_feasibility 等）。"""
    p = os.path.join(ROOT, "scripts")
    if p not in sys.path:
        sys.path.insert(0, p)
    return __import__(name)



# ==== M0-ENTRIES-BEGIN ====
# 9 个入口的权威名单（不许增删）。state 只按 server.py 里**实际存在的专用路由**判定，
# 不按 UI 词频猜：
#   wired   = 有专用 handler，且 web/index.html 里搜得到入口名
#   ui_only = 有专用 handler，但 web/index.html 里搜不到入口名（后端有、壳里没入口）
#   missing = 没有专用 handler，只有通用 /api/file、/api/save、/api/tree 兜底
# routes 是 state 的判定依据；fallback 是真能读到内容的通用路由（给报告用，不参与判定）。
ENTRY_SPECS = [
    {'key': 'shelf',     'name': '书架',   'routes': ['/api/shelf'],                            'fallback': []},
    {'key': 'startbook', 'name': '开书',   'routes': ['/api/planning'],                         'fallback': []},
    {'key': 'write',     'name': '写',     'routes': ['/api/write'],                            'fallback': []},
    {'key': 'outline',   'name': '大纲',   'routes': ['/api/outline'],                          'fallback': ['/api/file', '/api/save']},
    {'key': 'settings',  'name': '设定库', 'routes': ['/api/settings'],                         'fallback': ['/api/tree', '/api/file', '/api/save']},
    {'key': 'breakdown', 'name': '拆书',   'routes': ['/api/breakdown/dimensions', '/api/breakdown/import'], 'fallback': []},
    {'key': 'qc',        'name': '质检',   'routes': ['/api/qc'],                               'fallback': []},
    {'key': 'style',     'name': '文风',   'routes': ['/api/polish', '/api/polish/presets'],     'fallback': []},
    {'key': 'billing',   'name': '账单',   'routes': ['/api/usage/summary', '/api/usage/export'], 'fallback': []},
]

# web/index.html 里出现过入口名的 key（2026-11-17 实测 Select-String 命中数：
# 写 9 / 大纲 6 / 设定库 8 / 质检 11；书架 0 / 开书 0 / 拆书 0 / 文风 0 / 账单 0）
UI_HAS_NAME = frozenset(['write', 'outline', 'settings', 'qc'])

_IMPL_CACHE = {}


def ads_payload():
    """广告位：默认关闭。配置 data/config/ads.json（enabled/slots[]）。
    原则：不遮正文、不弹窗、不收集用户数据、不按点击计费；前端可关闭（localStorage）。"""
    p = os.path.join(ROOT, 'data', 'config', 'ads.json')
    off = {'ok': True, 'enabled': False, 'slots': [], 'policy': 'default-off'}
    if not os.path.exists(p):
        return off
    try:
        with open(p, encoding='utf-8') as f:
            raw = json.load(f)
    except Exception as e:
        return {'ok': False, 'enabled': False, 'slots': [],
                'error': report(e)}
    if not isinstance(raw, dict) or not raw.get('enabled'):
        return off
    today = time.strftime('%Y-%m-%d')
    out = []
    for it in (raw.get('slots') or []):
        if not isinstance(it, dict) or not it.get('title'):
            continue
        if it.get('starts') and today < str(it['starts']):
            continue
        if it.get('ends') and today > str(it['ends']):
            continue
        out.append({'id': it.get('id') or it['title'],
                    'place': it.get('place') or 'bottom-right',
                    'title': it['title'],
                    'text': it.get('text') or '',
                    'url': it.get('url') or '',
                    'sponsor': it.get('sponsor') or '',
                    'label': '广告'})
    return {'ok': True, 'enabled': True, 'slots': out, 'policy': 'closable-no-tracking'}


def _implemented_paths():
    """扫自身源码里 do_GET/do_POST 的 u.path 字面量，得到"实际存在的路由"集合。

    不硬编码：路由增删后这里自动跟上，/api/entries 不会说谎。
    """
    cached = _IMPL_CACHE.get('paths')
    if cached is not None:
        return cached
    found = set()
    try:
        with open(os.path.abspath(__file__), encoding='utf-8', errors='replace') as f:
            src = f.read()
        for m in re.finditer(r"u\.path\s*==\s*'([^']+)'", src):
            found.add(m.group(1))
        for m in re.finditer(r"u\.path\s+in\s+\(([^)]*)\)", src):
            for lit in re.findall(r"'([^']+)'", m.group(1)):
                found.add(lit)
    except Exception:
        pass
    _IMPL_CACHE['paths'] = found
    return found


def _server_bytes(path):
    try:
        return int(os.path.getsize(path))
    except Exception:
        return 0


def entries_payload():
    """GET /api/entries —— 9 个入口各自什么状态 + 判定依据路由。只读，不写盘。"""
    impl = _implemented_paths()
    rows = []
    for spec in ENTRY_SPECS:
        key = spec['key']
        hits = [p for p in spec['routes'] if p in impl]
        if hits:
            state = 'wired' if key in UI_HAS_NAME else 'ui_only'
            evidence = hits[0]
            route = evidence
        else:
            state = 'missing'
            evidence = ''
            route = '/api/%s' % key
        rows.append({'key': key, 'name': spec['name'], 'state': state,
                     'route': route, 'evidence_route': evidence,
                     'fallback_routes': list(spec['fallback'])})
    counts = {'wired': 0, 'ui_only': 0, 'missing': 0}
    for r in rows:
        counts[r['state']] = counts.get(r['state'], 0) + 1
    shipped = os.path.join(ROOT, '发布桌面版', 'core', 'server.py')
    src = os.path.abspath(__file__)
    src_bytes = _server_bytes(src)
    shipped_bytes = _server_bytes(shipped)
    shipped_present = os.path.isfile(shipped)
    # issue-0001：发布包比源码瘦一大截时要说出来，否则会有人直接把旧包发出去
    shipped_stale = bool(shipped_present and src_bytes and shipped_bytes < src_bytes * 0.8)
    if not shipped_present:
        shipped_note = '没有发布包（还没打包）'
    elif shipped_stale:
        shipped_note = ('发布包是旧版（%d 字节 vs 源码 %d 字节，仅 %.0f%%），'
                        '含已知安全修复缺失，先重新构建再用'
                        % (shipped_bytes, src_bytes, 100.0 * shipped_bytes / src_bytes))
    else:
        shipped_note = ''
    return {'ok': True,
            'entries': rows,
            'counts': counts,
            'server_source': src,
            'server_source_bytes': src_bytes,
            'shipped_path': shipped,
            'shipped_bytes': shipped_bytes,
            'shipped_present': shipped_present,
            'shipped_stale': shipped_stale,
            'shipped_note': shipped_note}
# ==== M0-ENTRIES-END ====

# ---------------- 大纲 / 设定库专用 API（v1.0.1 第 3 项） ----------------
# 依据 docs/架构-通用版/08-章纲分场规范.md：
#   章纲 = 场次表 + 必须做到的事 + 本章推进（可省） + 不许做 + 文风锚点
# 目的：这两个入口不再靠 /api/tree + /api/file + /api/save 兜底，
#       章纲在写入前就按规范校验，不合格直接挡下来。
_ENTRY_DIRS = {'outline': '大纲', 'settings': '设定库'}
_OUTLINE_BLOCKS = ('场次', '必须做到', '本章推进', '不许做', '文风锚点')


def _entry_dir_of(kind):
    d = _ENTRY_DIRS.get(kind)
    if not d:
        raise PathError('未知入口：%s' % kind)
    return d


def _entry_path(book, kind, name=''):
    """项目内 大纲/ 或 设定库/ 的路径。读写都走 safe_rel，越界抛 PathError。"""
    b = safe_name(book)
    rel = 'projects/%s/%s' % (b, _entry_dir_of(kind))
    if name:
        rel = rel + '/' + str(name).replace('\\', '/').strip('/')
        return safe_rel(rel, need_ext=('.md',))
    return safe_rel(rel)


def _md_title(txt, fallback):
    for line in (txt or '').splitlines():
        if line.startswith('# '):
            return line[2:].strip() or fallback
    return fallback


def _entry_item(full, rel_name):
    """一个 md 文件的列表项：标题、字数、改时间；读不了就给一节中文原因，不炸整棵树。"""
    try:
        with open(full, encoding='utf-8', errors='replace') as f:
            txt = f.read()
    except OSError as e:
        return {'name': rel_name, 'title': rel_name, 'chars': 0, 'error': human(e, '读取')}
    base = os.path.splitext(os.path.basename(rel_name))[0]
    try:
        mtime = time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(full)))
    except OSError:
        mtime = ''
    return {'name': rel_name, 'title': _md_title(txt, base), 'chars': len(txt), 'mtime': mtime}


def _walk_md(root, prefix='', depth=2):
    """递归收 .md（设定库下可能有 承诺/ 这类子目录）。返回 (items, error)。"""
    items = []
    try:
        names = sorted(os.listdir(root))
    except OSError as e:
        return items, human(e, '读取目录')
    for name in names:
        if name.startswith('.'):
            continue
        p = os.path.join(root, name)
        if os.path.isdir(p):
            if depth <= 0:
                continue
            sub, err = _walk_md(p, prefix + name + '/', depth - 1)
            items.extend(sub)
            if err:
                return items, err
            continue
        if not name.lower().endswith('.md'):
            continue
        items.append(_entry_item(p, prefix + name))
    return items, ''


def entry_list(book, kind):
    """列 大纲/ 或 设定库/ 下的一层 md。目录不存在不是错误，exists=false。"""
    norm, full = _entry_path(book, kind)
    res = {'ok': True, 'book': book, 'kind': kind, 'dir': _entry_dir_of(kind),
           'path': norm, 'exists': os.path.isdir(full), 'files': [], 'count': 0}
    if not res['exists']:
        return res
    files, err = _walk_md(full)
    res['files'] = files
    res['count'] = len(files)
    if err:
        res['error'] = err
    return res


def outline_blocks(text):
    """按 **块名** 切章纲块，返回 {块名: 正文}；只认规范里的五个块名。"""
    blocks, cur, buf = {}, None, []
    for line in (text or '').splitlines():
        m = re.match(r'^\*\*(.+?)\*\*\s*$', line.strip())
        name = ''
        if m:
            raw = m.group(1).strip()
            for known in _OUTLINE_BLOCKS:
                if raw.startswith(known):
                    name = known
                    break
        if name:
            if cur:
                blocks[cur] = '\n'.join(buf).strip()
            cur, buf = name, []
            continue
        if cur is not None:
            buf.append(line)
    if cur:
        blocks[cur] = '\n'.join(buf).strip()
    return blocks


def _is_chapter_outline(name, text):
    """哪些文件算章纲：文件名 3 位数字开头（009-xxx.md），或正文里已经有分场块。
    全书大纲 / 分卷大纲 这类整体大纲不做章纲校验。"""
    if re.match(r'^\d{3}', os.path.basename(str(name or ''))):
        return True
    return '<details' in (text or '').lower()


def check_chapter_outline(text):
    """章纲校验（六项必填 + 两条提醒）。error 级挡写入，warn 级只提示。

    依据 08-章纲分场规范 §二：场次表 / 必须做到 / 本章推进 / 不许做 / 文风锚点，缺一不可
    （本章推进可省——系统会按可推进卷自动挑，但挑出来的常和本章主题不搭）。
    """
    issues = []

    def add(code, level, msg):
        issues.append({'code': code, 'level': level, 'message': msg})

    txt = text or ''
    if '<details' not in txt.lower():
        add('outline.no-details', 'error',
            '没有分场块（<details>）：现在只是一句话章纲，模型会自己铺 1200 字环境再进冲突')
        return {'ok': False, 'issues': issues, 'blocks': [], 'scenes': 0}

    blocks = outline_blocks(txt)
    if not blocks:
        add('outline.no-blocks', 'error', '分场块里没有「**场次**」这类小标题，读不出块')
        return {'ok': False, 'issues': issues, 'blocks': [], 'scenes': 0}

    scenes = 0
    rows = [ln.strip() for ln in (blocks.get('场次') or '').splitlines()
            if ln.strip().startswith('|')]
    rows = [r for r in rows if not re.match(r'^\|[\s:|-]+\|$', r)]
    if not rows:
        add('outline.no-scene-table', 'error', '缺「场次」表：地点·时辰 / 发生什么 / 约字数 都没写')
    else:
        cols = [c for c in rows[0].strip('|').split('|')]
        if len(cols) < 4:
            add('outline.scene-cols', 'error',
                '场次表只有 %d 列，规范是 4 列（场 / 地点·时辰 / 发生什么 / 约字数）' % len(cols))
        scenes = max(len(rows) - 1, 0)
        if scenes < 2:
            add('outline.too-few-scenes', 'error',
                '只有 %d 场，至少 2 场；一场写到底就会变成流水账' % scenes)

    must = [ln for ln in (blocks.get('必须做到') or '').splitlines()
            if re.match(r'^\s*(\d+[.、)]|[-*]\s)', ln)]
    if len(must) < 3:
        add('outline.must-too-few', 'error',
            '「必须做到的事」只有 %d 条，规范是 3-6 条，每条要能用「有/没有」回答' % len(must))

    forb = [ln for ln in (blocks.get('不许做') or '').splitlines()
            if re.match(r'^\s*(\d+[.、)]|[-*]\s)', ln)]
    if not forb:
        add('outline.no-forbid', 'error', '缺「不许做」：模型会自编人物和设定')

    style = [ln for ln in (blocks.get('文风锚点') or '').splitlines()
             if re.match(r'^\s*(\d+[.、)]|[-*]\s)', ln)]
    if not style:
        add('outline.no-style-anchor', 'warn', '缺「文风锚点」：容易文风漂移，建议抄一句已有正文')

    adv = (blocks.get('本章推进') or '').strip()
    if adv and not re.findall(r'P-\d{3}', adv):
        add('outline.advance-no-id', 'warn', '「本章推进」里没有 P-XXX 编号，承诺表会变成死账')

    return {'ok': not any(i['level'] == 'error' for i in issues),
            'issues': issues, 'blocks': list(blocks.keys()), 'scenes': scenes}


class H(BaseHTTPRequestHandler):
    server_version = 'NovelApp/1.1'

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _entry_501(self, key):
        """缺失入口的占位应答：501 + X-Entry-State: missing。

        只回状态，不写盘、不落缓存、不触发后台任务。
        """
        body = json.dumps({'ok': False, 'error': 'not_implemented', 'entry': key},
                          ensure_ascii=False).encode('utf-8')
        self.send_response(501)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Entry-State', 'missing')
        self.end_headers()
        self.wfile.write(body)

    def _entry_dir(self, q, kind):
        """GET /api/outline、/api/settings：不带 name 列目录；带 name 读单篇。

        大纲单篇会附 check（章纲规范校验结果），前端据此标红不合格块。
        """
        book = (q.get('book') or [''])[0].strip()
        name = (q.get('name') or [''])[0].strip()
        if not book:
            self._json({'ok': False, 'kind': kind, 'error': 'book 必填'}, 400)
            return
        if not name:
            self._json(entry_list(book, kind), 200)
            return
        norm, full = _entry_path(book, kind, name)
        if not os.path.isfile(full):
            self._json({'ok': False, 'kind': kind, 'error': '文件不存在：%s' % name}, 404)
            return
        with open(full, encoding='utf-8', errors='replace') as f:
            txt = f.read()
        out = {'ok': True, 'kind': kind, 'book': book, 'name': name,
               'path': norm, 'content': txt, 'chars': len(txt)}
        if kind == 'outline':
            out['check'] = check_chapter_outline(txt) if _is_chapter_outline(name, txt) else None
        self._json(out, 200)

    def _entry_save(self, data, kind):
        """POST /api/outline、/api/settings：{book, name, content, force?}

        章纲（009-xxx.md 或已含 <details>）先过规范校验：error 级不写盘，除非 force=true。
        其它文件（全书大纲、设定库）只做长度与路径校验。
        """
        book = str(data.get('book') or '').strip()
        name = str(data.get('name') or '').strip()
        content = data.get('content')
        if not book or not name:
            self._json({'ok': False, 'kind': kind, 'error': 'book 和 name 必填'}, 400)
            return
        if not isinstance(content, str):
            self._json({'ok': False, 'kind': kind, 'error': 'content 必须是字符串'}, 400)
            return
        if len(content) > MAX_SAVE_CHARS:
            self._json({'ok': False, 'kind': kind,
                        'error': '内容过长（上限 %d 字）' % MAX_SAVE_CHARS}, 400)
            return
        norm, full = _entry_path(book, kind, name)
        chk = None
        if kind == 'outline' and _is_chapter_outline(name, content):
            chk = check_chapter_outline(content)
            if not chk['ok'] and not data.get('force'):
                self._json({'ok': False, 'kind': kind, 'name': name,
                            'error': '章纲不合格，没有写入', 'check': chk,
                            'hint': '按 check.issues 补全后再存；确实要存就带 force=true'}, 400)
                return
        os.makedirs(os.path.dirname(full), exist_ok=True)
        atomic_write(full, content)
        self._json({'ok': True, 'kind': kind, 'book': book, 'name': name,
                    'path': norm, 'chars': len(content), 'check': chk}, 200)

    def _err(self, msg, code=400, **extra):
        payload = {'error': msg}
        payload.update(extra)
        self._json(payload, code)

    # ---- v1.0.1 入口防护：Host / Origin / Content-Type ----
    def _guard(self):
        """拦在鉴权之前：假 Host、跨站 Origin、非 JSON 写请求一律 403。"""
        name = _host_key(self.headers.get('Host'))
        if name and not _allowed_host(name):
            self._json({'ok': False, 'error': 'host_not_allowed'}, 403)
            return False
        method = (self.command or '').upper()
        if method in _WRITE_METHODS:
            site = (self.headers.get('Sec-Fetch-Site') or '').strip().lower()
            if site == 'cross-site':
                self._json({'ok': False, 'error': 'origin_not_allowed'}, 403)
                return False
            origin = (self.headers.get('Origin') or '').strip()
            if origin:
                try:
                    port = self.server.server_address[1]
                except Exception:
                    port = 0
                if not _origin_same(origin, port):
                    self._json({'ok': False, 'error': 'origin_not_allowed'}, 403)
                    return False
        if method in ('POST', 'PUT', 'PATCH'):
            ctype = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            if ctype != 'application/json':
                self._json({'ok': False, 'error': 'content_type_not_json'}, 403)
                return False
        return True

    def _chat_ok(self):
        """对话接口必须带令牌：环境变量优先，否则用进程内随机令牌（由页面注入）。"""
        got = (self.headers.get('X-Novelapp-Token') or '').strip()
        expect = os.environ.get('NOVELAPP_BACKEND_TOKEN') or _session_token()
        return bool(got) and got == expect

    def _auth_ok(self):
        # 2026-11-07 auth (P0-2): 8770 had no auth at all.
        # Plugin generates token, passes via NOVELAPP_BACKEND_TOKEN.
        # No env var (manual debug) -> allow, keep compatibility.
        expect = os.environ.get('NOVELAPP_BACKEND_TOKEN') or ''
        if not expect:
            return True
        got = self.headers.get('X-Novelapp-Token') or ''
        return got == expect

    def _body(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        if n > MAX_BODY:
            raise PathError('请求体过大（上限 %d 字节）' % MAX_BODY)
        if not n:
            return {}
        raw = self.rfile.read(n)
        try:
            data = json.loads(raw.decode('utf-8'))
        except Exception:
            raise PathError('请求体不是合法 JSON')
        if not isinstance(data, dict):
            raise PathError('请求体必须是 JSON 对象')
        return data

    # 版本历史（对照 NovelCrafter 的 Revision History）与冷冻架（Scene Archive）
    # 实现在 core/history.py、core/shelf.py；这里只做参数校验 + 转发，不重复实现一份。

    def _history(self, q):
        book = (q.get('book') or [''])[0].strip()
        chapter = (q.get('chapter') or [''])[0].strip()
        if not book or not chapter:
            self._json({'ok': False, 'error': 'book 和 chapter 必填'}, 400)
            return
        if book != os.path.basename(book) or book.startswith('.'):
            self._json({'ok': False, 'error': 'book 不合法'}, 400)
            return
        if not os.path.isdir(os.path.join(PROJECTS, book)):
            self._json({'ok': False, 'error': '书不存在：%s' % book}, 404)
            return
        try:
            versions = HI.list_versions(book, chapter)
        except ValueError as e:
            self._json({'ok': False, 'error': str(e)}, 400)
            return
        self._json({'ok': True, 'book': book, 'chapter': HI.chapter_no(chapter),
                    'count': len(versions), 'versions': versions}, 200)

    def _history_diff(self, q):
        book = (q.get('book') or [''])[0].strip()
        chapter = (q.get('chapter') or [''])[0].strip()
        a = (q.get('a') or [''])[0].strip()
        b = (q.get('b') or [''])[0].strip()
        if not book or not chapter or not a or not b:
            self._json({'ok': False, 'error': 'book / chapter / a / b 都必填'}, 400)
            return
        if book != os.path.basename(book) or book.startswith('.'):
            self._json({'ok': False, 'error': 'book 不合法'}, 400)
            return
        if not os.path.isdir(os.path.join(PROJECTS, book)):
            self._json({'ok': False, 'error': '书不存在：%s' % book}, 404)
            return
        try:
            text = HI.diff(book, chapter, a, b)
        except ValueError as e:
            self._json({'ok': False, 'error': str(e)}, 400)
            return
        body = text.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _history_restore(self, data):
        book = str(data.get('book') or '').strip()
        chapter = str(data.get('chapter') or '').strip()
        vid = str(data.get('id') or data.get('vid') or '').strip()
        if not book or not chapter or not vid:
            self._json({'ok': False, 'error': 'book / chapter / id 都必填'}, 400)
            return
        if book != os.path.basename(book) or book.startswith('.'):
            self._json({'ok': False, 'error': 'book 不合法'}, 400)
            return
        if not os.path.isdir(os.path.join(PROJECTS, book)):
            self._json({'ok': False, 'error': '书不存在：%s' % book}, 404)
            return
        try:
            res = HI.restore(book, chapter, vid)
        except ValueError as e:
            self._json({'ok': False, 'error': str(e)}, 400)
            return
        except OSError as e:
            self._json({'ok': False, 'error': '恢复失败：%s' % e}, 500)
            return
        self._json(res, 200)

    def _shelf_set(self, data):
        book = str(data.get('book') or '').strip()
        if not book:
            self._json({'ok': False, 'error': 'book 必填'}, 400)
            return
        if book != os.path.basename(book) or book.startswith('.'):
            self._json({'ok': False, 'error': 'book 不合法'}, 400)
            return
        if not os.path.isdir(os.path.join(PROJECTS, book)):
            self._json({'ok': False, 'error': '书不存在：%s' % book}, 404)
            return
        raw = data.get('on')
        if isinstance(raw, str):
            on = raw.strip().lower() not in ('', '0', 'false', 'off', 'no')
        elif raw is None:
            on = True                      # 缺省 = 上架
        else:
            on = bool(raw)
        try:
            res = SH.set_shelf(book, on=on, note=data.get('note'))
        except ValueError as e:
            self._json({'ok': False, 'error': str(e)}, 400)
            return
        self._json(res, 200)

    def _shelf_list(self, q):
        books = SH.shelf_list()
        self._json({'ok': True, 'count': len(books), 'shelf': books}, 200)

    # -------- 缝针：把账目标成作废（商业研讨三方一致的一条）--------
    # 诊断完只给报告 = 分析工具，留存差；必须跟一个 5 分钟能做完的动作。
    def _abandonable(self, q):
        """列出这一本书里可以标作废的账目（伏笔 + 未兑付承诺）。"""
        book = (q.get('book') or [''])[0]
        if not book:
            self._json({'ok': False, 'error': 'book 必填'}, 400)
            return
        try:
            sys.path.insert(0, os.path.join(ROOT, 'scripts'))
            import ledger_abandon as LA
            rows, path = LA.list_foreshadow(book)
            items = [{'kind': 'foreshadow', 'id': r['id'], 'chapter': r['chapter'],
                      'title': r['content'][:40], 'status': r['status']}
                     for r in rows if r['status'] not in (LA.ABANDON, '已收')]
            prom = []
            pd = os.path.join(PROJECTS, book, '设定库', '承诺')
            if os.path.isdir(pd):
                for fn in sorted(os.listdir(pd)):
                    if not fn.endswith('.md'):
                        continue
                    fm = LA.front_matter(LA.read(os.path.join(pd, fn)))
                    if fm.get('状态') in (LA.ABANDON, '已兑付', '已完成', 'closed', 'done'):
                        continue
                    pid = fm.get('编号') or fn.replace('.md', '').split('-')[0]
                    prom.append({'kind': 'promise', 'id': pid,
                                 'title': (fm.get('标题') or fn)[:40],
                                 'status': fm.get('状态') or '进行'})
            self._json({'ok': True, 'book': book, 'foreshadow': items, 'promise': prom,
                        'file': path}, 200)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _abandon(self, data):
        """把指定的账目标成作废。data: {book, foreshadow: [id], promise: [id]}"""
        book = str(data.get('book') or '').strip()
        if not book:
            self._json({'ok': False, 'error': 'book 必填'}, 400)
            return
        fs_ids = [str(x) for x in (data.get('foreshadow') or [])]
        pm_ids = [str(x) for x in (data.get('promise') or [])]
        if not fs_ids and not pm_ids:
            self._json({'ok': False, 'error': '没有指定要作废的 id'}, 400)
            return
        try:
            sys.path.insert(0, os.path.join(ROOT, 'scripts'))
            import ledger_abandon as LA
            res = {}
            if fs_ids:
                res['foreshadow'] = LA.abandon_foreshadow(book, fs_ids, False)
            if pm_ids:
                res['promise'] = LA.abandon_promise(book, pm_ids, False)
            changed = sum(len(r.get('changed') or []) for r in res.values())
            self._json({'ok': True, 'changed': changed, 'detail': res}, 200)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _assistant(self, data):
        """POST /api/assistant —— 右栏挂件（私人助理）。

        2026-11-10 起走 run_agent（带全套工具）：能读文件、跑命令、导资料，
        不再限制成"只会写小说的问答"。账本摘要仍拼进人设，写作上下文不丢。
        """
        book = str(data.get('book') or '').strip()
        message = str(data.get('message') or '').strip()
        if not message:
            self._json({'ok': False, 'error': 'message 必填'}, 400)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()

        def send(ev):
            try:
                self.wfile.write(('data: ' + json.dumps(ev, ensure_ascii=False) + '\n\n').encode('utf-8'))
                self.wfile.flush()
            except Exception:
                pass

        try:
            # 附带文件：读不了就把错误当第一条 SSE 事件发回去（不静默丢、不调模型）
            preamble, ferr, _fmeta = _asst_files_preamble((data or {}).get('files'))
            if ferr:
                send({'type': 'error', 'text': ferr})
                return
            if preamble:
                message = preamble + '\n\n' + message
            # 简版账本上下文（比写章的装配轻得多）
            ctx_bits = []
            if book and data.get('use_book_context'):
                try:
                    sys.path.insert(0, os.path.join(ROOT, 'scripts'))
                    import debt_view as DV
                    rep = DV.build_debt(book, None)
                    if rep.get('ok'):
                        t = ['%s：%s（%s）' % (it['kind'], it['title'], it['why'])
                             for it in (rep.get('must_touch') or [])]
                        if t:
                            ctx_bits.append('当前必须动的账：' + '；'.join(t))
                        if rep.get('state_gaps'):
                            ctx_bits.append('资料缺口 %d 处' % len(rep['state_gaps']))
                except Exception:
                    pass
                try:
                    import completion as _c
                    crep = _c.analyze(book, None, None)
                    ctx_bits.append('未偿 %s 点，判定 %s' % (crep.get('M'), crep.get('verdict')))
                except Exception:
                    pass
            # 2026-11-10 按 YG 要求：挂件不再是「只会写小说的助手」，改成私人助理。
            # 走的是和主对话同一个 agent 循环（带工具），所以能读文件、跑命令、导资料。
            # 2026-11-10 按 YG 要求：解绑项目。挂件就是通用私人助理，不预设"当前项目：《X》"，
            # 也不默认塞账本；聊到某本书时，让用户点名、助手自己用工具去查。
            persona = (
                '你是这台电脑上的私人助理。读写文件、跑命令、翻目录、整理素材、导入资料、写小说，'
                '都是你的常规工作；客户已经授权整机读写，不存在「超出职责范围」，也不要把活推回给用户'
                '让自己贴内容。需要信息先用工具查，别猜。回答要短（通常 3-6 句），先给结论。'
                '你不绑定任何项目或书：用户没点名时按通用助理处理，别自称属于某个项目。')
            seed = dict(data)
            seed['_stage_text'] = str(data.get('message') or '')

            # 让模型能弹选项问客户：把 SSE 通道包成回调注册进 coordinator
            def _ask(question, options):
                aid = uuid_hex()
                slot = {'ev': threading.Event(), 'answer': None}
                _ASK_WAIT[aid] = slot
                try:
                    send({'type': 'ask', 'id': aid, 'question': question,
                          'options': list(options or [])})
                    slot['ev'].wait(120)          # 最多等 2 分钟
                finally:
                    _ASK_WAIT.pop(aid, None)
                return slot['answer']

            CO.ASK_HOOK = _ask
            final_text, usage = '', {}
            # 挂件是同步等的：加个总时限，跑太久就带着已完成的部分收尾，
            # 别让客户对着"…"等到天荒地老（2026-11-10 自检卡死）
            _acfg = CO._agent_cfg()
            deadline = time.time() + int(_acfg.get('assistant_timeout') or 150)
            steps = 0
            timed_out = False
            try:
                for ev in run_agent(message, seed, system_prefix=persona):
                    t = ev.get('type')
                    if t == 'tool':
                        steps += 1
                    elif t == 'final':
                        final_text = str(ev.get('text') or '')
                        usage = ev.get('usage') or {}
                    elif t == 'error':
                        send(ev)
                    if time.time() > deadline:
                        timed_out = True
                        break
            finally:
                CO.ASK_HOOK = None
            if timed_out and not final_text:
                final_text = ('跑了 %d 步、超过 %d 秒，先停在这里（再发「继续」我就接着做）。'
                              '要更快就把范围说小一点，比如只查一个目录或一个文件。'
                              % (steps, int(_acfg.get('assistant_timeout') or 150)))
            billing = {'total_tokens': int(usage.get('total_tokens') or 0),
                       'total_cny': float(usage.get('total_cny') or 0)}
            send({'type': 'done', 'text': final_text.strip(),
                  'tokens': billing['total_tokens'],
                  'cny': round(billing['total_cny'], 6)})
            try:
                log_usage('assistant', book, '', billing, {})
            except Exception:
                pass
        except Exception as e:
            send({'type': 'error', 'text': report(e)})

    def _assistant_answer(self, data):
        """POST /api/assistant/answer —— 挂件里点了选项/填了回答，把答案回给正在等的那次工具调用。"""
        data = data if isinstance(data, dict) else {}
        aid = str(data.get('id') or '').strip()
        ans = str(data.get('answer') or '').strip()
        slot = _ASK_WAIT.get(aid)
        if not slot:
            self._json({'ok': False, 'error': '这条提问已经过期（或已答过）'}, 404)
            return
        slot['answer'] = ans[:400]
        slot['ev'].set()
        self._json({'ok': True}, 200)

    def _dialog_open(self, data):
        """POST /api/dialog/open —— 弹系统文件选择框，回绝对路径。

        为什么后端弹：Electron 渲染进程在 contextIsolation 下拿不到绝对路径，
        插件也没接 host 的 dialog 能力。PowerShell + WinForms 的 OpenFileDialog 是
        最省事且稳的路子（客户机就是 Windows）。取消返回 ok=false, cancelled=true。
        """
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "[System.Windows.Forms.Application]::EnableVisualStyles();"
            "$owner = New-Object System.Windows.Forms.Form;"
            "$owner.TopMost = $true; $owner.ShowInTaskbar = $false; $owner.WindowState = 'Minimized';"
            "$d = New-Object System.Windows.Forms.OpenFileDialog;"
            "$d.Title = '选择要交给助手的文件';"
            "$d.Filter = '所有文件 (*.*)|*.*|文本 (*.txt;*.md;*.json;*.csv;*.log)|*.txt;*.md;*.markdown;*.json;*.csv;*.log|图片 (*.png;*.jpg;*.jpeg;*.webp;*.gif)|*.png;*.jpg;*.jpeg;*.webp;*.gif';"
            "$d.Multiselect = $false; $d.CheckFileExists = $true; $d.RestoreDirectory = $true;"
            "$r = $d.ShowDialog($owner);"
            "if ($r -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.WriteLine($d.FileName) }"
        )
        try:
            proc = subprocess.run(
                ['powershell', '-STA', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
                capture_output=True, timeout=300)
        except subprocess.TimeoutExpired:
            self._json({'ok': False, 'error': '对话框超过 5 分钟没选（超时）'}, 408)
            return
        except Exception as ex:
            self._json({'ok': False, 'error': report(ex)}, 500)
            return
        out = (proc.stdout or b'').decode('utf-8', 'replace').strip()
        if not out:
            self._json({'ok': False, 'cancelled': True}, 200)
            return
        path = out.splitlines()[-1].strip()
        self._json({'ok': True, 'path': path, 'name': os.path.basename(path)}, 200)

    def _assistant_file_info(self, data):
        """POST /api/assistant/file —— 挂件选中文件后算「文件名 · N 字」。

        只读、不缓存、不调模型；真正的读取发生在 /api/assistant 发消息时。
        """
        data = data if isinstance(data, dict) else {}
        full, err = _asst_check_path(data.get('path'))
        if err:
            self._json({'ok': False, 'error': err}, 400)
            return
        ext = os.path.splitext(full)[1].lower()
        # 2026-11-10：不再按后缀拒收。文本类给正文，其它给元信息（对齐 DSH 的任意文件口径）
        try:
            size = os.path.getsize(full)
        except OSError as e:
            self._json({'ok': False, 'error': report(e)}, 500)
            return
        if size > ASST_FILE_BYTES:
            self._json({'ok': False, 'error': '单个附件最多 %d MB，这个是 %.1f MB' % (
                ASST_FILE_BYTES // (1024 * 1024), size / 1024.0 / 1024.0)}, 400)
            return
        if not os.path.isfile(full):
            self._json({'ok': False, 'error': '文件不存在：%s' % full}, 404)
            return
        kind = 'text' if ext in ASST_TEXT_EXTS else ('image' if ext in ASST_IMAGE_EXTS else 'binary')
        if kind == 'text':
            try:
                text, clipped = _asst_read_text(full)
            except Exception as e:
                self._json({'ok': False, 'error': report(e)}, 500)
                return
            self._json({'ok': True, 'path': full, 'name': os.path.basename(full),
                        'ext': ext, 'kind': kind, 'chars': len(text), 'chars_at_least': clipped,
                        'limit': ASST_FILE_LIMIT,
                        'will_send': min(len(text), ASST_FILE_LIMIT)}, 200)
        else:
            self._json({'ok': True, 'path': full, 'name': os.path.basename(full),
                        'ext': ext, 'kind': kind, 'bytes': size,
                        'note': ('图片：发消息时会先让视觉模型（deepseek-flash）读成文字再交给助手'
                                 if kind == 'image' else '二进制文件：只给文件名/大小/类型')}, 200)

    # -------- 世界观策划流水线（13 步）--------

    def _planning_ask(self, data):
        """POST /api/planning/ask —— 对某一步跑一次 AI 辅助（不问就写）。

        data: {book, id, extra?}
        返回 {ok, text, model}；不自动写盘（客户看过再决定）。
        """
        book = str(data.get('book') or '').strip()
        sid = str(data.get('id') or '').strip()
        if not book or not sid:
            self._json({'ok': False, 'error': 'book / id 必填'}, 400)
            return
        try:
            import planning as PL
            out = PL.ask_step(book, sid, data.get('extra'))
            self._json(out, 200 if out.get('ok') else 400)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _planning(self, data):
        """POST /api/planning —— 13 步概览（状态 + 产出字数 + 进度）。"""
        book = str(data.get('book') or '').strip()
        if not book:
            self._json({'ok': False, 'error': 'book 必填'}, 400)
            return
        try:
            import planning as PL
            self._json({'ok': True, 'data': PL.summary(book)}, 200)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _breakdown_import(self, data):
        """POST /api/breakdown/import —— 导入一本参考书，拆出「开篇钩子 + 十合一」。

        慢（1-2 分钟，两次模型调用），前端要显示"拆解中"。
        """
        path = str(data.get('path') or '').strip()
        if not path:
            self._json({'ok': False, 'error': '文件路径必填'}, 400)
            return
        # 2026-11-17 修：粘贴样本走的是相对路径（projects/_拆书样本/x.md）。
        # 打包后进程 CWD 不是 projects 根，裸 isfile 会报"文件不存在" → 先按 projects_root/ROOT 解析。
        if not os.path.isabs(path):
            rel = path.replace('/', os.sep)
            for base in (projects_root(), ROOT):
                cand = os.path.join(base, rel)
                if os.path.isfile(cand):
                    path = cand
                    break
        try:
            import breakdown_ui as BU
            r = BU.import_book(path, data.get('name'))
            self._json(r, 200 if r.get('ok') else 400)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _breakdown_dimension(self, data):
        """POST /api/breakdown/dimension —— 给一本已拆过的书再拆一个维度。

        data: {book, code, force?}
        返回 {ok, book, code, file, chars, error?}；已拆过时带 exists=True。
        慢（一次模型调用，约 1-2 分钟），前端要显示"拆解中"。
        """
        book = str(data.get('book') or '').strip()
        code = str(data.get('code') or '').strip()
        if not book or not code:
            self._json({'ok': False, 'error': 'book / code 必填'}, 400)
            return
        raw = data.get('force')
        force = raw is True or raw == 1 or (isinstance(raw, str)
                                            and raw.strip().lower() in ('1', 'true', 'yes', 'on'))
        try:
            import breakdown_ui as BU
            r = BU.import_dimension(book, code, force=force)
            self._json(r, 200 if r.get('ok') else 400)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _breakdown_dimensions(self, q):
        """GET /api/breakdown/dimensions?book=<书名> —— 这本书哪些维度拆过了。"""
        book = (q.get('book') or [''])[0].strip()
        if not book:
            self._json({'ok': False, 'error': 'book 必填'}, 400)
            return
        try:
            import breakdown_ui as BU
            r = BU.list_dimensions(book)
            self._json(r, 200 if r.get('ok') else 400)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _planning_brief(self, data):
        """POST /api/planning/brief —— 记下「这本书你想写什么」。

        可以空着：空 = 按通用套路发散（决策权在作者，不做必填）。
        """
        book = str(data.get('book') or '').strip()
        if not book:
            self._json({'ok': False, 'error': 'book 必填'}, 400)
            return
        try:
            import planning as PL
            txt = PL.set_brief(book, data.get('text') or '')
            self._json({'ok': True, 'brief': txt, 'data': PL.summary(book)}, 200)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _planning_refs(self, data):
        """POST /api/planning/refs —— 记下「参考哪几本拆解」。可空。

        空 = 一本都不参考，只给推荐书单；不做必选。
        """
        book = str(data.get('book') or '').strip()
        if not book:
            self._json({'ok': False, 'error': 'book 必填'}, 400)
            return
        try:
            import planning as PL
            refs = PL.set_refs(book, data.get('refs') or [])
            self._json({'ok': True, 'refs': refs, 'data': PL.summary(book)}, 200)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _planning_step(self, data):
        """POST /api/planning/step —— 读/写某一步的产出。

        GET 语义（无 text 字段）：返回内容
        写语义（有 text 字段）：写盘；写完不自动改状态（状态由 status 接口管）
        """
        book = str(data.get('book') or '').strip()
        sid = str(data.get('id') or '').strip()
        if not book or not sid:
            self._json({'ok': False, 'error': 'book / id 必填'}, 400)
            return
        try:
            import planning as PL
            if 'text' in data:
                p = PL.write_step(book, sid, str(data.get('text') or ''))
                self._json({'ok': True, 'path': p.replace(os.sep, '/'),
                            'chars': len(str(data.get('text') or ''))}, 200)
            else:
                self._json({'ok': True, 'text': PL.read_step(book, sid)}, 200)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _planning_status(self, data):
        """POST /api/planning/status —— 改一步状态（含「跳过」和跳过原因）。"""
        book = str(data.get('book') or '').strip()
        sid = str(data.get('id') or '').strip()
        status = str(data.get('status') or '').strip()
        if not book or not sid:
            self._json({'ok': False, 'error': 'book / id 必填'}, 400)
            return
        try:
            import planning as PL
            cur = PL.set_step(book, sid, status or None, data.get('skip_reason'))
            self._json({'ok': True, 'step': cur, 'data': PL.summary(book)}, 200)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _recheck(self, data):
        """POST /api/chapter/recheck —— Step 7 复检：改完之后重跑四关。

        data: {book, chapter, text?（不传就读盘上当前稿）}
        规范：闸二「四关不过不许同步」。
        """
        book = str(data.get('book') or '').strip()
        ch = str(data.get('chapter') or '').strip()
        if not book or not ch:
            self._json({'ok': False, 'error': 'book / chapter 必填'}, 400)
            return
        try:
            import precheck as PC
            pre = PC.precheck(book, ch, data.get('text'))
            self._json({
                'ok': True,
                'passed': bool(pre.get('passed')),
                'blocking': pre.get('blocking') or [],
                'warnings': pre.get('warnings') or [],
                'score': pre.get('score'),
                'gate': '闸二：四关不过不许同步',
                'verdict': 'pass' if pre.get('passed') else 'fail',
            }, 200)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _ai_detect(self, data):
        """POST /api/ai-detect —— 判一章正文的「AI 痕迹」。

        data: {book, chapter}；chapter 可以是编号（001）也可以是文件名。
        一次模型调用（thinking 层，几秒到几十秒），只给疑似程度，不下断论。
        """
        book = str(data.get('book') or '').strip()
        ch = str(data.get('chapter') or '').strip()
        if not book or not ch:
            self._json({'ok': False, 'error': 'book / chapter 必填'}, 400)
            return
        if book != os.path.basename(book) or book in ('.', '..'):
            self._json({'ok': False, 'error': '书名不合法：%s' % book}, 400)
            return
        bdir = os.path.join(PROJECTS, book)
        if not os.path.isdir(bdir):
            self._json({'ok': False, 'error': '书不存在：%s' % book}, 404)
            return
        # chapter 两种写法：003（编号）或 003-第三章-中间那个字.md（文件名）
        fname = ch
        if not fname.lower().endswith('.md'):
            fname = resolve_chapter_file(book, ch)
        fname = os.path.basename(fname)
        if not fname or fname.startswith('.') or '..' in fname:
            self._json({'ok': False, 'error': '章节名不合法：%s' % ch}, 400)
            return
        full = os.path.join(bdir, '章节', fname)
        if not os.path.isfile(full):
            self._json({'ok': False, 'error': '章节不存在：projects/%s/章节/%s'
                        % (book, fname)}, 404)
            return
        try:
            with open(full, encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError as e:
            self._json({'ok': False, 'error': '读不了：' + report(e)}, 500)
            return
        try:
            import ai_detect as AD
            r = AD.detect(text, os.path.splitext(fname)[0])
            r['book'] = book
            r['chapter'] = fname
            self._json(r, 200 if r.get('ok') else 400)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _ai_detect_text(self, data):
        """POST /api/ai-detect/text —— 直接传一段文本（给以后的编辑器选区用）。

        data: {text, title?}；不读盘、不写盘，只出疑似程度。
        """
        text = data.get('text')
        if not isinstance(text, str) or not text.strip():
            self._json({'ok': False, 'error': 'text 必填（非空字符串）'}, 400)
            return
        title = str(data.get('title') or '').strip()[:80]
        try:
            import ai_detect as AD
            r = AD.detect(text, title)
            self._json(r, 200 if r.get('ok') else 400)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _ai_detect_rewrite(self, data):
        """POST /api/ai-detect/rewrite —— 给「去痕改写建议」（只读）。

        data: {book, chapter} 或 {text, title?, focus?}
        只返回建议（before/after/why），**不落盘、不改章节文件**：作者自己复制粘贴。
        路径校验口径和 _ai_detect 一致（两处刻意重复，避免动到已跑通的检测接口）。
        """
        book = str(data.get('book') or '').strip()
        ch = str(data.get('chapter') or '').strip()
        text = data.get('text')
        title = str(data.get('title') or '').strip()[:80]
        focus = str(data.get('focus') or '').strip()[:60]
        if book or ch:
            if not book or not ch:
                self._json({'ok': False, 'error': 'book / chapter 要一起给'}, 400)
                return
            if book != os.path.basename(book) or book in ('.', '..'):
                self._json({'ok': False, 'error': '书名不合法：%s' % book}, 400)
                return
            bdir = os.path.join(PROJECTS, book)
            if not os.path.isdir(bdir):
                self._json({'ok': False, 'error': '书不存在：%s' % book}, 404)
                return
            fname = ch
            if not fname.lower().endswith('.md'):
                fname = resolve_chapter_file(book, ch)
            fname = os.path.basename(fname)
            if not fname or fname.startswith('.') or '..' in fname:
                self._json({'ok': False, 'error': '章节名不合法：%s' % ch}, 400)
                return
            full = os.path.join(bdir, '章节', fname)
            if not os.path.isfile(full):
                self._json({'ok': False, 'error': '章节不存在：projects/%s/章节/%s'
                            % (book, fname)}, 404)
                return
            try:
                with open(full, encoding='utf-8', errors='replace') as f:
                    text = f.read()
            except OSError as e:
                self._json({'ok': False, 'error': '读不了：' + report(e)}, 500)
                return
            if not title:
                title = os.path.splitext(fname)[0]
        elif not isinstance(text, str) or not text.strip():
            self._json({'ok': False, 'error': 'book+chapter 或 text 必填'}, 400)
            return
        try:
            import ai_detect as AD
            r = AD.suggest(text, title, focus or None)
            r['book'] = book
            r['chapter'] = ch
            r['readonly'] = True        # 明写给前端：这条接口不会写任何文件
            self._json(r, 200 if r.get('ok') else 400)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    def _consensus(self, data):
        results = data.get('results')
        if not isinstance(results, list):
            self._json({'ok': False, 'error': 'results 必填（审稿结果数组）'}, 400)
            return
        try:
            import reviewers as RV
            out = RV.extract_consensus(results, model=data.get('model'))
            self._json(out, 200 if out.get('ok') else 400)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)

    # -------- GET --------

    def do_GET(self):
        if not self._guard():
            return
        if not self._auth_ok():
            return self._json({'ok': False, 'error': 'unauthorized'}, 401)
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            ensure_cfg_fresh()          # 请求入口做一次 mtime 比对，人工改配置立即生效
            if u.path in ('/', '/index.html'):
                self._index()
            elif u.path == '/api/tree':
                _rel = (q.get('path') or [''])[0].strip()
                if _rel:
                    _norm, _ = safe_rel(_rel)      # .. 穿越 / 绝对路径 -> PathError -> 400
                    self._json({'tree': tree(_norm), 'root': ROOT})
                else:
                    self._json({'tree': tree('projects'), 'root': ROOT})
            elif u.path == '/api/file':
                self._read_file(q)
            elif u.path == '/api/sessions':
                self._json(list_sessions())
                return
            elif u.path == '/api/config':
                self._json(mask_cfg(CFG))          # api_key 只出脱敏值
            elif u.path == '/api/setup/status':
                self._setup_status()
            elif u.path == '/api/config/reload':
                self._config_reload()
            elif u.path == '/api/account/balance':
                self._account_balance(q)
            elif u.path == '/api/billing/status':          # 开源版：不再计费，仅报成本遥测
                self._json({'ok': True, 'mode': 'free', 'billing': 'disabled',
                            'hint': '本项目开源免费，无订阅/无充值/无按章计费'}, 200)
                self._billing_status()
            elif u.path == '/api/account/usage':
                self._account_usage(q)
            elif u.path == '/api/account/token':
                self._account_token()
            elif u.path == '/api/gateway/status':
                self._gateway_status()
            elif u.path == '/api/layers':
                self._json(layers_payload(), 200)
            elif u.path == '/api/gate':
                self._json(gate_payload(), 200)
            elif u.path == '/api/login/status':
                token = _read_token()
                if not token:
                    LOGIN_CACHE.update({'at': 0.0, 'token_prefix': '', 'data': None})
                    self._json({'ok': True, 'logged_in': False}, 200)
                else:
                    prefix = _mask_token(token)
                    cached = LOGIN_CACHE.get('data')
                    fresh = (cached and LOGIN_CACHE.get('token_prefix') == prefix
                             and time.time() - LOGIN_CACHE.get('at', 0) < 60)
                    if fresh:
                        self._json({'ok': True, 'logged_in': True, 'cached': True, **cached}, 200)
                    else:
                        prof = _profile(token)
                        LOGIN_CACHE.update({'at': time.time(), 'token_prefix': prefix, 'data': prof})
                        self._json({'ok': True, 'logged_in': True, 'cached': False,
                                    'token_prefix': prefix, **prof}, 200)
            elif u.path == '/api/stages':
                book = (q.get('book') or [''])[0].strip()
                if not book:
                    self._json({'ok': False, 'error': 'book 不能为空'}, 400)
                elif not os.path.isdir(os.path.join(PROJECTS, book)):
                    self._json({'ok': False, 'error': '书不存在：%s' % book}, 404)
                else:
                    self._json({'ok': True, 'book': book,
                                'stages': ST.full_map(book),
                                'details': ST.details_map(book),
                                'missing': ST.missing_map(book)}, 200)
            elif u.path == '/api/breakdown/dimensions':
                self._breakdown_dimensions(q)
            elif u.path == '/api/polish/models':
                self._json(polish_models_payload(), 200)
            elif u.path == '/api/polish/presets':
                self._json(polish_presets_payload(), 200)
            elif u.path == '/api/polish/options':
                self._json(polish_options_payload(), 200)
            elif u.path == '/api/review/options':
                self._json(review_options_payload(), 200)
            elif u.path == '/api/reviewers':
                self._json(reviewers_payload(), 200)
            elif u.path == '/api/stats':
                self._stats(q)
            elif u.path == '/api/scene-tag':
                self._scene_tag(q)
            elif u.path == '/api/debt':
                self._debt(q)
            elif u.path == '/api/completion':
                self._completion(q)
            elif u.path == '/api/usage/summary':
                try:
                    _days = int((q.get('days') or ['30'])[0] or 30)
                except (TypeError, ValueError):
                    _days = 30
                self._json(usage_summary(_days), 200)
            elif u.path == '/api/usage/export':
                try:
                    _days = int((q.get('days') or ['30'])[0] or 30)
                except (TypeError, ValueError):
                    _days = 30
                csv_body = usage_export_csv(_days).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition',
                                 'attachment; filename="novelapp-usage-%s.csv"'
                                 % time.strftime('%Y%m%d'))
                self.send_header('Content-Length', str(len(csv_body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(csv_body)
            elif u.path == '/api/qc':
                self._qc(q)
            elif u.path == '/api/history':
                self._history(q)
            elif u.path == '/api/history/diff':
                self._history_diff(q)
            elif u.path == '/api/shelf':
                self._shelf_list(q)
            elif u.path == '/api/ledger/abandonable':
                self._abandonable(q)
            elif u.path == '/api/ads':          # 广告位（默认关闭）
                self._json(ads_payload(), 200)
            elif u.path == '/api/health':
                tok_path = CO.user_token_path()
                tok_prefix = ''
                try:
                    with open(tok_path, encoding='utf-8') as f:
                        _d = json.load(f)
                    _t = (_d.get('token') or _d.get('key') or '') if isinstance(_d, dict) else ''
                    tok_prefix = (_t[:8] + '...') if _t else ''
                except Exception:
                    tok_prefix = ''
                self._json({'ok': True, 'root': os.path.dirname(PROJECTS),
                            'projects': os.path.isdir(PROJECTS),
                            'data_dir': CO.data_dir(), 'token_file': tok_path,
                            'token_present': bool(tok_prefix), 'token_prefix': tok_prefix,
                            'projects_root': PROJECTS})
            elif u.path == '/api/entries':                    # M0-GET-ROUTES
                self._json(entries_payload(), 200)
            elif u.path == '/api/outline':                    # 大纲：列目录 / 读单篇
                self._entry_dir(q, 'outline')
            elif u.path == '/api/settings':                   # 设定库：列目录 / 读单篇
                self._entry_dir(q, 'settings')
            else:
                self._json({'error': 'unknown'}, 404)
        except PathError as e:
            self._err(str(e), 400)
        except Exception as e:
            self._err(report(e), 500)

    def _index(self):
        p = os.path.join(ROOT, 'web', 'index.html')
        if not os.path.exists(p):
            self._json({'error': 'index.html 不存在'}, 404)
            return
        body = open(p, 'rb').read()
        # v1.0.1：给页面注入请求令牌（页面脚本据此带 X-Novelapp-Token 调 /api/chat）
        _tk = (os.environ.get('NOVELAPP_BACKEND_TOKEN') or _session_token()).encode('utf-8')
        body = body.replace(b'__NOVELAPP_TOKEN__', _tk)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_file(self, q):
        """默认全量返回（章节最长也就几十万字，全量读没问题）。
        想要分块读时传 offset / limit，此时 truncated 才可能为 True。
        旧客户端传的 full=1 仍然接受（等价于默认行为）。"""
        rel = (q.get('path') or [''])[0]
        norm, full = safe_rel(rel)
        if os.path.isdir(full):
            self._json({'path': norm, 'dir': True, 'children': [c['name'] for c in tree(norm, 0)]})
            return
        if not os.path.exists(full):
            self._json({'error': 'not found'}, 404)
            return
        with open(full, encoding='utf-8', errors='replace') as f:
            content = f.read()
        total = len(content)
        offset = max(int((q.get('offset') or ['0'])[0] or 0), 0)
        limit_raw = (q.get('limit') or [''])[0]
        limit = int(limit_raw) if limit_raw not in ('', None) else None
        sliced = offset > 0 or limit is not None
        if sliced:
            piece = content[offset: offset + limit] if limit is not None else content[offset:]
        else:
            piece = content
        self._json({'path': norm, 'content': piece,
                    'chars': total, 'total_chars': total, 'offset': offset,
                    'truncated': len(piece) < total, 'sliced': sliced})

    def _stats(self, q):
        rel = (q.get('path') or [''])[0]
        if not rel.strip():
            self._json(stats_path(PROJECTS))
            return
        if rel.strip() in ('projects', 'projects/'):
            self._json(stats_path(PROJECTS))
            return
        norm, full = safe_rel(rel)
        if not os.path.exists(full):
            self._json({'error': 'not found'}, 404)
            return
        self._json(stats_path(full))

    def _qc(self, q):
        """GET /api/qc?path=<章节> —— 合并 L1/L2 + L3/L4 结果，脚本失败不升级成 500。"""
        rel = (q.get('path') or [''])[0]
        if not rel.strip():
            self._json({'ok': False, 'error': 'path 不能为空',
                        'issues': [], 'stats': {}}, 400)
            return
        try:
            norm, full = safe_rel(rel, need_ext=('.md',))
        except PathError as e:
            self._json({'ok': False, 'error': str(e), 'issues': [], 'stats': {}}, 400)
            return
        if not os.path.isfile(full):
            self._json({'ok': False, 'error': 'not found', 'path': norm,
                        'issues': [], 'stats': {}}, 404)
            return
        try:
            result = run_qc_file(full, norm)
        except Exception as e:
            self._json({'ok': False, 'error': report(e),
                        'issues': [], 'stats': {}}, 200)
            return
        self._json(result, 200)

    # -------- POST --------

    def do_POST(self):
        if not self._guard():
            return
        if not self._auth_ok():
            return self._json({'ok': False, 'error': 'unauthorized'}, 401)
        u = urlparse(self.path)
        try:
            ensure_cfg_fresh()
            data = self._body()
            if u.path == '/api/chat':
                if not self._chat_ok():
                    self._json({'ok': False, 'error': 'unauthorized'}, 401)
                    return
                self._chat(data)
                return
            if u.path == '/api/login':
                token = str(data.get('token') or '').strip()
                if not token:
                    self._json({'ok': False, 'error': '令牌不能为空'}, 400)
                    return
                if not re.match(r'^sk-[A-Za-z0-9_\-]{16,}$', token):
                    self._json({'ok': False, 'error': '令牌格式不对（应以 sk- 开头，后面是字母数字）'}, 400)
                    return
                probe = _probe(token)
                if not probe.get('ok'):
                    self._json({'ok': False, 'error': probe.get('error')}, probe.get('code') or 401)
                    return
                prof = _profile(token)
                try:
                    with open(_token_file(), 'w', encoding='utf-8') as f:
                        json.dump({'key': token, 'token': token,
                                   'saved_at': time.strftime('%Y-%m-%dT%H:%M:%S')}, f, ensure_ascii=False, indent=1)
                except OSError as e:
                    self._json({'ok': False, 'error': '令牌已验证，但写盘失败：%s' % e}, 500)
                    return
                LOGIN_CACHE.update({'at': 0.0, 'token_prefix': '', 'data': None})
                self._json({'ok': True, 'logged_in': True, 'token_prefix': _mask_token(token),
                            'path': _token_file(), **prof}, 200)
                return
            if u.path == '/api/logout':
                removed = False
                try:
                    if os.path.exists(_token_file()):
                        os.remove(_token_file())
                        removed = True
                except OSError:
                    pass
                LOGIN_CACHE.update({'at': 0.0, 'token_prefix': '', 'data': None})
                self._json({'ok': True, 'logged_in': False, 'removed': removed}, 200)
                return
            if u.path == '/api/inspire':
                self._inspire(data)
                return
            if u.path == '/api/polish':
                self._polish(data)
                return
            if u.path == '/api/billing/topup':             # 开源版：无充值
                self._json({'ok': False, 'error': 'gone', 'hint': '开源版不计费'}, 410)
                self._billing_topup(data)
                return
            if u.path == '/api/billing/refund':            # 开源版：无退款
                self._json({'ok': False, 'error': 'gone', 'hint': '开源版不计费'}, 410)
                self._billing_refund(data)
                return
            if u.path == '/api/write':
                self._write_stream(data)
                return
            if u.path == '/api/stages':
                book = str(data.get('book') or '').strip()
                try:
                    r = ST.set_stage(book, data.get('chapter'), data.get('stage'),
                                     reason=data.get('reason'), source=data.get('source'),
                                     action=data.get('action'))
                except ValueError as e:
                    self._json({'ok': False, 'error': str(e)}, 400)
                    return
                out = {'ok': True, **r}
                if r.get('stage') == 'done' and r.get('changed'):
                    # 定稿：把 .layers 对齐到盘上正文（刷新失败只记日志，挡不住定稿）
                    out['layer_refresh'] = layer_finalize_refresh(book, r.get('chapter'))
                self._json(out, 200)
                return
            if u.path == '/api/review/config':
                self._review_config(data)
                return
            if u.path == '/api/review/run':
                self._review_run(data)
                return
            if u.path == '/api/account/login':
                self._account_login(data)
            elif u.path == '/api/account/setup':
                self._account_setup(data)
            elif u.path == '/api/account/logout':
                self._json(account_logout(), 200)
            elif u.path == '/api/setup/test':
                self._setup_test(data)
            elif u.path == '/api/setup/save':
                self._setup_save(data)
            elif u.path == '/api/settings/search':
                self._settings_search(data)
            elif u.path == '/api/project':
                self._project(data)
            elif u.path == '/api/save':
                self._save(data)
            elif u.path == '/api/file/new':
                self._new_file(data)
            elif u.path == '/api/scene-tag':
                self._scene_tag_set(data)
            elif u.path == '/api/file/delete':
                self._delete_file(data)
            elif u.path == '/api/file/rename':
                self._rename_file(data)
            elif u.path == '/api/project/delete':
                self._delete_project(data)
            elif u.path == '/api/history/restore':
                self._history_restore(data)
            elif u.path == '/api/shelf':
                self._shelf_set(data)
            elif u.path == '/api/ledger/abandon':
                self._abandon(data)
            elif u.path == '/api/assistant':
                self._assistant(data)
            elif u.path == '/api/assistant/answer':
                self._assistant_answer(data)
                return
            elif u.path == '/api/sessions/archive':
                self._json(set_session_archived(data.get('id'), bool(data.get('archived'))))
                return
            elif u.path == '/api/settings/agent':
                self._json(save_agent_settings(data))
                return
            elif u.path == '/api/dialog/open':
                self._dialog_open(data)
                return
            elif u.path == '/api/assistant/file':
                self._assistant_file_info(data)
            elif u.path == '/api/review/consensus':
                self._consensus(data)
            elif u.path == '/api/chapter/recheck':
                self._recheck(data)
            elif u.path == '/api/layers/clear':
                self._layers_clear(data)
            elif u.path == '/api/ai-detect':
                self._ai_detect(data)
            elif u.path == '/api/ai-detect/text':
                self._ai_detect_text(data)
            elif u.path == '/api/ai-detect/rewrite':
                self._ai_detect_rewrite(data)
            elif u.path == '/api/planning':
                self._planning(data)
            elif u.path == '/api/planning/brief':
                self._planning_brief(data)
            elif u.path == '/api/breakdown/import':
                self._breakdown_import(data)
            elif u.path == '/api/breakdown/dimension':
                self._breakdown_dimension(data)
            elif u.path == '/api/planning/refs':
                self._planning_refs(data)
            elif u.path == '/api/planning/step':
                self._planning_step(data)
            elif u.path == '/api/planning/status':
                self._planning_status(data)
            elif u.path == '/api/planning/ask':
                self._planning_ask(data)
            elif u.path == '/api/outline':                    # 大纲：写单篇（章纲先校验）
                self._entry_save(data, 'outline')
            elif u.path == '/api/settings':                   # 设定库：写单篇
                self._entry_save(data, 'settings')
            else:
                self._json({'error': 'unknown'}, 404)
        except PathError as e:
            self._err(str(e), 400)
        except Exception as e:
            self._err(report(e), 500)

    def _layers_clear(self, data):
        """POST /api/layers/clear —— 删一章的 .layers 层缓存。

        data: {book, chapter}；chapter 认 '002' 也认 '002-xxx.md'（照现有写法）。
        只删缓存目录，不动正文、不备份、不改章节状态。
        """
        book = str(data.get('book') or '').strip()
        chapter = str(data.get('chapter') or '').strip()
        if not book or not chapter:
            self._json({'ok': False, 'error': 'book / chapter 必填'}, 400)
            return
        if book != os.path.basename(book) or book in ('.', '..'):
            self._json({'ok': False, 'error': '书名不合法：%s' % book}, 400)
            return
        bdir = os.path.join(PROJECTS, book)
        if not os.path.isdir(bdir):
            self._json({'ok': False, 'error': '书不存在：%s' % book}, 404)
            return
        ch = ST.chapter_no(chapter)
        if not ch:
            self._json({'ok': False, 'error': '章节号无法识别：%s' % chapter}, 400)
            return
        fname = resolve_chapter_file(book, ch)
        has_file = os.path.isfile(os.path.join(bdir, '章节', fname))
        has_cache = os.path.isdir(layer_dir(book, ch))
        if not has_file and not has_cache:
            self._json({'ok': False, 'error': '章节不存在：projects/%s/章节/%s'
                        % (book, ch)}, 404)
            return
        try:
            removed = layer_clear(book, ch)
        except OSError as e:
            self._json({'ok': False, 'error': '删不掉：' + report(e)}, 500)
            return
        _log('手动清层缓存：%s/%s 删了 %d 个文件' % (book, ch, len(removed)))
        self._json({'ok': True, 'book': book, 'chapter': ch, 'removed': removed}, 200)

    def _inspire(self, data):
        """POST /api/inspire —— 把一句话展开成正文片段（SSE，可变体）。

        契约照 Laper /v1/script/assist 抄：tool=expand、variants 1..3、
        上下文按预算裁（前 12 行 / 人物 12x600 / 账本 20x600），不落盘、不 commit。
        """
        book = str(data.get('book') or '').strip()
        chapter = str(data.get('chapter') or '').strip() or '001'
        seed = str(data.get('seed') or '').strip()
        hint = str(data.get('hint') or '').strip()
        try:
            variants = int(data.get('variants') or 2)
        except (TypeError, ValueError):
            variants = 2
        variants = max(1, min(INSPIRE_BUDGET['max_variants'], variants))
        if not seed:
            self._json({'ok': False, 'error': 'seed 不能为空（先写一句你想展开的话）'}, 400)
            return
        if len(seed) > INSPIRE_BUDGET['seed']:
            self._json({'ok': False, 'error': 'seed 太长（上限 %d 字）' % INSPIRE_BUDGET['seed']}, 400)
            return
        if not os.path.isdir(os.path.join(PROJECTS, book)):
            self._json({'ok': False, 'error': '书不存在：%s' % book}, 404)
            return
        model_req = str(data.get('model') or '').strip() or 'deepseek-flash'
        spec = polish_spec(model_req) or polish_spec('deepseek-flash')
        cfg = polish_cfg_for(spec, 'disabled')
        cfg['max_tokens'] = 2000
        ctx = inspire_context(book, chapter)

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()

        def send(ev):
            try:
                self.wfile.write(('data: ' + json.dumps(ev, ensure_ascii=False) + chr(10) + chr(10)).encode('utf-8'))
                self.wfile.flush()
                return True
            except Exception:
                return False

        send({'type': 'start', 'variants': variants, 'model': spec.get('id'),
              'context': {'before': bool(ctx.get('before')), 'cast': bool(ctx.get('cast')),
                          'ledger': bool(ctx.get('ledger'))},
              'budget': INSPIRE_BUDGET})
        results = []
        for idx in range(1, variants + 1):
            prompt = inspire_prompt(book, seed, hint, ctx, idx, variants)
            try:
                resp = CO.chat(dict(cfg, temperature=0.9 if idx > 1 else 0.8),
                               [{'role': 'user', 'content': prompt}])
            except Exception as e:
                send({'type': 'error', 'variant': idx, 'message': report(e)})
                continue
            billing = resp.get('_billing') or {}
            text = CO.sanitize_worker_text(CO._extract_content(resp) or '').strip()
            if not text:
                send({'type': 'error', 'variant': idx, 'message': '模型空输出'})
                continue
            results.append(text)
            send({'type': 'variant', 'index': idx, 'text': text,
                  'verify': inspire_verify(book, text),
                  'tokens': int(billing.get('total_tokens') or 0),
                  'cny': round(float(billing.get('total_cny') or 0), 6)})
            log_usage('inspire', book, chapter, billing, {'variant': idx})
        send({'type': 'done', 'variants': len(results)})

    def _polish(self, data):
        """POST /api/polish —— 润色现有文字（SSE）。不 commit、不 precheck、不改章节状态。"""
        book = str(data.get('book') or '').strip()
        chapter = str(data.get('chapter') or '').strip()
        text = str(data.get('text') or '')
        scope = str(data.get('scope') or 'selection').strip()
        instruction = str(data.get('instruction') or '').strip()
        if scope not in ('selection', 'chapter'):
            self._json({'ok': False, 'error': 'scope 只能是 selection 或 chapter'}, 400)
            return
        if not text.strip():
            self._json({'ok': False, 'error': 'text 不能为空（先选中一段或在码字区写点东西）'}, 400)
            return
        if len(text) > 20000:
            self._json({'ok': False, 'error': '一次最多润色 20000 字，请分段'}, 400)
            return
        if not instruction:
            instruction = '让句子更顺，去掉明显的冗余'

        # 模型可选（YG：客户要能挑润色模型）；默认 flash，快且便宜
        model_req = str(data.get('model') or '').strip() or 'deepseek-flash'
        spec = polish_spec(model_req)
        if not spec:
            self._json({'ok': False, 'error': 'model 不在可选清单里',
                        'allowed': [m['id'] for m in POLISH_MODELS],
                        'models_endpoint': '/api/polish/models'}, 400)
            return
        model = spec['id']
        fallback_model = 'deepseek-flash'
        prompt = ('你是《%s》的作者，正在改自己的稿子。\n\n'
                  '下面是一段正文，请按「%s」改写。\n\n'
                  '铁律：\n'
                  '- 只改表达，不改情节、不改人物、不改信息\n'
                  '- 保持原有的叙述节奏和句子长度习惯\n'
                  '- 不要加形容词堆砌，不要"文学化"\n'
                  '- 如果原文有口语/方言/破句，保留\n'
                  '- 字数接近原文（默认 ±10%%；若 instruction 要求增删细节，按 instruction 走，最多 1.5 倍）\n'
                  '- 直接输出改后的全文，不要解释、不要标注改了什么\n\n'
                  '【原文】\n%s' % (book or '这本书', instruction, text))
        # 关思考策略按厂商分流（实测：glm/kimi 不认 thinking:disabled，只认 reasoning_effort:low）
        cfg = polish_cfg_for(spec, spec.get('thinking') or 'disabled')
        cfg['max_tokens'] = max(1200, int(len(text) * 2.2))

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()

        def send(ev):
            try:
                self.wfile.write(('data: ' + json.dumps(ev, ensure_ascii=False) + '\n\n').encode('utf-8'))
                self.wfile.flush()
                return True
            except Exception:
                return False

        # 2026-11-17 修 P0：原三行（if not send(ev): raise）缩进错位成了 send() 内的死代码，
        # 导致 _polish 作用域里没有 send_or_die → 真实 SSE 首帧后 NameError（ui-panels 报的）
        def send_or_die(ev):
            if not send(ev):
                raise ClientGone()

        send({'type': 'start', 'scope': scope, 'chars_in': len(text),
              'instruction': instruction, 'model': model,
              'fallback_model': fallback_model,
              'book': book, 'chapter': chapter})

        out = []
        try:
            _seen = [0]

            def on_delta(kind, piece):
                if kind != 'content':
                    return                      # 润色不显示思考
                out.append(piece)
                _seen[0] += 1
                if _seen[0] % 10 == 1 and _peer_closed(self.connection):
                    raise ClientGone()
                send_or_die({'type': 'delta', 'text': piece})
            used_model = model
            fell_back = False
            # 策略升级链：首选策略 → 另一种 → 不带参数 → 最后换 flash
            chain = [spec.get('thinking') or 'disabled']
            for alt in ('reasoning_low', 'disabled', 'none'):
                if alt not in chain:
                    chain.append(alt)
            resp = None
            for strategy in chain:
                resp = CO.chat_stream(polish_cfg_for(spec, strategy),
                                      [{'role': 'user', 'content': prompt}],
                                      on_delta=on_delta)
                if ''.join(out).strip():
                    break
            if not ''.join(out).strip():        # 兜底：换便宜模型再来一次
                flash = polish_spec('deepseek-flash')
                used_model = flash['id']
                fell_back = True
                resp = CO.chat_stream(polish_cfg_for(flash, 'disabled'),
                                      [{'role': 'user', 'content': prompt}],
                                      on_delta=on_delta)
            billing = resp.get('_billing') or {}
            send({'type': 'usage',
                  'prompt_tokens': int(billing.get('prompt_tokens') or 0),
                  'completion_tokens': int(billing.get('completion_tokens') or 0),
                  'total_cny': round(float(billing.get('total_cny') or 0), 6),
                  'usage_estimated': bool(billing.get('usage_estimated'))})
            log_usage('polish', book, chapter, billing)
        except ClientGone:
            _log('润色被客户端中断：book=%s ch=%s 已收 %d 字'
                 % (book or '-', chapter or '-', len(''.join(out))))
            return
        except Exception as e:
            ev = {'type': 'error', 'message': str(e)[:200], 'chars_out': len(''.join(out)),
                  'model': locals().get('used_model', model)}
            if isinstance(e, getattr(CO, 'GatewayAuthError', ())):
                ev['auth'] = True
            send(ev)
            return
        result = ''.join(out).strip()
        if not result:
            send({'type': 'error', 'message': '模型没有输出（可换一句 instruction 再试）', 'chars_out': 0})
            return
        send({'type': 'done', 'chars_in': len(text), 'chars_out': len(result),
              'ratio': round(len(result) / max(1, len(text)), 2),
              'model': used_model, 'model_fallback': fell_back})

    def _review_config(self, data):
        """POST /api/review/config —— 把审稿人配置写回 reviewers.yaml（带备份，行级补丁）。"""
        import re as _re
        path = os.path.join(ROOT, 'config', 'reviewers.yaml')
        if not os.path.isfile(path):
            self._json({'ok': False, 'error': 'reviewers.yaml 不存在'}, 404)
            return
        want = {}
        for r in (data.get('reviewers') or []):
            if isinstance(r, dict) and r.get('id'):
                want[str(r['id'])] = r
        mode = str(data.get('mode') or '').strip().lower()
        if not want and mode not in ('vote', 'merge', 'union'):
            self._json({'ok': False, 'error': '没有可写入的变更（reviewers 或 mode）'}, 400)
            return
        try:
            with open(path, encoding='utf-8') as f:
                lines = f.read().split('\n')
        except OSError as e:
            self._json({'ok': False, 'error': '读取失败：%s' % e}, 500)
            return

        cur = None
        out = []
        for ln in lines:
            m = _re.match(r'^\s*-\s*id:\s*(\S+)\s*$', ln)
            if m:
                cur = m.group(1)
                out.append(ln)
                continue
            if _re.match(r'^\s{0,2}[a-z_]+:', ln) and not ln.startswith('  '):
                if _re.match(r'^mode:', ln) and mode in ('vote', 'merge', 'union'):
                    out.append('mode: %s' % mode)
                    continue
                if _re.match(r'^gate:', ln):
                    cur = None
                out.append(ln)
                continue
            if cur and cur in want:
                cfg_r = want[cur]
                if _re.match(r'^\s+model:', ln) and cfg_r.get('model'):
                    indent = ln[:len(ln) - len(ln.lstrip())]
                    out.append('%smodel: %s' % (indent, cfg_r['model']))
                    continue
                if _re.match(r'^\s+enabled:', ln) and 'enabled' in cfg_r:
                    indent = ln[:len(ln) - len(ln.lstrip())]
                    out.append('%senabled: %s' % (indent, 'true' if cfg_r.get('enabled') else 'false'))
                    continue
                if _re.match(r'^\s+weight:', ln) and 'weight' in cfg_r:
                    indent = ln[:len(ln) - len(ln.lstrip())]
                    out.append('%sweight: %s' % (indent, int(cfg_r['weight'])) )
                    continue
            out.append(ln)

        bak = path + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
        try:
            with open(bak, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(out))
            os.replace(tmp, path)
        except OSError as e:
            self._json({'ok': False, 'error': '写入失败：%s' % e}, 500)
            return
        import reviewers as RV
        cfg = RV.load_config(force=True)
        self._json({'ok': True, 'backup': os.path.basename(bak),
                    'mode': cfg.get('mode'),
                    'reviewers': [{'id': r.get('id'), 'model': r.get('model'),
                                   'enabled': bool(r.get('enabled', True))}
                                  for r in RV.reviewers_of(cfg)]}, 200)

    def _write_stream(self, data):
        """POST /api/write —— 写作层流式输出（SSE）"""
        book = str(data.get('book') or '').strip()
        chapter = str(data.get('chapter') or '').strip()
        prompt = str(data.get('prompt') or '').strip()
        if not book or not chapter:
            self._json({'ok': False, 'error': 'book 和 chapter 必填'}, 400)
            return
        if not os.path.isdir(os.path.join(PROJECTS, book)):
            self._json({'ok': False, 'error': '书不存在：%s' % book}, 404)
            return
        ch = ST.chapter_no(chapter) or '000'
        mode = str(data.get('mode') or 'replace').strip().lower()
        if mode not in ('replace', 'append'):
            self._json({'ok': False, 'error': 'mode 只能是 replace 或 append'}, 400)
            return
        # from_layer：指定从第 N 层起跑。缺省（不传 / 传空）= 老路径，一行都不变。
        _from_raw = str(data.get('from_layer') or '').strip()
        _from_key = ''
        if _from_raw:
            try:
                _from_key = CO.resolve_role(_from_raw) or ''
            except Exception:
                _from_key = ''
            if _from_key not in CO.LAYER_ORDER:
                self._json({'ok': False, 'error': '分层重跑的层名不对：%s（可选 L1–L4）' % _from_raw,
                            'layers': list(CO.LAYER_ORDER),
                            'hint': '可用：%s（也认中文：研究/思考/写作/质检）'
                                    % ' / '.join(CO.LAYER_ORDER)}, 400)
                return
        if not prompt:
            prompt = '写第 %s 章正文。' % ch

        # 第 2 保险：便宜粗筛（纯本地规则，零模型调用）—— 脏输入不进贵模型
        try:
            _stage_now = ST.get_stage(book, ch)
        except Exception:
            _stage_now = ''
        _screen = precheck_input.screen_write(book, chapter, prompt, mode, root=PROJECTS,
                                        force=bool(data.get('force')), stage=_stage_now)
        if not _screen['ok']:
            self._json({'ok': False,
                        'error': '前置检查未通过：' + _screen['blocked'][0]['reason'],
                        'screen': _screen,
                        'hint': '按 screen.blocked 补全后再写；确实要写就带 force=true'}, 400)
            return

        # 现有章节文件（append 要用；replace 也会覆盖它，写盘前会备份）
        fname = resolve_chapter_file(book, ch)
        rel = os.path.join('projects', book, '章节', fname)
        existing = ''
        abs_rel = os.path.join(PROJECTS, book, '章节', fname)
        try:
            with open(abs_rel, encoding='utf-8') as f:
                existing = f.read()
        except OSError:
            existing = ''
        mode_given = bool(str(data.get('mode') or '').strip())
        have = len(existing.strip())
        # from_layer 是「重跑某一层」，这一章本来就有正文，不拦
        if have > 200 and not bool(data.get('force')) and not mode_given and not _from_key:
            self._json({'ok': False, 'error': 'chapter_not_empty',
                        'message': '这一章已有 %d 字，直接写会覆盖掉' % have,
                        'chars': have, 'path': rel.replace(os.sep, '/'),
                        'options': [
                            {'id': 'replace', 'label': '覆盖（当前内容会先备份）',
                             'backup': True},
                            {'id': 'append', 'label': '接着往下写（追加）'},
                            {'id': 'cancel', 'label': '算了'}],
                        'can_force': True}, 400)
            return
        # 2026-11-17 开源转向：付费闸已关闭。不再拦截任何章节；
        # 成本仍逐次记进账本（kind="usage"），用于账单页的成本透明，不做收费。
        _notes = data.get('notes')
        if isinstance(_notes, list) and _notes:
            _lines = [str(x).strip() for x in _notes if str(x).strip()][:8]
            if _lines:
                prompt = (prompt + '\n\n【审稿意见（逐条处理，改完不许再犯）】\n'
                          + '\n'.join('- ' + x for x in _lines))
        if mode == 'append':
            if not existing.strip():
                self._json({'ok': False, 'error': '这一章还没有正文，先写正文才能接着写'}, 400)
                return
            tail = existing.strip()[-1200:]
            prompt = (prompt + '\n\n【本章已有正文（请接着往下写，不要重复已有内容）】\n' + tail)

        layer = CO.resolve_layer('writing') or {}
        if not layer.get('enabled', True):
            self._json({'ok': False, 'error': '写作层已关闭（layers.yaml enabled: false）'}, 400)
            return
        model = layer.get('model') or ''
        # Step 2 重点章判定：卷末 / 黄金三章 换强模型（配置在 config/writing_tiers.json）
        tier_name, tier_reason, tier_conf = 'normal', '', {}
        try:
            import tier as TIER
            tier_name, tier_reason, tier_conf = TIER.resolve_tier(book, ch)
            if tier_conf.get('model'):
                model = tier_conf['model']
        except Exception:
            pass
        cfg = CO.load_cfg()
        system = CO.WORKER_SYSTEM.get('writing') or ''
        # 套话禁令：四层写章走的是这里，不是 chat_worker —— 两处都要注入
        try:
            _ban = CO.cliche_ban_block()
            if _ban:
                system = (system + _ban).strip()
        except Exception:
            pass
        target = layer.get('target_words')
        ctx_info = {}
        hit = {}
        try:
            import write_context as WC
            ctx = WC.build_context(book, ch, extra_hint=prompt)
            if ctx.get('system'):
                system += '\n\n' + ctx['system']
                hit = ctx.get('sections') or {}
                ctx_info = {'chars': ctx.get('chars'), 'hit': hit}
        except Exception as e:
            ctx_info = {'error': report(e)}

        # 资料完整性门槛：客户「从零写」之前先看他有没有料
        NAME = {'characters': '角色卡', 'prev': '前情正文', 'outline': '章纲',
                'power': '力量体系', 'summaries': '章节摘要', 'states': '角色状态'}
        ch_int = int(ch) if str(ch).isdigit() else 0
        missing = []
        if not hit.get('characters'):
            missing.append('characters')
        if ch_int > 1 and (hit.get('prev') or 0) < 1:
            missing.append('prev')
        advised = [k for k in ('outline', 'power', 'summaries') if not hit.get(k)]
        force = bool(data.get('force'))
        if missing and not force and not _from_key:   # 重跑某层不是「从零写」，不卡资料门槛
            self._json({'ok': False, 'error': '资料不全，先补齐再写',
                        'missing': missing, 'advised': advised,
                        'hint': ('去左栏「设定库」补一张角色卡；'
                                 '如果是新项目，先在「大纲」里写这一章要写什么。'
                                 '（缺：%s）' % '、'.join(NAME.get(m, m) for m in missing)),
                        'context': {'hit': hit},
                        'can_force': True}, 400)
            return
        # 缓存预检：前面的层没落盘就不能假装成功（先回 SSE error，再 return，不写任何章节文件）
        if _from_key:
            _idx = list(CO.LAYER_ORDER).index(_from_key)
            _need = list(CO.LAYER_ORDER)[:_idx]
            _miss = [L for L in _need if layer_cache_load(book, ch, L) is None]
            if _miss:
                _msg = '没有第 %d 层之前的缓存，得从头跑' % (_idx + 1)
                _log('from_layer 缓存缺失：book=%s ch=%s from=%s 缺=%s'
                     % (book, ch, _from_key, ','.join(_miss)))
                _ev = {'type': 'error', 'text': _msg, 'message': _msg,
                       'from_layer': _from_key, 'cached': False,
                       'missing': _miss, 'chars': 0}
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('X-Accel-Buffering', 'no')
                self.end_headers()
                try:
                    self.wfile.write(('data: ' + json.dumps(_ev, ensure_ascii=False)
                                      + '\n\n').encode('utf-8'))
                    self.wfile.flush()
                except Exception:
                    pass
                return
        warnings = []
        if missing:
            warnings.append('资料不全：缺少%s，生成结果可能跑偏'
                            % '、'.join(NAME.get(m, m) for m in missing))
        if advised:
            warnings.append('建议补充：%s' % '、'.join(NAME.get(a, a) for a in advised))
        if target:
            system += ('\n\n【字数要求】本章正文不少于 %s 字（中文字符）。写完先数字数：'
                       '不够就继续写，补环境、动作、心理、对话，用具体场面补够，'
                       '不要用概述、总结或"时间流逝"带过。' % target)
        messages = [{'role': 'system', 'content': system},
                    {'role': 'user', 'content': prompt}]
        call_cfg = {'model': model, 'temperature': layer.get('temperature', 0.8)}
        if tier_conf.get('max_tokens'):
            call_cfg['max_tokens'] = int(tier_conf['max_tokens'])
        if tier_conf.get('thinking') is True:
            call_cfg['extra_body'] = {'thinking': {'type': 'enabled'}}
        if layer.get('max_tokens'):
            call_cfg['max_tokens'] = int(layer['max_tokens'])
        if layer.get('thinking') is False:
            call_cfg['extra_body'] = {'thinking': {'type': 'disabled'}}
        if not _from_key:      # from_layer 走 chat_worker（内部自己记 prompt），这里不重复 dump
            _dump_worker_prompt('writing', model, system, prompt, call_cfg, source='api/write')

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()

        def send(ev):
            try:
                self.wfile.write(('data: ' + json.dumps(ev, ensure_ascii=False) + '\n\n').encode('utf-8'))
                self.wfile.flush()
                return True
            except Exception:
                return False

        def send_or_die(ev):
            if not send(ev):
                raise ClientGone()

        prev_stage = (ST.get_stage(book, ch) or 'draft')
        dry_run = bool(data.get('dry_run'))
        send({'type': 'start', 'book': book, 'chapter': ch, 'model': model,
              'layer': layer.get('label') or 'writing', 'target_words': target, 'mode': mode,
              'context': ctx_info, 'prev_stage': prev_stage, 'dry_run': dry_run,
              'warnings': warnings, 'forced': bool(missing and force),
              'from_layer': _from_key or None})
        send({'type': 'stage', 'stage': 'working',
              'label': ('%s起跑' % layer_label(_from_key)) if _from_key else '写作中'})
        if not dry_run:                       # dry_run 不动章节状态
            _set_stage({'book': book, 'chapter': ch}, 'working',
                       reason=('从%s起跑' % layer_label(_from_key)) if _from_key else '写作层流式中',
                       source='writing', action='review')

        text = ''
        partial = []
        used_stream = bool(layer.get('stream', True))
        billing = {}
        _t0 = time.time()
        try:
            if _from_key:
                # 分层重跑：前面的层读 .layers 缓存，只跑 from_layer 及其后的层
                text, _agg = run_layer_chain(book, ch, _from_key, cfg, prompt, send,
                                             existing=existing)
                billing = dict(_agg)
                used_stream = False
                send({'type': 'usage',
                      'prompt_tokens': int(billing.get('prompt_tokens') or 0),
                      'completion_tokens': int(billing.get('completion_tokens') or 0),
                      'total_tokens': int(billing.get('total_tokens') or 0),
                      'total_cny': round(float(billing.get('total_cny') or 0), 6),
                      'usage_estimated': False, 'tier': tier_name,
                      'tier_reason': tier_reason,
                      'tier_model': (model if tier_name != 'normal' else ''),
                      'from_layer': _from_key})
                log_usage('write', book, ch, billing)
            else:
                if used_stream:
                    _seen = [0]

                    def on_delta(kind, piece):
                        if kind == 'content':
                            partial.append(piece)
                        _seen[0] += 1
                        if _seen[0] % 10 == 1 and _peer_closed(self.connection):
                            raise ClientGone()
                        send_or_die({'type': 'delta', 'kind': kind, 'text': piece})
                    resp = CO.chat_stream(call_cfg, messages, on_delta=on_delta)
                else:
                    resp = CO.chat(call_cfg, messages)
                    text_part = CO.sanitize_worker_text(CO._extract_content(resp) or '')
                    if text_part:
                        send({'type': 'delta', 'kind': 'content', 'text': text_part})
                text = CO.sanitize_worker_text(CO._extract_content(resp) or '')
                billing = resp.get('_billing') or {}
                send({'type': 'usage',
                      'prompt_tokens': int(billing.get('prompt_tokens') or 0),
                      'completion_tokens': int(billing.get('completion_tokens') or 0),
                      'total_tokens': int(billing.get('total_tokens') or 0),
                      'total_cny': round(float(billing.get('total_cny') or 0), 6),
                      'usage_estimated': bool(billing.get('usage_estimated')), 'tier': tier_name, 'tier_reason': tier_reason, 'tier_model': (model if tier_name != 'normal' else '')})
                log_usage('write', book, ch, billing)
                # 层产出落盘：写作层（.layers/<章号>/writing.md + _meta.json）
                try:
                    layer_cache_save(book, ch, 'writing', text,
                                     layer_rec('writing', model,
                                               int((time.time() - _t0) * 1000),
                                               billing.get('total_tokens'),
                                               billing.get('total_cny'), len(text),
                                               {'prompt_tokens': int(billing.get('prompt_tokens') or 0),
                                                'completion_tokens': int(billing.get('completion_tokens') or 0),
                                                'source': 'api/write'}))
                except Exception as _ce:
                    _log('层产出落盘失败（%s/%s writing）：%s: %s'
                         % (book, ch, type(_ce).__name__, _ce))
        except ClientGone:
            # 客户端点了「停止」：立刻停流，不 precheck、不 commit、不写盘；只把状态复位
            _log('写章被客户端中断：book=%s ch=%s 已收 %d 字（dry_run=%s）'
                 % (book, ch, len(''.join(partial)), dry_run))
            if not dry_run:
                back = prev_stage if prev_stage in ('draft', 'awaiting', 'blocked', 'done') else 'draft'
                if back == 'working':
                    back = 'draft'
                _set_stage({'book': book, 'chapter': ch}, back, reason='客户中断',
                           source='writing', action='cancel', force=True)
            return
        except Exception as e:
            auth = isinstance(e, getattr(CO, 'GatewayAuthError', ()))
            reason = (str(e)[:40] if auth else '写章失败：' + human(e))
            # 失败不能把章节卡在 working：回到原状态（draft 还是 draft、awaiting 还是 awaiting）
            back = prev_stage if prev_stage in ('draft', 'awaiting', 'blocked', 'done') else 'draft'
            if back == 'working':        # working 是瞬时态，失败时不能停在它上面
                back = 'draft'
            if not dry_run:
                _set_stage({'book': book, 'chapter': ch}, back, reason=reason,
                           source='writing', action='retry', force=True)
            send({'type': 'stage', 'stage': back, 'reason': reason})
            ev = {'type': 'error', 'message': str(e)[:200], 'text': str(e)[:200],
                  'chars': len(''.join(partial)), 'partial': True,
                  'from_layer': _from_key or None}
            if auth:
                ev['auth'] = True          # 前端据此弹「重新登录」
            send(ev)
            return

        if not text.strip():
            reason = '写章失败：模型没有输出正文'
            _set_stage({'book': book, 'chapter': ch}, 'blocked', reason=reason,
                       source='writing', action='retry')
            send({'type': 'stage', 'stage': 'blocked', 'reason': reason})
            send({'type': 'error', 'message': reason, 'chars': 0})
            return

        body = text if mode == 'replace' else (existing.rstrip() + '\n\n' + text)
        # 只有完整正文才做机检 + 入账（流片段不参与）
        try:
            import precheck as PC
            pre = PC.precheck(book, ch, body)
        except Exception:
            pre = {'passed': True, 'blocking': [], 'warnings': [], 'score': 100}
        if not pre.get('passed'):
            reason = '机检未过：%s' % (pre['blocking'][0]['detail'] if pre.get('blocking') else '未知')
            draft_rel = ''
            if text.strip():
                # 没过关的正文也别丢：存成 .draft 供客户查看/自取（不进章节列表）
                try:
                    body_text, _w = CO.strip_leading_heading(text, ch)
                    draft_name = fname + '.draft'
                    draft_abs = os.path.join(PROJECTS, book, '章节', draft_name)
                    os.makedirs(os.path.dirname(draft_abs), exist_ok=True)
                    _tag = keep_scene_tag(abs_rel)
                    with open(draft_abs, 'w', encoding='utf-8') as f:
                        f.write(_tag + '# 第 %s 章（机检未过·草稿）\n\n%s\n'
                                % (ch.lstrip('0') or ch, body_text))
                    draft_rel = 'projects/%s/章节/%s' % (book, draft_name)
                except OSError:
                    draft_rel = ''
            if not dry_run:
                _set_stage({'book': book, 'chapter': ch}, 'blocked', reason=reason,
                           source='writing', action='retry')
            send({'type': 'stage', 'stage': 'blocked', 'reason': reason})
            send({'type': 'error', 'message': reason, 'chars': len(text), 'precheck': pre,
                  'draft': draft_rel or None,
                  'next': next_options(pre, {})})
            return

        if dry_run:
            # 只写出来给客户看：不写盘、不 commit、不改章节状态、不备份
            if tier_name != 'normal':
                send({'type': 'tier', 'tier': tier_name, 'reason': tier_reason, 'model': model})
            send({'type': 'done', 'dry_run': True, 'chars': len(text), 'mode': mode,
                  'path': rel.replace(os.sep, '/'), 'precheck': pre,
                  'next': {'stage': 'preview', 'options': [
                      {'id': 'apply', 'label': '用这个（写回文件）', 'enabled': True},
                      {'id': 'discard', 'label': '保留原文', 'enabled': True}]},
                  'note': 'dry_run：没有写盘、没有 commit、章节状态未变'})
            return

        try:
            os.makedirs(os.path.dirname(abs_rel), exist_ok=True)
            HI.snapshot(book, ch, 'ai-write')      # 版本历史：覆盖前存旧稿（只返回 ok=False，不阻断写盘）
            backup_name = ''
            if os.path.exists(abs_rel):          # 覆盖前留备份
                try:
                    with open(abs_rel, encoding='utf-8') as f:
                        old = f.read()
                    backup_name = fname + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
                    with open(os.path.join(PROJECTS, book, '章节', backup_name), 'w',
                              encoding='utf-8') as f:
                        f.write(old)
                except OSError:
                    backup_name = ''
            head_warning = ''
            if mode == 'replace':
                body_text, head_warning = CO.strip_leading_heading(text, ch)
                _tag = keep_scene_tag(abs_rel)          # 改稿不清场景标签
                with open(abs_rel, 'w', encoding='utf-8') as f:
                    f.write(_tag + '# 第 %s 章\n\n%s\n' % (ch.lstrip('0') or ch, body_text))
            else:
                with open(abs_rel, 'w', encoding='utf-8') as f:
                    f.write(body + '\n')
        except Exception as e:
            send({'type': 'error', 'message': '正文写盘失败：%s' % e, 'chars': len(text)})
            return
        # 付费闸记账：正文已落盘才算消耗一章（dry_run / 机检未过 / 中断都走不到这里）
        try:
            if not _from_key and int(ch) > int(PG.load_cfg().get('free_chapters') or 0):
                _gw_model = model
                try:
                    _gw_model = CO.map_model(CO.gateway_cfg(), model) or model
                except Exception:
                    _gw_model = model
                PG.consume(1, chapter=ch, ref='write:%s:%s' % (book, ch), model=_gw_model,
                           usage={'prompt_tokens': int(billing.get('prompt_tokens') or 0),
                                  'completion_tokens': int(billing.get('completion_tokens') or 0),
                                  'total_tokens': int(billing.get('total_tokens') or 0)})
        except Exception as _be:
            _log('billing consume skipped：%s: %s' % (type(_be).__name__, _be))
        commit_info = {}
        try:
            import chapter_commit as CC
            commit_info = CC.commit_chapter(book, ch, body, precheck=pre)
        except Exception as e:
            commit_info = {'ok': False, 'error': report(e)}
        if commit_info.get('ok'):
            # 说真话：这条路径跑了 Step 2/3/4（重点章判定 + 写作 + 质检）。
            # Step 5 审稿团只在 pipeline=true 时跑；Step 1 的六问在 write_context 里（3/6 是真数据）。
            # Step 7 复检见 /api/chapter/recheck。
            reason = '已完成写作 + 质检，已入账 %d 条事件' % (commit_info.get('events') or 0)
            _set_stage({'book': book, 'chapter': ch}, 'awaiting', reason=reason,
                       source='writing', action='confirm')
            send({'type': 'stage', 'stage': 'awaiting', 'reason': reason})
        else:
            reason = '事实入账失败：%s' % (commit_info.get('error') or '未知')
            _set_stage({'book': book, 'chapter': ch}, 'blocked', reason=reason,
                       source='writing', action='retry')
            send({'type': 'stage', 'stage': 'blocked', 'reason': reason})
        # step 5 审稿团（只在 pipeline=true 时跑）。读取配置的审稿人，并行各出一份意见，
        # 然后用 extract_consensus 裁决成 必改/待定/忽略（规范第四节）。
        # 规范说「第 5 步必须人工」，所以这里只出清单，不替客户改稿。
        if data.get('pipeline'):
            try:
                import reviewers as RV
                send({'type': 'step', 'step': 5, 'name': '审稿团', 'status': 'running'})
                _team = RV.run_team(body, abs_rel, write=False)
                _cons = RV.extract_consensus(_team.get('reviewers') or [])
                send({'type': 'step', 'step': 5, 'name': '审稿团', 'status': 'done',
                      'detail': {'verdict': (_team.get('merged') or {}).get('verdict'),
                                 'reviewers': len(_team.get('reviewers') or []),
                                 'must_fix': _cons.get('must_fix') or [],
                                 'pending': _cons.get('pending') or [],
                                 'ignored_count': len(_cons.get('ignored') or []),
                                 'consensus_error': _cons.get('error')}})
            except Exception as e:
                send({'type': 'step', 'step': 5, 'name': '审稿团', 'status': 'failed',
                      'detail': {'error': report(e)}})

        # 承诺自动 touch：只有章纲明确指定（plan）才登记；auto 只提示不猜
        try:
            import write_context as WC
            import promises as PM
            _outline = WC._outline_struct(book, ch)
            _chosen, _src = WC._pick_promises(book, ch, _outline)
            _ids = [str(_p.get('编号') or '') for _p in (_chosen or []) if _p.get('编号')]
            if _src == 'plan' and _ids:
                for _pid in _ids:
                    PM.touch(book, _pid, ch, '推进', '四层写完后自动登记')
                send({'type': 'promises', 'ok': True, 'source': 'plan', 'touched': _ids})
            elif _ids:
                send({'type': 'promises', 'ok': True, 'source': 'auto', 'suggested': _ids,
                      'note': '自动挑的，没有自动登记；确认后在设定库手动 touch'})
            else:
                send({'type': 'promises', 'ok': True, 'source': 'none', 'touched': []})
        except Exception as _pe:
            send({'type': 'promises', 'ok': False, 'error': report(_pe)})

        # 角色状态表更新：六问第 2 问的数据源，失败不影响主流程
        try:
            import update_state as US
            _us = US.update_one(abs_rel, book)
            send({'type': 'role_state', 'ok': bool(_us.get('ok')),
                  'changed': _us.get('changed') or [],
                  'note': _us.get('note') or _us.get('error') or ''})
        except Exception as _e:
            send({'type': 'role_state', 'ok': False, 'error': report(_e)})

        if tier_name != 'normal':
            send({'type': 'tier', 'tier': tier_name, 'reason': tier_reason, 'model': model})
        send({'type': 'done', 'chars': len(body), 'added_chars': len(text), 'mode': mode,
              'path': rel.replace(os.sep, '/'),
              'commit': commit_info, 'precheck': pre,
              'backup': backup_name or None,
              'warnings': ([head_warning] if head_warning else []),
              'next': next_options(pre, commit_info),
              'stream': used_stream, 'from_layer': _from_key or None,
              'layer_stale': bool(billing.get('stale'))})

    def _review_run(self, data):
        import reviewers as RV
        """POST /api/review/run {path} 或 {book, chapter} —— SSE：reviewer_start / reviewer_done / team_done

        审稿团是「四层写完之后的用户决策点」，不是随时能跑的独立面板：
        章节状态不是 awaiting / done 时拒绝（避免审到半截稿）。
        """
        raw = data.get('path')
        book = str(data.get('book') or '').strip()
        chapter = str(data.get('chapter') or '').strip()
        if not raw and book and chapter:
            ch = ST.chapter_no(chapter)
            d = os.path.join(PROJECTS, book, '章节')
            hit = ''
            try:
                for f in sorted(os.listdir(d)):
                    if f.startswith(ch + '-') and f.endswith('.md') and '.bak' not in f:
                        hit = f
                        break
            except OSError:
                hit = ''
            if not hit:
                self._json({'ok': False, 'error': '这一章还没有正文文件：%s/%s' % (book, chapter)}, 404)
                return
            raw = 'projects/%s/章节/%s' % (book, hit)
        try:
            norm, full = safe_rel(raw, need_ext=('.md',))
        except PathError as e:
            self._json({'ok': False, 'error': str(e)}, 400)
            return
        if not os.path.isfile(full):
            self._json({'ok': False, 'error': 'not found', 'path': norm}, 404)
            return

        # 状态守卫：只有「写完了」的章才允许送审
        _b = ST.book_of_path(norm)
        _ch = ST.chapter_no(norm)
        if _b and _ch:
            _st = ST.get_stage(_b, _ch) or 'draft'
            if _st not in ('awaiting', 'done', 'blocked'):
                self._json({'ok': False, 'stage': _st,
                            'error': '这一章还没写完（状态：%s），先让 AI 写完再审' % _st}, 400)
                return
        mode = data.get('mode')
        max_tokens = data.get('max_tokens')
        # 临时覆盖：reviewers=[id...] 只跑这几位；models={id: model} 覆盖各自模型
        cfg_override = None
        only_ids = data.get('reviewers')
        models_override = data.get('models')
        if only_ids or models_override:
            try:
                cfg_override = RV.apply_reviewer_override(
                    RV.load_config(),
                    only_ids=[str(x) for x in only_ids] if isinstance(only_ids, list) else None,
                    models=models_override if isinstance(models_override, dict) else None)
            except Exception as e:
                self._json({'ok': False, 'error': 'review_override_invalid',
                            'detail': report(e)}, 400)
                return
        # 可选：角色卡 / 地图 / 上一章 / 章号（路径同样锁在 projects/ 内）
        extras = {}
        for key, ext in (('chars', ('.md',)), ('map', ('.md',)), ('prev', ('.md',))):
            val = data.get(key)
            if val:
                try:
                    _n, p = safe_rel(val, need_ext=ext)
                except PathError as e:
                    self._json({'ok': False, 'error': '%s: %s' % (key, e)}, 400)
                    return
                if not os.path.isfile(p):
                    self._json({'ok': False, 'error': '%s not found' % key, 'path': val}, 404)
                    return
                extras[key] = p
        # 调用方没传时自动补：角色卡 / 世界地图 / 上一章
        # （时间线、力量体系、伏笔、角色状态由 reviewers.py 按章节路径自己找）
        try:
            _bk = ST.book_of_path(norm)
            _cn = ST.chapter_no(norm)
            _sd = os.path.join(PROJECTS, _bk, '设定库') if _bk else ''
            if 'chars' not in extras and _sd:
                _p = os.path.join(_sd, '角色卡.md')
                if os.path.isfile(_p):
                    extras['chars'] = _p
            if 'map' not in extras and _sd:
                _p = os.path.join(_sd, '世界地图.md')
                if os.path.isfile(_p):
                    extras['map'] = _p
            if 'prev' not in extras and _bk and _cn:
                _dir = os.path.join(PROJECTS, _bk, '章节')
                _prev = ''
                try:
                    for _f in sorted(os.listdir(_dir)):
                        if not _f.endswith('.md') or '.bak' in _f:
                            continue
                        _n = _f.split('-')[0]
                        if _n.isdigit() and int(_n) < int(_cn):
                            _prev = os.path.join(_dir, _f)
                except OSError:
                    _prev = ''
                if _prev:
                    extras['prev'] = _prev
        except Exception:
            pass
        try:
            with open(full, encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError as e:
            self._json({'ok': False, 'error': 'read_failed', 'detail': str(e)}, 500)
            return

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()
        try:
            for ev in RV.iter_team(text, norm, mode=mode,
                                   max_tokens=int(max_tokens) if max_tokens else None,
                                   chars_path=extras.get('chars'),
                                   map_path=extras.get('map'),
                                   prev_path=extras.get('prev'),
                                   ch_override=data.get('ch'),
                                   cfg_override=cfg_override):
                if isinstance(ev, dict) and ev.get('type') == 'team_done':
                    try:
                        _t = ev.get('totals') or {}
                        log_usage('review', book, chapter, {'total_tokens': _t.get('tokens'), 'total_cny': _t.get('cny')})
                    except Exception:
                        pass
                self.wfile.write(('data: ' + json.dumps(ev, ensure_ascii=False) + '\n\n').encode('utf-8'))
                self.wfile.flush()
        except Exception as e:
            try:
                self.wfile.write(('data: ' + json.dumps(
                    {'type': 'error', 'text': report(e)},
                    ensure_ascii=False) + '\n\n').encode('utf-8'))
                self.wfile.flush()
            except Exception:
                pass

    # -------- 账户 / 用量 --------

    def _account_login(self, data):
        try:
            res = account_login(data.get('username'), data.get('password'))
        except PathError as e:
            self._json({'ok': False, 'error': 'bad_request', 'hint': str(e)}, 400)
            return
        except Exception as e:
            self._json({'ok': False, 'error': 'internal', 'hint': report(e)}, 200)
            return
        self._json(res, 200 if res.get('ok') else 401)

    def _account_balance(self, q):
        sid, _ = _get_session(self, q=q)
        try:
            res = account_balance(sid)
        except Exception as e:
            res = {'ok': False, 'error': 'internal', 'hint': report(e)}
        if not res.get('ok'):
            # R22：余额同样不能因上游登录态而失明 → 回退本地账本，标明来源
            try:
                _st = PG.status()
                self._json({'ok': True, 'source': 'local_ledger', 'balance': _st.get('balance'),
                            'remaining': _st.get('remaining'), 'tier': _st.get('tier'),
                            'free_chapters': _st.get('free_chapters'),
                            'gateway': {'ok': False, 'error': res.get('error')}}, 200)
                return
            except Exception:
                pass
        self._json(res, 200 if res.get('ok') else 401)

    def _account_usage(self, q):
        sid, _ = _get_session(self, q=q)
        limit = (q.get('limit') or ['20'])[0]
        try:
            res = account_usage(sid, limit)
        except Exception as e:
            res = {'ok': False, 'error': 'internal', 'hint': report(e)}
        if not res.get('ok'):
            # R22：网关 /api/log/self 会 401。计费/用量不能因为上游登录态而失明，
            # 回退到本地账本（append-only），并显式标注来源，前端据此区分口径。
            try:
                loc = PG.local_usage(limit)
                loc['gateway'] = {'ok': False, 'error': res.get('error'),
                                  'detail': res.get('detail'), 'hint': res.get('hint')}
                self._json(loc, 200)
                return
            except Exception as e:
                res['local_ledger_error'] = report(e)
        self._json(res, 200 if res.get('ok') else 401)

    # -------- 付费闸 / 账本（task-5） --------

    def _billing_status(self):
        try:
            self._json(PG.status(), 200)
        except Exception as e:
            self._json({'ok': False, 'error': 'internal',
                        'hint': report(e)}, 500)

    def _billing_topup(self, data):
        try:
            r = PG.topup(data.get('tier'), data.get('amount'), data.get('ref'),
                         data.get('chapters'))
        except Exception as e:
            self._json({'ok': False, 'error': 'internal',
                        'hint': report(e)}, 500)
            return
        if not r.get('ok'):
            self._json(r, 400)
            return
        if r.get('duplicate'):
            _log('billing topup duplicate ref=%s tier=%s（未加账）'
                 % (r.get('ref'), r.get('tier')))
        else:
            _log('billing topup ok ref=%s tier=%s amount=%s balance=%s'
                 % (r.get('ref'), r.get('tier'), r.get('amount'), r.get('balance')))
        self._json(r, 200)

    def _billing_refund(self, data):
        try:
            r = PG.refund(data.get('amount'), data.get('ref'), data.get('tier'),
                          data.get('chapters'))
        except Exception as e:
            self._json({'ok': False, 'error': 'internal',
                        'hint': report(e)}, 500)
            return
        if not r.get('ok'):
            self._json(r, 400)
            return
        _log('billing refund ref=%s amount=%s balance=%s'
             % (r.get('ref'), r.get('amount'), r.get('balance')))
        self._json(r, 200)

    def _account_setup(self, data):
        try:
            res = account_setup(data.get('username'), data.get('password'))
        except PathError as e:
            self._json({'ok': False, 'error': 'bad_request', 'hint': str(e)}, 400)
            return
        except Exception as e:
            self._json({'ok': False, 'error': 'internal',
                        'hint': report(e)}, 200)
            return
        code = 200 if res.get('ok') else (401 if res.get('error') in ('unauthorized',) else 200)
        self._json(res, code)

    def _account_token(self):
        try:
            self._json(account_token(), 200)
        except Exception as e:
            self._json({'ok': False, 'error': 'internal',
                        'hint': report(e)}, 200)

    def _gateway_status(self):
        g = CO.gateway_cfg(CFG)
        pricing = CO.gateway_pricing()
        saved = load_user_token()
        self._json({'enabled': bool(g['enabled']),
                    'base': g.get('base'),
                    'has_key': bool(g.get('downstream_key')),
                    'key_source': g.get('key_source'),
                    'need_login': bool(g.get('need_login')),
                    'login_hint': None if g.get('downstream_key') else '尚未登录：请先在软件里登录账号',
                    'token_ready': bool(saved and saved.get('token')),
                    'token_user': (saved or {}).get('username'),
                    'fee_rate': _fee_rate_of(g),
                    'quota_per_unit': pricing.get('quota_per_unit'),
                    'price': pricing.get('price'),
                    'models': sorted((pricing.get('models') or {}).keys())[:30],
                    'pricing_error': pricing.get('error'),
                    'sessions': _session_count()}, 200)

    def _config_reload(self):
        """GET /api/config/reload —— 手动强制重载（前端齿轮里可以挂个按钮）。"""
        before = (CFG.get('coordinator') or {}).get('model')
        ensure_cfg_fresh(force=True)
        after = (CFG.get('coordinator') or {}).get('model')
        self._json({'ok': CFG_STATE['error'] is None,
                    'changed': before != after,
                    'model_before': before,
                    'model_after': after,
                    'error': CFG_STATE['error'],
                    'reloads': CFG_STATE['reloads'],
                    'config_path': CFG_PATH,
                    'log': os.path.join(CO.LOG_DIR, 'config.log')}, 200)

    # -------- 配置引导 --------

    def _setup_status(self):
        try:
            self._json(setup_status(), 200)
        except Exception as e:
            self._json({'configured': False, 'error': report(e),
                        'providers': SETUP_PROVIDERS,
                        'local_ollama': {'detected': False, 'models': []}}, 200)

    def _setup_test(self, data):
        try:
            res = setup_test(data.get('endpoint'), data.get('api_key'), data.get('model'))
        except PathError as e:
            self._json({'ok': False, 'error': 'bad_request', 'hint': str(e)}, 400)
            return
        except Exception as e:
            self._json({'ok': False, 'error': 'internal', 'hint': report(e)}, 500)
            return
        self._json(res, 200)          # 业务失败也是 200，前端看 ok 字段

    def _settings_search(self, data):
        """POST /api/settings/search {enabled: bool} —— 联网搜索开关（默认关闭）。

        开着等于客户自己认可「用 Bing 的 RSS 做搜索源」这件事，所以要显式 true / false，
        不接受 "true"/1 这类模糊值，免得前端传错把开关写成开。
        """
        v = data.get('enabled')
        if not isinstance(v, bool):
            self._json({'ok': False, 'error': 'enabled 必须是 true / false'}, 400)
            return
        try:
            res = save_search_enabled(v)
        except OSError as e:
            self._json({'ok': False, 'error': 'write_failed', 'hint': str(e)}, 500)
            return
        self._json(res, 200 if res.get('ok') else 500)

    def _setup_save(self, data):
        try:
            res = setup_save(data.get('endpoint'), data.get('api_key'), data.get('model'),
                             data.get('gateway') if isinstance(data.get('gateway'), dict) else None)
        except PathError as e:
            self._json({'ok': False, 'error': 'bad_request', 'hint': str(e)}, 400)
            return
        except Exception as e:
            self._json({'ok': False, 'error': 'write_failed',
                        'hint': report(e)}, 500)
            return
        self._json(res, 200)

    def _project(self, data):
        name = data.get('name')
        try:
            path, err = create_project(name, data.get('genre', ''), data.get('author', ''))
        except PathError as e:
            self._json({'ok': False, 'error': 'bad_name', 'detail': str(e)}, 400)
            return
        if err == 'exists':
            self._json({'ok': False, 'error': 'exists', 'path': 'projects/' + safe_name(name).strip()}, 409)
            return
        self._json({'ok': True, 'path': path, 'created': True}, 200)

    def _save(self, data):
        content = data.get('content')
        if not isinstance(content, str):
            self._json({'ok': False, 'error': 'content 必须是字符串'}, 400)
            return
        if len(content) > MAX_SAVE_CHARS:
            self._json({'ok': False, 'error': 'too_large', 'chars': len(content),
                        'max_chars': MAX_SAVE_CHARS,
                        'hint': '单文件上限 %d 字，内容未写入，未做任何截断' % MAX_SAVE_CHARS}, 413)
            return
        norm, full = safe_rel(data.get('path', ''), need_ext=ALLOWED_EXT)
        force = bool(data.get('force'))
        if os.path.isdir(full):
            self._json({'ok': False, 'error': '路径是目录'}, 400)
            return
        old = None
        if os.path.exists(full):
            with open(full, encoding='utf-8', errors='replace') as f:
                old = f.read()
            if (not force and len(old) >= 200 and len(content) < len(old) * SHRINK_GUARD):
                self._json({'ok': False, 'error': 'content_shrunk',
                            'old_chars': len(old), 'new_chars': len(content),
                            'hint': '新内容不足原文一半，加 force=true 才覆盖'}, 409)
                return
        HI.snapshot_path(norm, 'revise')       # 版本历史：改稿写盘前存旧稿（非章节正文自动跳过）
        size = atomic_write(full, content)
        self._json({'ok': True, 'bytes': size, 'chars': len(content),
                    'path': norm, 'created': old is None,
                    'replaced_chars': len(old) if old is not None else 0}, 200)

    def _new_file(self, data):
        content = data.get('content', '')
        if not isinstance(content, str):
            self._json({'ok': False, 'error': 'content 必须是字符串'}, 400)
            return
        if len(content) > MAX_SAVE_CHARS:
            self._json({'ok': False, 'error': 'too_large', 'chars': len(content),
                        'max_chars': MAX_SAVE_CHARS, 'hint': '内容未写入，未做任何截断'}, 413)
            return
        norm, full = safe_rel(data.get('path', ''), need_ext=ALLOWED_EXT)
        if os.path.exists(full):
            self._json({'ok': False, 'error': 'exists', 'path': norm}, 200)
            return
        size = atomic_write(full, content)
        self._json({'ok': True, 'path': norm, 'bytes': size, 'chars': len(content)}, 200)

    # 场景标签：只改章节 md 头部那一行注释，正文一个字节都不动（实现见 scripts/scene_tag.py）
    def _scene_tag(self, q):
        rel = (q.get('path') or [''])[0]
        norm, full = safe_rel(rel, need_ext=ALLOWED_EXT)
        if not os.path.isfile(full):
            self._json({'ok': False, 'error': 'not found'}, 404)
            return
        self._json({'ok': True, 'path': norm, 'tag': scene_tag_lib().parse(full)}, 200)

    def _scene_tag_set(self, data):
        rel = data.get('path')
        norm, full = safe_rel(rel, need_ext=ALLOWED_EXT)
        if not os.path.isfile(full):
            self._json({'ok': False, 'error': 'not found'}, 404)
            return
        raw = data.get('tag')
        if raw is None:
            raw = data.get('raw')
        lib = scene_tag_lib()
        try:
            res = lib.set_tag(full, '' if raw is None else raw)
        except (OSError, ValueError) as e:
            self._json({'ok': False, 'error': '写场景标签失败：%s' % e}, 500)
            return
        self._json({'ok': True, 'path': norm, 'changed': res['changed'],
                    'tag': lib.parse(full)}, 200)

    # 读债 / 完结可行性：接的是 scripts/ 里的纯脚本，不重复实现一份
    def _debt(self, q):
        book = (q.get("book") or [""])[0]
        chapter = (q.get("chapter") or [""])[0]
        if not book:
            self._json({"ok": False, "error": "book 必填"}, 400)
            return
        try:
            lib = _script_lib("debt_view")
            rep = lib.build_debt(book, chapter or None)
        except Exception as e:
            self._json({"ok": False, "error": report(e)}, 500)
            return
        self._json(rep, 200 if rep.get("ok") else 404)

    def _completion(self, q):
        book = (q.get("book") or [""])[0]
        planned = (q.get("planned") or [""])[0]
        if not book:
            self._json({"ok": False, "error": "book 必填"}, 400)
            return
        try:
            p = os.path.join(ROOT, "core")
            if p not in sys.path:
                sys.path.insert(0, p)
            import completion as _c
            n = int(planned) if str(planned).isdigit() else None
            rep = _c.analyze(book, n, None)
            self._json({"ok": True, "report": rep, "text": _c.report(rep)}, 200)
        except Exception as e:
            self._json({"ok": False, "error": report(e)}, 500)

    # 删除：一律先进 data/.trash/<时间戳>/，客户后悔能捞回来
    def _trash_dir(self):
        stamp = time.strftime('%Y%m%d-%H%M%S')
        d = os.path.join(DATA_ROOT, '.trash', stamp)
        os.makedirs(d, exist_ok=True)
        return d, stamp

    # POST /api/file/rename {path, to} —— 同目录改名（章节错别字更正）
    def _rename_file(self, data):
        norm, full = safe_rel(data.get('path', ''), need_ext=ALLOWED_EXT)
        if not os.path.isfile(full):
            self._json({'ok': False, 'error': 'not found', 'path': norm}, 404)
            return
        to = str(data.get('to') or '').strip()
        if not to:
            self._json({'ok': False, 'error': '新名字不能为空'}, 400)
            return
        if '/' in to or chr(92) in to or to in ('.', '..'):
            self._json({'ok': False, 'error': '新名字里不能带路径'}, 400)
            return
        if not to.lower().endswith('.md'):
            to = to + '.md'
        target = os.path.join(os.path.dirname(full), to)
        if _canon(target) != _canon(full) and os.path.exists(target):
            self._json({'ok': False, 'error': 'exists', 'to': to}, 200)
            return
        try:
            os.rename(full, target)
        except OSError as e:
            self._json({'ok': False, 'error': report(e)}, 500)
            return
        new_rel = norm.rsplit('/', 1)[0] + '/' + to
        # 章节状态跟着搬家：旧编号复位，新编号继承
        try:
            _b = ST.book_of_path(norm)
            _old = ST.chapter_no(norm)
            _new = ST.chapter_no(new_rel)
            if _b and _old and _new and _old != _new:
                _st = ST.get_stage(_b, _old) or 'draft'
                ST.set_stage(_b, _new, _st, reason='章节已重命名', source='manual', action='confirm', force=True)
                ST.set_stage(_b, _old, 'draft', reason='章节已重命名', source='manual', action='confirm', force=True)
        except Exception:
            pass
        self._json({'ok': True, 'path': new_rel, 'from': norm, 'to': to}, 200)
    # POST /api/file/delete {path} —— 只允许删「章节」里的正文
    def _delete_file(self, data):
        norm, full = safe_rel(data.get('path', ''), need_ext=ALLOWED_EXT)
        if not os.path.isfile(full):
            self._json({'ok': False, 'error': 'not found', 'path': norm}, 404)
            return
        if '/章节/' not in norm:
            self._json({'ok': False, 'error': '只允许从「章节」里删除正文文件'}, 400)
            return
        try:
            trash, stamp = self._trash_dir()
            target = os.path.join(trash, norm.replace('/', os.sep))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(full, target)
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)
            return
        try:
            _b = ST.book_of_path(norm)
            _c = ST.chapter_no(norm)
            if _b and _c:
                ST.set_stage(_b, _c, 'draft', reason='文件已删除', source='manual', action='confirm', force=True)
        except Exception:
            pass
        self._json({'ok': True, 'path': norm, 'trash': '.trash/' + stamp}, 200)

    # POST /api/project/delete {name} —— 整本书移进 .trash
    def _delete_project(self, data):
        name = safe_name(data.get('name')).strip()
        d = os.path.join(PROJECTS, name)
        if not os.path.isdir(d):
            self._json({'ok': False, 'error': 'not found', 'name': name}, 404)
            return
        try:
            trash, stamp = self._trash_dir()
            shutil.move(d, os.path.join(trash, name))
        except Exception as e:
            self._json({'ok': False, 'error': report(e)}, 500)
            return
        self._json({'ok': True, 'name': name, 'trash': '.trash/' + stamp}, 200)
    def _chat(self, data):
        data = data if isinstance(data, dict) else {}
        # 附带文件在开流之前读：读不了就只发一条 error 事件，不花模型钱、也不把半截消息送进 agent。
        # （前端等整条流读完才解析，错误必须是流里的事件，不能只走 HTTP 状态码。）
        preamble, ferr, _fmeta = _asst_files_preamble(data.get('files'))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()

        def _sse(ev):
            self.wfile.write(('data: ' + json.dumps(ev, ensure_ascii=False) + '\n\n').encode('utf-8'))
            self.wfile.flush()

        if ferr:
            try:
                _sse({'type': 'error', 'text': ferr})
            except Exception:
                pass
            return
        message = str(data.get('message') or '')
        if preamble:
            message = preamble + '\n\n' + message
        # 章节目标只认客户自己打的那句话（见 run_agent 里的 _stage_text）
        seed = dict(data)
        seed['_stage_text'] = str(data.get('message') or '')
        try:
            for ev in run_agent(message, seed):
                _sse(ev)
        except Exception as e:
            try:
                _sse({'type': 'error', 'text': report(e)})
            except Exception:
                pass


def _usage_add(acc, b):
    if not b:
        return
    for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        acc[k] += int(b.get(k) or 0)
    for k in ('quota', 'official_cny', 'fee_cny', 'total_cny'):
        acc[k] += float(b.get(k) or 0)
    acc['steps'] += 1
    if b.get('model'):
        acc['models'].add(b['model'])
    if b.get('request_id'):
        acc['request_id'] = b['request_id']
    if b.get('fee_rate'):
        acc['fee_rate'] = b['fee_rate']


def _usage_out(acc):
    if not acc['steps']:
        return None
    return {'prompt_tokens': acc['prompt_tokens'],
            'completion_tokens': acc['completion_tokens'],
            'total_tokens': acc['total_tokens'],
            'quota': round(acc['quota'], 2),
            'official_cny': round(acc['official_cny'], 6),
            'fee_cny': round(acc['fee_cny'], 6),
            'total_cny': round(acc['total_cny'], 6),
            'fee_rate': acc['fee_rate'],
            'steps': acc['steps'],
            'models': sorted(acc['models']),
            'layers': acc.get('layers') or [],
            'request_id': acc.get('request_id')}


# ---------------- 登录（与插件 /novelapp/login 等价） ----------------
LOGIN_CACHE = {'at': 0.0, 'token_prefix': '', 'data': None}


def _gw_base():
    g = CO.gateway_cfg()
    return str(g.get('base') or 'http://127.0.0.1:3000/v1').rstrip('/')


def _http_json(url, token, payload=None, timeout=15):
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=body, method='POST' if body else 'GET',
                          headers={'Content-Type': 'application/json',
                                   'Authorization': 'Bearer ' + token})
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8', 'replace'))
    except HTTPError as e:
        raw = b''
        try:
            raw = e.read()
        except Exception:
            pass
        try:
            detail = json.loads(raw.decode('utf-8', 'replace'))
        except Exception:
            detail = {'error': {'message': raw.decode('utf-8', 'replace')[:200]}}
        return e.code, detail
    except Exception as e:
        return 0, {'error': {'message': report(e)}}


def _mask_token(t):
    if not t:
        return ''
    return t[:6] + '…' + t[-4:] if len(t) > 10 else t[:3] + '…'


def _token_file():
    """与 coordinator / 插件一致：data_dir()/config/user_token.json"""
    return CO.user_token_path()


def _read_token():
    return CO.load_saved_user_token() or ''


def _profile(token):
    """models + 余额（USD 与 CNY 两个都给）。"""
    base = _gw_base()
    out = {'models': [], 'balance_usd': None, 'balance_cny': None}
    code, data = _http_json(base + '/models', token, timeout=8)
    if code == 200 and isinstance(data, dict):
        out['models'] = [m.get('id') for m in (data.get('data') or []) if m.get('id')]
    code, data = _http_json(base + '/dashboard/billing/subscription', token, timeout=8)
    if code == 200 and isinstance(data, dict):
        usd = data.get('hard_limit_usd')
        if isinstance(usd, (int, float)):
            out['balance_usd'] = round(float(usd), 4)
            out['balance_cny'] = round(float(usd) * 7.3, 2)
    return out


def _probe(token):
    base = _gw_base()
    code, data = _http_json(base + '/chat/completions', token,
                            {'model': 'deepseek-flash', 'max_tokens': 1,
                             'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=20)
    if code == 200:
        return {'ok': True}
    msg = ((data or {}).get('error') or {}).get('message') or str(data)[:120]
    if code == 401 or 'invalid token' in msg.lower() or '令牌无效' in msg or 'Unauthorized' in msg:
        return {'ok': False, 'code': 401, 'error': '令牌无效：网关拒绝了这个 key'}
    if code == 403 or 'quota' in msg.lower() or '余额' in msg:
        return {'ok': False, 'code': 403, 'error': '余额不足：' + str(msg)[:80]}
    if code == 0:
        return {'ok': False, 'code': 502, 'error': '连不上网关（%s）：%s' % (base, msg)}
    return {'ok': False, 'code': 502, 'error': '网关返回 %s：%s' % (code, str(msg)[:80])}


def cny_per_1k_for(model, g=None, pricing=None):
    """用 compute_billing 算「1000 字输入 + 1000 字输出」的成本，当千字参考价。

    与真实扣费同源（同一个 gateway_pricing 价表 + 同一套 quota 公式），
    所以网关调价会自动跟上；拿不到价表时返回 None，由调用方回退。
    """
    try:
        g = g or CO.gateway_cfg()
        gw = CO.map_model(g, model)
        b = CO.compute_billing(gw, {'prompt_tokens': 1000, 'completion_tokens': 1000}, g,
                               pricing=pricing)
        v = round(float(b.get('total_cny') or 0), 4)
        return v if v > 0 else None
    except Exception:
        return None


POLISH_MODELS = [
    # cny_per_1k / speed 都是「58 字润色」实测折算（元/千字、秒/百字），长文单字更便宜
    {'id': 'deepseek-flash', 'vendor': 'deepseek', 'thinking': 'disabled',
     'temperature': 0.4, 'label': '快速润色', 'hint': '快，便宜；适合日常改稿',
     'cny_per_1k': 0.009, 'speed': '约 1.5 秒/100 字'},
    {'id': 'deepseek-v4-pro', 'vendor': 'deepseek', 'thinking': 'disabled',
     'temperature': 0.4, 'label': '精细润色', 'hint': '质量更高；适合定稿前过一遍',
     'cny_per_1k': 0.026, 'speed': '约 2.3 秒/100 字'},
    {'id': 'glm-5.3', 'vendor': 'glm', 'thinking': 'reasoning_low',
     'temperature': 0.4, 'label': '智谱旗舰', 'hint': '中文语感好，适合文学性润色',
     'cny_per_1k': 0.069, 'speed': '约 2.5 秒/100 字'},
    {'id': 'glm-5.3-flash', 'vendor': 'glm', 'thinking': 'reasoning_low',
     'temperature': 0.4, 'label': '智谱轻量', 'hint': '智谱里更便宜的一档；适合日常改稿',
     'cny_per_1k': 0.069, 'speed': '约 2.8 秒/100 字'},
    {'id': 'kimi-k3', 'vendor': 'kimi', 'thinking': 'reasoning_low',
     'temperature': 1, 'label': '月之暗面', 'hint': '长文本强；适合整章润色（思考量波动，费用浮动）',
     'cny_per_1k': 0.098, 'speed': '约 5.3 秒/100 字'},
    {'id': 'kimi-k3.1-pro', 'vendor': 'kimi', 'thinking': 'reasoning_low',
     'temperature': 1, 'label': '月之暗面 Pro', 'hint': '更强的长文本处理；适合整章润色（费用波动较大）',
     'cny_per_1k': 0.12, 'speed': '约 5 秒/100 字（3–10 秒波动）'},
]
POLISH_ALIASES = {'flash': 'deepseek-flash', 'default': 'deepseek-flash',
                  'pro': 'deepseek-v4-pro', 'long': 'deepseek-v4-pro'}


def polish_spec(model):
    """按 id 找模型规格；别名先归一。找不到返回 None。"""
    mid = POLISH_ALIASES.get(str(model or '').strip(), str(model or '').strip())
    for m in POLISH_MODELS:
        if m['id'] == mid:
            return m
    return None


def polish_cfg_for(spec, strategy):
    """按「模型 + 关思考策略」造调用参数。"""
    body = {'thinking': {'type': 'disabled'}} if strategy == 'disabled' else (
        {'reasoning_effort': 'low'} if strategy == 'reasoning_low' else None)
    cfg = {'model': spec['id'], 'temperature': spec.get('temperature', 0.4),
           'max_tokens': 1200}
    if body:
        cfg['extra_body'] = body
    return cfg


def review_options_payload():
    """审稿团选项：审稿人清单 + 每个审稿人可选模型 + 计费提示。"""
    import reviewers as RV
    cfg = RV.load_config()
    reviewers = []
    for r in RV.reviewers_of(cfg):
        reviewers.append({
            'id': r.get('id'),
            'name': r.get('name') or r.get('id'),
            'persona': r.get('persona') or '',
            'model': r.get('model'),
            'enabled': bool(r.get('enabled', True)),
            'weight': r.get('weight', 1),
            'params': r.get('params') or {},
            'models': [m['id'] for m in POLISH_MODELS],
        })
    return {'ok': True,
            'mode': (cfg.get('mode') or 'vote'),
            'modes': [
                {'id': 'vote', 'label': '过半才算（推荐）', 'hint': '三人里两人说行才算过'},
                {'id': 'merge', 'label': '都说才算', 'hint': '最严'},
                {'id': 'union', 'label': '任一说就算', 'hint': '最松'},
            ],
            'temperature': cfg.get('temperature', 0.4),
            'reviewers': reviewers,
            'cny_note': '成本估算（不是收费）：kimi 系单价较高（约 0.05 元/千字），deepseek-flash 最便宜；开源版不向用户收任何费用'}


def polish_models_payload():
    """润色可选模型清单（前端渲染下拉；加模型只改 POLISH_MODELS）。

    价格按「1000 字输入 + 1000 字输出」用 compute_billing 实时折算（= 官方价 × (1+fee_rate)，当前 fee_rate=0）；
    真实计费走流末 usage（compute_billing，按实际模型）。
    实测：deepseek 系认 thinking:disabled；glm/kimi 系只有 reasoning_effort:low 能出正文。
    """
    try:
        g = CO.gateway_cfg()
        pricing = CO.gateway_pricing()          # 只拉一次，6 个模型复用
    except Exception:
        g, pricing = None, None
    out = []
    for m in POLISH_MODELS:
        live = cny_per_1k_for(m['id'], g, pricing)
        item = {k: m[k] for k in ('id', 'label', 'hint', 'speed', 'thinking', 'vendor')}
        item['cny_per_1k'] = live if live else m['cny_per_1k']
        item['cny_fallback'] = m['cny_per_1k']
        item['cny_source'] = 'live' if live else 'fallback'
        out.append(item)
    return {'ok': True, 'default': 'deepseek-flash',
            'cny_basis': '按 1000 字输入 + 1000 字输出计费折算（与实扣同源，当前按官方价）；'
                         '实际会因文本长度与模型思考量浮动',
            'models': out}


def polish_presets_payload():
    """润色预设指令（前端点一下就把 instruction 塞进 /api/polish）。"""
    return {
        'ok': True,
        'presets': [
            {'id': 'tight', 'label': '更紧凑', 'hint': '去掉冗余，句子缩短',
             'instruction': '让句子更紧凑，去掉重复和冗余表达，其余不动'},
            {'id': 'spoken', 'label': '口语化', 'hint': '书面语换白话',
             'instruction': '把书面语换成口语，允许破句和方言味，保持原意'},
            {'id': 'noadj', 'label': '去形容词', 'hint': '删堆砌的修饰',
             'instruction': '删掉堆砌的形容词和副词，留动词和名词，不要抒情'},
            {'id': 'vivid', 'label': '加强画面感', 'hint': '加动作和感官细节',
             'instruction': '加具体的动作和感官细节，不加抽象抒情，不加形容词堆砌；字数最多增加五成'},
            {'id': 'custom', 'label': '自定义', 'hint': '自己写要求',
             'instruction': ''},
        ],
    }


def polish_options_payload():
    """一次拿全：模型 + 预设（少一次往返）。"""
    models = polish_models_payload()
    presets = polish_presets_payload()
    return {'ok': True, 'default_model': models.get('default'),
            'models': models.get('models') or [],
            'presets': presets.get('presets') or []}


def next_options(pre=None, commit_info=None):
    """写完之后的「下一步选项」：前端据此渲染决策按钮（YG：审稿团是写完后的用户决策点）。"""
    passed = bool((pre or {}).get('passed', True))
    committed = bool((commit_info or {}).get('ok'))
    if passed and committed:
        return {'stage': 'awaiting', 'options': [
            {'id': 'review', 'label': '用审稿团看一下', 'enabled': True},
            {'id': 'accept', 'label': '直接定稿', 'enabled': True},
            {'id': 'retry', 'label': '重写这一章', 'enabled': True},
        ]}
    if not passed:
        return {'stage': 'blocked', 'options': [
            {'id': 'review', 'label': '用审稿团看一下', 'enabled': True},
            {'id': 'retry', 'label': '重写这一章', 'enabled': True},
        ]}
    return {'stage': 'awaiting', 'options': [
        {'id': 'review', 'label': '用审稿团看一下', 'enabled': True},
        {'id': 'retry', 'label': '重写这一章', 'enabled': True},
        {'id': 'accept', 'label': '直接定稿', 'enabled': False,
         'why': '事实入账未成功（%s）' % ((commit_info or {}).get('error') or '未知')},
    ]}


def resolve_chapter_file(book, ch):
    """按编号找已有章节文件；找不到才用默认命名。"""
    ch = str(ch).zfill(3)
    d = os.path.join(PROJECTS, book, '章节')
    prefix = ch + '-'
    try:
        for f in sorted(os.listdir(d)):
            if f.startswith(prefix) and f.endswith('.md') and '.bak' not in f:
                return f
    except OSError:
        pass
    return '%s-第%s章.md' % (ch, ch.lstrip('0') or ch)


def _stage_target(data, user_input):
    """从请求体（book/chapter）或正文里的「第N章」推出章节状态目标。"""
    if not isinstance(data, dict):
        return None
    book = str(data.get('book') or '').strip()
    chapter = str(data.get('chapter') or '').strip()
    if not chapter:
        m = re.search(r'第\s*(\d{1,4})\s*章|(\d{1,4})\s*章', user_input or '')
        if m:
            chapter = m.group(1) or m.group(2)
    if not book:
        proj = PROJECTS
        books = [d for d in (os.listdir(proj) if os.path.isdir(proj) else [])
                 if os.path.isdir(os.path.join(proj, d))]
        if len(books) == 1:
            book = books[0]
    if not book or not chapter:
        return None
    return {'book': book, 'chapter': ST.chapter_no(chapter)}


def _set_stage(target, stage, reason=None, source=None, action=None, force=False):
    if not target:
        return None
    try:
        r = ST.set_stage(target['book'], target['chapter'], stage,
                         reason=reason, source=source, action=action, force=force)
        return r.get('stage')
    except Exception:
        return None


def _stage_event(target, stage, **extra):
    if not target:
        return None
    ev = {'type': 'stage', 'stage': stage, 'chapter': target['chapter'], 'book': target['book']}
    ev.update(extra)
    return ev


# ---------------- 写作助手「附带文件」 ----------------
# 客户在助手输入框里粘一个文本文件的绝对路径，服务端读前 N 字拼到 user 消息前面。
# 与 tool_read_file 的区别：那个工具只认 ROOT 下的相对路径（模型自己翻项目）；
# 这里是客户主动递进来的、项目目录之外的文件（桌面资料、导出的 txt 等），
# 所以放行任意绝对路径 —— 权限边界仍是「跑这个进程的本机账号」，不做目录白名单；
# 只挡 `..` 这种把路径拼出花样的写法（abspath 之后再判断一次）。
# 2026-11-10：附件口径对齐 DSH（它收任意文件；图片单独有额度）
#   ASST_TEXT_EXTS   这些按正文读给模型；其余只给元信息（免得二进制糊进上下文）
#   ASST_IMAGE_EXTS  DSH 的四种图片；我们跑的是文本模型，只能给元信息，不能看图
#   ASST_FILE_BYTES  单文件 20MB（= DSH maxImageBytes 20971520）
#   ASST_FILE_MAX    单次 20 个（= DSH maxImagesPerMessage 20）
#   ASST_FILE_LIMIT  每个文本文件最多塞 50000 字（DSH 用工具按需读，我们内联，得有个帽子）
ASST_TEXT_EXTS = ('.txt', '.md', '.markdown', '.json', '.csv', '.log', '.yaml', '.yml', '.ini',
                  '.py', '.js', '.ts', '.tsx', '.jsx', '.html', '.htm', '.css', '.xml', '.srt',
                  '.toml', '.bat', '.ps1', '.sh', '.sql', '.tex', '.rtf')
ASST_IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
ASST_FILE_EXTS = ASST_TEXT_EXTS + ASST_IMAGE_EXTS
ASST_FILE_LIMIT = 50000
ASST_FILE_MAX = 20
ASST_FILE_BYTES = 20 * 1024 * 1024


def _asst_clean_path(path):
    """去掉首尾空白，以及从资源管理器复制路径时带上的引号。"""
    return str(path or '').strip().strip('"').strip("'")


def _asst_check_path(path):
    """校验客户给的文件路径，返回 (abspath, error)。"""
    p = _asst_clean_path(path)
    if not p:
        return None, '路径是空的'
    if '\x00' in p:
        return None, '路径里有非法字符'
    if any(seg == '..' for seg in re.split(r'[\\/]+', p)):
        return None, '路径里不允许 ..：%s' % p
    if not os.path.isabs(p):
        return None, '只接受绝对路径（从资源管理器地址栏复制）：%s' % p
    return os.path.abspath(p), None


def _asst_read_text(full):
    """按 utf-8 → gbk → gb18030 → errors=replace 的顺序把文件读成文本。

    返回 (text, clipped)：clipped=True 表示文件超过 ASST_FILE_BYTES，只读了开头，
    text 的长度只是「至少这么多字」，不是全文精确字数。
    """
    with open(full, 'rb') as f:
        raw = f.read(ASST_FILE_BYTES + 1)
    clipped = len(raw) > ASST_FILE_BYTES
    if clipped:
        raw = raw[:ASST_FILE_BYTES]
    for enc in ('utf-8', 'gbk', 'gb18030'):
        try:
            return raw.decode(enc), clipped
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace'), clipped


def _describe_image(full, max_bytes=12 * 1024 * 1024):
    """用网关里能吃图的模型（deepseek-flash = DeepSeek-V4.1-Flash）把图片读成一段中文描述。

    为什么单独走一次：主 agent 循环是纯文本工具调用，塞 image_url 会打断它；
    先描述成文字再拼进上下文，主链路一行不用改。
    失败一律返回 (None, 原因)，调用方退回"只给元信息"，绝不让附件把整条消息搞挂。
    """
    try:
        import base64
        size = os.path.getsize(full)
        if size > max_bytes:
            return None, '图片 %.1f MB，超过视觉描述上限 %d MB' % (size / 1024.0 / 1024.0, max_bytes // (1024 * 1024))
        with open(full, 'rb') as f:
            raw = f.read()
        ext = os.path.splitext(full)[1].lower()
        mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.webp': 'image/webp', '.gif': 'image/gif'}.get(ext, 'image/png')
        b64 = base64.b64encode(raw).decode()
        g = CO.gateway_cfg(CFG)
        body = {
            'model': 'deepseek-flash',
            'max_tokens': 1200,
            'messages': [{'role': 'user', 'content': [
                {'type': 'text', 'text': '把这张图讲清楚：画面内容、版式、以及图中出现的所有文字（逐字抄下来）。'
                                         '用中文，不要客套，直接给描述。'},
                {'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (mime, b64)}}]}],
        }
        req = request.Request(
            (g.get('base') or 'http://127.0.0.1:3000/v1').rstrip('/') + '/chat/completions',
            data=json.dumps(body).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + _user_key(),
                     'Content-Type': 'application/json'})
        with request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode('utf-8', 'replace'))
        msg = ((resp.get('choices') or [{}])[0].get('message') or {})
        text = (msg.get('content') or '').strip()
        if not text:
            return None, '视觉模型返回空（可能被思考占满 max_tokens）'
        return text, None
    except Exception as ex:
        return None, report(ex, where='run_script')


def _user_key():
    """网关 key：和插件用同一份 user_token.json（NOVELAPP_DATA/config 优先）。"""
    cands = []
    nd = os.environ.get('NOVELAPP_DATA')
    if nd:
        cands.append(os.path.join(nd, 'config', 'user_token.json'))
    ap = os.environ.get('APPDATA')
    if ap:
        cands.append(os.path.join(ap, 'novelapp-desktop', 'data', 'config', 'user_token.json'))
    for c in cands:
        try:
            with open(c, encoding='utf-8') as f:
                d = json.load(f)
            k = str((d or {}).get('key') or (d or {}).get('token') or '')
            if k:
                return k
        except Exception:
            continue
    return ''


def _asst_files_preamble(files):
    """把 files 读成一段拼在 user 消息前的上下文。

    返回 (preamble, error, meta)；error 非空时调用方必须把它当第一条 SSE 事件发回去。
    """
    if files is None or files == '' or files == []:
        return '', None, []
    if isinstance(files, str):
        files = [files]
    if not isinstance(files, (list, tuple)):
        return '', '[附带文件读不了] files 必须是路径数组', []
    paths = [_asst_clean_path(x) for x in files]
    paths = [p for p in paths if p]
    if len(paths) > ASST_FILE_MAX:
        return '', '[附带文件读不了] 一次最多带 %d 个文件，这次给了 %d 个' % (
            ASST_FILE_MAX, len(paths)), []
    blocks, meta = [], []
    for raw in paths:
        full, err = _asst_check_path(raw)
        if err:
            return '', '[附带文件读不了] ' + err, []
        ext = os.path.splitext(full)[1].lower()
        if not os.path.isfile(full):
            return '', '[附带文件读不了] 文件不存在：%s' % full, []
        try:
            size = os.path.getsize(full)
        except OSError as e:
            return '', '[附带文件读不了] %s（%s）' % (full, report(e)), []
        if size > ASST_FILE_BYTES:
            return '', '[附带文件读不了] 单个附件最多 %d MB，%s 是 %.1f MB' % (
                ASST_FILE_BYTES // (1024 * 1024), os.path.basename(full), size / 1024.0 / 1024.0), []
        if ext not in ASST_TEXT_EXTS:
            if ext in ASST_IMAGE_EXTS:
                # 图片走视觉模型（deepseek-flash）读成文字再进上下文；失败就退回元信息
                desc, why = _describe_image(full)
                if desc:
                    blocks.append('【附带的图片：%s · %.1f MB · 已由视觉模型读图】\n%s\n【图片结束】' % (
                        full, size / 1024.0 / 1024.0, desc))
                    meta.append({'path': full, 'name': os.path.basename(full),
                                 'bytes': size, 'kind': 'image', 'sent': len(desc)})
                else:
                    blocks.append('【附带的图片：%s · %.1f MB · %s】\n（没读到画面，只能按文件名判断）\n【图片结束】' % (
                        full, size / 1024.0 / 1024.0, why or '视觉描述失败'))
                    meta.append({'path': full, 'name': os.path.basename(full),
                                 'bytes': size, 'kind': 'image', 'sent': 0, 'error': why})
                continue
            blocks.append('【附带的文件：%s · %.1f MB · %s】\n（二进制，没转文字；需要内容就让我读或抽）\n【文件结束】' % (
                full, size / 1024.0 / 1024.0, ext or '无后缀'))
            meta.append({'path': full, 'name': os.path.basename(full),
                         'bytes': size, 'kind': 'binary', 'sent': 0})
            continue
        try:
            text, clipped = _asst_read_text(full)
        except Exception as e:
            return '', '[附带文件读不了] %s（%s）' % (full, report(e)), []
        total = len(text)
        piece = text[:ASST_FILE_LIMIT]
        if clipped or total > ASST_FILE_LIMIT:
            head = '【附带的文件：%s，共 %d 字%s，这里只给前 %d 字】' % (
                full, total, '以上' if clipped else '', ASST_FILE_LIMIT)
        else:
            head = '【附带的文件：%s，共 %d 字】' % (full, total)
        blocks.append('%s\n%s\n【文件结束】' % (head, piece))
        meta.append({'path': full, 'name': os.path.basename(full),
                     'bytes': size, 'kind': 'text', 'chars': total, 'sent': len(piece)})
    return '\n\n'.join(blocks), None, meta


# ---------------- 层产出落盘 + from_layer（从第 N 层起跑） ----------------
# 目录：projects/<书>/章节/.layers/<章号>/<layer>.md
#       projects/<书>/章节/.layers/<章号>/_meta.json  ->  {layer: {model, ms, tokens, cny, ts}}
# .layers 以点开头：tree() 直接跳过，章节列表 / 项目树都看不到它。
LAYER_CACHE_DIR = '.layers'


class LayerCacheMissing(Exception):
    """前面的层没有缓存：不假装成功，直接报「得从头跑」。"""

    def __init__(self, start_key, missing, idx):
        self.start_key = start_key
        self.missing = list(missing)
        self.idx = idx
        Exception.__init__(self, '没有第 %d 层之前的缓存，得从头跑' % (idx + 1))


def layer_dir(book, ch):
    return os.path.join(PROJECTS, book, '章节', LAYER_CACHE_DIR, str(ch))


def layer_path(book, ch, layer):
    return os.path.join(layer_dir(book, ch), str(layer) + '.md')


def layer_cache_load(book, ch, layer):
    """读某一层的缓存产出；文件不存在 / 内容为空都算没有缓存。"""
    try:
        with open(layer_path(book, ch, layer), encoding='utf-8') as f:
            t = f.read()
    except OSError:
        return None
    return t if t.strip() else None


def layer_meta_load(book, ch):
    try:
        with open(os.path.join(layer_dir(book, ch), '_meta.json'), encoding='utf-8') as f:
            d = json.load(f)
    except Exception:
        d = {}
    return d if isinstance(d, dict) else {}


def layer_rec(layer, model, ms, tokens, cny, chars, extra=None):
    rec = {'model': model or '', 'ms': int(ms or 0), 'tokens': int(tokens or 0),
           'cny': round(float(cny or 0), 6), 'chars': int(chars or 0),
           'layer': layer, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}
    if extra:
        rec.update(extra)
    return rec


def layer_cache_save(book, ch, layer, text, rec):
    """写 <layer>.md + 合并 _meta.json（先写临时文件再 replace，不留半截）。"""
    d = layer_dir(book, ch)
    os.makedirs(d, exist_ok=True)
    p = layer_path(book, ch, layer)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text if text.endswith('\n') else text + '\n')
    os.replace(tmp, p)
    meta = layer_meta_load(book, ch)
    meta[str(layer)] = rec
    mp = os.path.join(d, '_meta.json')
    mt = mp + '.tmp'
    with open(mt, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    os.replace(mt, mp)
    return p


def _layer_meta_write(book, ch, meta):
    """原子写 _meta.json（同 layer_cache_save：先写临时文件再 replace）。"""
    d = layer_dir(book, ch)
    os.makedirs(d, exist_ok=True)
    mp = os.path.join(d, '_meta.json')
    mt = mp + '.tmp'
    with open(mt, 'w', encoding='utf-8') as f:
        json.dump(meta or {}, f, ensure_ascii=False, indent=1)
    os.replace(mt, mp)
    return mp


def layer_finalize_refresh(book, ch):
    """定稿（章节状态进入 done）时，把层缓存对齐到盘上正文。

    做三件事：
      1. .layers/<章号>/writing.md 换成盘上当前正文
      2. .layers/<章号>/quality.md 删掉（质检的是旧稿，留着会骗人）
      3. _meta.json 里给 writing 打 refreshed_at + source='finalize'

    刷新失败绝不影响定稿：异常全部吞掉，只写一行日志，返回 ok=False 的结果。
    """
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    try:
        code = ST.chapter_no(ch) or str(ch)
    except Exception:
        code = str(ch)
    try:
        d = layer_dir(book, code)
        if not os.path.isdir(d):
            return {'ok': True, 'refreshed': False, 'reason': 'no-cache'}
        fname = resolve_chapter_file(book, code)
        src = os.path.join(PROJECTS, book, '章节', fname)
        if not os.path.isfile(src):
            _log('层缓存刷新跳过（%s/%s）：盘上没有正文 %s' % (book, code, fname))
            return {'ok': True, 'refreshed': False, 'reason': 'no-chapter'}
        with open(src, encoding='utf-8') as f:
            raw = f.read()
        # 去掉「# 第 N 章」标题行：与 run_layer_chain 比对正文用的清洗保持一致，
        # 否则定稿后第一次「从质检层重跑」会立刻报 layer_cache_stale。
        try:
            body = CO.strip_leading_heading(raw, code)[0]
        except Exception:
            body = raw
        if not body.strip():
            _log('层缓存刷新跳过（%s/%s）：盘上正文是空的' % (book, code))
            return {'ok': True, 'refreshed': False, 'reason': 'empty-chapter'}
        p = layer_path(book, code, 'writing')
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(body if body.endswith('\n') else body + '\n')
        os.replace(tmp, p)
        q = layer_path(book, code, 'quality')
        quality_removed = False
        if os.path.isfile(q):
            os.remove(q)
            quality_removed = True
        meta = layer_meta_load(book, code)
        old = meta.get('writing') if isinstance(meta.get('writing'), dict) else {}
        rec = dict(old)
        rec['layer'] = 'writing'
        rec['chars'] = len(body)
        rec['refreshed_at'] = ts
        rec['source'] = 'finalize'
        meta['writing'] = rec
        meta.pop('quality', None)      # 质检结果已过期：文件删了，账也别留着
        _layer_meta_write(book, code, meta)
        _log('层缓存已按定稿刷新：%s/%s（writing %d 字%s）'
             % (book, code, len(body), '，quality 已删' if quality_removed else ''))
        return {'ok': True, 'refreshed': True, 'chars': len(body),
                'quality_removed': quality_removed, 'refreshed_at': ts}
    except Exception as e:
        # 失败别在缓存目录里留半截临时文件
        for _t in (layer_path(book, code, 'writing') + '.tmp',
                   os.path.join(layer_dir(book, code), '_meta.json.tmp')):
            try:
                if os.path.isfile(_t):
                    os.remove(_t)
            except Exception:
                pass
        _log('层缓存刷新失败（%s/%s）：%s: %s' % (book, code, type(e).__name__, e))
        return {'ok': False, 'refreshed': False, 'error': report(e)}


def layer_clear(book, ch):
    """删掉一章的 .layers 目录，返回被删掉的文件名（排序）。没目录返回 []。"""
    d = layer_dir(book, ch)
    if not os.path.isdir(d):
        return []
    removed = sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))
    shutil.rmtree(d)
    return removed


def _layer_norm(text):
    """比对缓存与正文用：去掉所有空白，避免换行差异误报。"""
    return ''.join(str(text or '').split())


def layer_label(key):
    try:
        return CO.resolve_layer(key).get('label') or key
    except Exception:
        return key


def layer_prompt(key, ch, user_prompt, ctx, body, book):
    """拼每层的 user prompt。四层的 system 提示词仍在 coordinator.WORKER_SYSTEM，这里不动它。"""
    num = str(ch).lstrip('0') or '0'
    head = ('【前几层产出】\n' + ctx.strip() + '\n\n') if (ctx or '').strip() else ''
    if key == 'research':
        return ('《%s》第 %s 章。客户要求：%s\n\n'
                '请给这一章需要的可核查事实、设定依据与参考结构，不写正文。'
                % (book, num, user_prompt))
    if key == 'thinking':
        return (head + '《%s》第 %s 章。客户要求：%s\n\n'
                '请给结构化判断：结论 / 依据 / 风险 / 可选分支。' % (book, num, user_prompt))
    if key == 'writing':
        # 修复：分层链的写作层原来只给「前几层产出 + 客户要求」，没有角色卡/设定库/章纲，
        # 写出来比默认路径薄一截。这里把 write_context 的装配结果并进来（同一份数据，
        # 只是放在 user 里并声明「冲突时以设定为准」，因为 chat_worker 的 system 是固定的）。
        extra = ''
        try:
            import write_context as WC
            _c = WC.build_context(book, ch, extra_hint=user_prompt) or {}
            _s = (_c.get('system') or '').strip()
            if _s:
                extra = ('【这本书的设定与硬要求（写的时候必须遵守；与下面客户要求冲突时以设定为准）】\n'
                         + _s + '\n\n')
        except Exception:
            extra = ''
        return extra + head + (user_prompt or ('写第 %s 章正文。' % num))
    return (head + '《%s》第 %s 章正文（%d 字）如下：\n\n%s\n\n'
            '请按行号列问题：行号 / 问题类型 / 原文片段 / 改法。'
            % (book, num, len(body or ''), body or ''))


def run_layer_chain(book, ch, start_key, cfg, prompt, send, existing=''):
    """从 start_key 起跑：它前面的层读 .layers 缓存，start_key 及其后逐层调用并落盘。

    返回 (正文, usage 汇总)。前面的层缺缓存时抛 LayerCacheMissing，
    调用方负责回 SSE error 并且不写任何章节文件。
    """
    order = list(CO.LAYER_ORDER)
    idx = order.index(start_key)
    before, after = order[:idx], order[idx:]

    def must_send(ev):
        if not send(ev):
            raise ClientGone()

    cached, missing = {}, []
    for L in before:
        t = layer_cache_load(book, ch, L)
        if t is None:
            missing.append(L)
        else:
            cached[L] = t
    if missing:
        raise LayerCacheMissing(start_key, missing, idx)
    for L in before:
        must_send({'type': 'layer', 'id': L, 'label': layer_label(L),
                   'cached': True, 'chars': len(cached[L])})

    agg = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'total_cny': 0.0}
    parts = ['【%s】\n%s' % (layer_label(L), cached[L][:4000]) for L in before]
    body = cached.get('writing') or existing or ''
    # 缓存与正文不一致的发现手段：写作层缓存 ≠ 盘上正文 → 明说，别让人以为质检的是手改后的那版
    if cached.get('writing') and existing.strip():
        try:
            cur, _hw = CO.strip_leading_heading(existing, ch)
        except Exception:
            cur = existing
        if _layer_norm(cur) != _layer_norm(cached['writing']):
            agg['stale'] = True
            must_send({'type': 'warning', 'code': 'layer_cache_stale',
                       'text': ('这一章的正文和 .layers 里的写作层缓存不一致（可能手改过）。'
                                '本次质检的是缓存那份，落盘会把正文写回缓存内容'
                                '（覆盖前会自动留 .bak 备份）。要保住手改稿，先别落盘、'
                                '或者从头跑一次四层。')})
    for L in after:
        p = layer_prompt(L, ch, prompt, '\n\n'.join(parts), body, book)
        must_send({'type': 'layer', 'id': L, 'label': layer_label(L), 'cached': False,
                   'model': (CO.resolve_layer(L) or {}).get('model') or ''})
        t0 = time.time()
        out, meta = CO.chat_worker(L, p, cfg)
        ms = int((time.time() - t0) * 1000)
        rec = layer_rec(L, meta.get('model'), ms, meta.get('total_tokens'),
                        meta.get('total_cny'), len(out),
                        {'prompt_tokens': int(meta.get('prompt_tokens') or 0),
                         'completion_tokens': int(meta.get('completion_tokens') or 0),
                         'source': 'api/write:from_layer'})
        layer_cache_save(book, ch, L, out, rec)
        agg['prompt_tokens'] += int(meta.get('prompt_tokens') or 0)
        agg['completion_tokens'] += int(meta.get('completion_tokens') or 0)
        agg['total_tokens'] += int(meta.get('total_tokens') or 0)
        agg['total_cny'] += float(meta.get('total_cny') or 0)
        must_send({'type': 'layer_done', 'id': L, 'label': layer_label(L), 'model': rec['model'],
                   'ms': ms, 'tokens': rec['tokens'], 'cny': rec['cny'], 'chars': len(out)})
        parts.append('【%s】\n%s' % (layer_label(L), out[:4000]))
        if L == 'writing':
            body = out                     # 写作层的产出才是落盘正文
            must_send({'type': 'delta', 'kind': 'content', 'text': out})
        elif L == 'quality':
            must_send({'type': 'quality', 'issues_text': out, 'chars': len(out)})
    return body, agg


def run_agent(user_input, data=None, system_prefix=None):
    """总指挥循环，逐事件 yield 给前端（带章节状态流转）。

    system_prefix：给挂件用的额外人设（私人助理），拼在 CO.SYSTEM 前面；
    不传就是原来的总指挥。
    """
    # _stage_text：附带文件被拼进了 user_input，但「要写第几章」只能看客户自己打的那句话，
    # 否则附件里出现「第 3 章」就会把这本书误推进到 working。
    seed_text = ''
    if isinstance(data, dict):
        seed_text = str(data.get('_stage_text') or '')
    target = _stage_target(data, seed_text or user_input)
    if target:
        _set_stage(target, 'working', reason='四层流水线运行中', source='writing', action='review')
        ev = _stage_event(target, 'working', reason='四层流水线运行中',
                          source='writing', action='review')
        if ev:
            yield ev
    try:
        for ev in _agent_loop(user_input, target, system_prefix=system_prefix):
            yield ev
    except Exception as e:
        if target:
            reason = '写章失败：' + human(e)
            _set_stage(target, 'draft', reason=reason, source='writing', action='retry')
            bad = _stage_event(target, 'draft', reason=reason, source='writing',
                               action='retry', error=report(e))
            if bad:
                yield bad
        yield {'type': 'error', 'text': report(e)}


def _agent_loop(user_input, stage_target=None, system_prefix=None):
    co = CFG.get('coordinator', CFG)
    usage_acc = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0,
                 'quota': 0.0, 'official_cny': 0.0, 'fee_cny': 0.0, 'total_cny': 0.0,
                 'steps': 0, 'models': set(), 'fee_rate': 0.0, 'request_id': None,
                 'layers': []}
    try:
        CO.reset_worker_calls()
    except Exception as e:
        try:
            _lg = os.path.join(os.environ.get('NOVELAPP_DATA') or '', 'logs')
            os.makedirs(_lg, exist_ok=True)
            with open(os.path.join(_lg, 'prompt-log-error.log'), 'a', encoding='utf-8') as _f:
                _f.write('%s %s\n' % (type(e).__name__, e))
        except Exception:
            pass
    # 技能清单拼进 system：只给名字 + 一句描述，正文让模型按需调 skill 工具取。
    # 全塞进去会把 system 顶到几万字，每次调用都付一遍钱。
    _sys = ((system_prefix + '\n\n') if system_prefix else '') + CO.SYSTEM
    try:
        _cat = CO.skill_catalog()
        if _cat:
            _sys = _sys + '\n\n' + _cat
    except Exception:
        pass
    # 联网搜索默认关闭：开着才把那一条提示拼进 system（关着不提，模型就不会白调一次）。
    # 工具本身始终留在 CO.TOOLS 里，客户在设置里一开立刻可用。
    try:
        if CO.search_enabled(CFG):
            _sys = _sys + '\n' + CO.SYSTEM_SEARCH_RULE
    except Exception:
        pass
    messages = [{'role': 'system', 'content': _sys},
                {'role': 'user', 'content': user_input}]
    max_steps = co.get('max_steps', 20)

    for step in range(1, max_steps + 1):
        try:
            resp = CO.chat(co, messages, CO.TOOLS)
        except CO.GatewayAuthError as e:
            if stage_target:
                reason = '写章失败：' + human(e)
                _set_stage(stage_target, 'draft', reason=reason, source='writing', action='retry')
                ev = _stage_event(stage_target, 'draft', reason=reason, source='writing',
                                  action='retry', error=str(e))
                if ev:
                    yield ev
            yield {'type': 'error', 'text': str(e), 'need_login': True}
            return
        _usage_add(usage_acc, resp.get('_billing'))
        msg = resp['choices'][0]['message']
        messages.append(msg)

        calls = msg.get('tool_calls') or []
        if not calls:
            text = CO.sanitize_worker_text(msg.get('content') or '')
            ev = {'type': 'final', 'text': text, 'usage': _usage_out(usage_acc)}
            if stage_target:
                auto = getattr(CO, 'LAST_COMMIT_AUTO', None) or {}
                if auto and auto.get('chapter') == stage_target['chapter'] and not auto.get('ok'):
                    reason = auto.get('error') or '事实入账失败'
                    stage = _set_stage(stage_target, 'blocked', reason=reason,
                                       source='writing', action='retry')
                    ev['stage'] = stage or 'blocked'
                    ev['chapter'] = stage_target['chapter']
                    ev['reason'] = reason
                    ev['source'] = 'writing'
                    ev['action'] = 'retry'
                    yield ev
                    return
                if auto and auto.get('chapter') == stage_target['chapter'] and auto.get('ok'):
                    reason = '已写完 %d 字，已入账 %d 条事件，等你确认' % (
                        len(text), auto.get('events') or 0)
                    stage = _set_stage(stage_target, 'awaiting', reason=reason,
                                       source='writing', action='confirm')
                    ev['stage'] = stage or 'awaiting'
                    ev['chapter'] = stage_target['chapter']
                    ev['reason'] = reason
                    ev['source'] = 'writing'
                    ev['action'] = 'confirm'
                    yield ev
                    return
                # 没有自动入账记录：仍是「写完等审」
                reason = '已写完 %d 字，还没审稿' % len(text)
                stage = _set_stage(stage_target, 'awaiting', reason=reason,
                                   source='writing', action='review')
                ev['stage'] = stage or 'awaiting'
                ev['chapter'] = stage_target['chapter']
                ev['reason'] = reason
                ev['source'] = 'writing'
                ev['action'] = 'review'
            yield ev
            return

        for tc in calls:
            name = tc['function']['name']
            try:
                args = json.loads(tc['function']['arguments'] or '{}')
            except Exception:
                args = {}
            yield {'type': 'tool', 'step': step, 'name': name,
                   'args': {k: (str(v)[:60] + '…' if len(str(v)) > 60 else v) for k, v in args.items()}}

            try:
                out = CO.dispatch_tool(name, args, CFG)
            except Exception as e:
                out = '[工具异常] %s：%s' % (name, report(e))

            clean = CO.sanitize_worker_text(str(out))
            # 回灌给模型的工具输出上限 12000 字：不设的话 20 步能把上下文顶到十几万 token
            if len(clean) > 12000:
                clean = clean[:12000] + '\n…[工具输出截断：共 %d 字]' % len(clean)
            layer_calls = []
            try:
                layer_calls = CO.take_worker_calls()
            except Exception:
                pass
            for c in layer_calls:
                usage_acc['layers'].append(c)
            ev = {'type': 'tool_result', 'name': name,
                  'text': clean[:600], 'truncated': len(clean) > 600}
            if layer_calls:
                last = layer_calls[-1]
                ev['layer'] = {'id': last.get('role'), 'label': last.get('layer'),
                               'model': last.get('model'), 'skipped': bool(last.get('skipped')),
                               'tokens': last.get('total_tokens')}
            yield ev
            messages.append({'role': 'tool', 'tool_call_id': tc['id'], 'content': clean})

    ev = {'type': 'final', 'text': '[达到最大步数]', 'usage': _usage_out(usage_acc)}
    if stage_target:
        reason = '跑到 %d 步没收敛，可能卡在某一层' % max_steps
        ev['stage'] = _set_stage(stage_target, 'blocked', reason=reason,
                                 source='writing', action='retry') or 'blocked'
        ev['chapter'] = stage_target['chapter']
        ev['reason'] = reason
        ev['source'] = 'writing'
        ev['action'] = 'retry'
    yield ev


def serve(port=8770, open_browser=True):
    """起服务并阻塞。桌面壳可在独立线程里调用它。"""
    srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    print(f'服务已启动: http://127.0.0.1:{port}')
    print(f'项目根目录: {ROOT}')
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f'http://127.0.0.1:{port}')).start()
    srv.serve_forever()


if __name__ == '__main__':
    if '--run-script' in sys.argv:      # frozen 下由 _run_script 调起，跑完即退
        CO.exec_script(sys.argv)
        sys.exit(0)
    _port = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
    serve(_port, '--no-browser' not in sys.argv)