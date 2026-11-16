# -*- coding: utf-8 -*-
"""总指挥（Coordinator）

一个带工具调用能力的 agent 循环：
  用户指令 -> 模型思考 -> 调工具 -> 看结果 -> 继续或结束

总指挥不读正文全文，只看状态与摘要；正文由 worker 处理。
"""
import json, os, sys, re, subprocess, time
from urllib import request
from urllib.error import HTTPError, URLError

def _resolve_root():
    """PyInstaller frozen 时根目录 = exe 所在目录（web/config/scripts 被拷到旁边）；
    源码运行时 = core/ 的上一级。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


ROOT = _resolve_root()


LOG_DIR = os.path.join(ROOT, 'logs')
QC_LOG = os.path.join(LOG_DIR, 'qc.log')
QC_LOG_MAX = 2 * 1024 * 1024      # 2MB 轮转


def log_qc_run(script, info, stderr_text):
    """把质检子进程的 stderr / 退出码追加到 ROOT/logs/qc.log。

    打包版没有控制台窗口，脚本的 [warn]、异常栈只有 stderr 有，
    不落盘用户就永远看不到（配置写坏时尤其致命）。
    """
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        if os.path.exists(QC_LOG) and os.path.getsize(QC_LOG) > QC_LOG_MAX:
            try:
                os.replace(QC_LOG, QC_LOG + '.1')
            except OSError:
                pass
        import datetime as _dt
        ts = _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        info = info or {}
        with open(QC_LOG, 'a', encoding='utf-8') as f:
            f.write('[%s] %s exit=%s ms=%s%s\n' % (
                ts, os.path.basename(script), info.get('exit', '?'), info.get('ms', '?'),
                (' error=' + str(info['error'])) if info.get('error') else ''))
            for line in (stderr_text or '').strip().splitlines():
                f.write('    ' + line + '\n')
    except OSError:
        pass


def script_cmd(script_rel, extra=()):
    """返回启动脚本的命令行。

    frozen 模式下没有独立的 python.exe，用自身 exe 的 --run-script 模式复用解释器；
    源码模式直接用当前解释器。
    """
    script = script_rel if os.path.isabs(script_rel) else os.path.join(ROOT, script_rel)
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--run-script', script] + [str(a) for a in extra]
    return [sys.executable, script] + [str(a) for a in extra]


def exec_script(argv):
    """--run-script <script> [args...]：在冻结进程内跑外部 py 脚本，退出码透传。"""
    idx = list(argv).index('--run-script')
    script = argv[idx + 1]
    sys.argv = [script] + list(argv[idx + 2:])
    import runpy
    code = 0
    try:
        runpy.run_path(script, run_name='__main__')
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 0
    except Exception as e:
        sys.stderr.write('%s: %s\n' % (type(e).__name__, e))
        code = 1
    sys.exit(code)


import yamlite

LAYERS_PATH = os.path.join(ROOT, 'config', 'layers.yaml')
REVIEWERS_PATH = os.path.join(ROOT, 'config', 'reviewers.yaml')
LAYER_ORDER = ('research', 'thinking', 'writing', 'quality')
_LAYERS_STATE = {'sig': None, 'data': None, 'error': None}


def layers_config(force=False):
    """读 config/layers.yaml；mtime 变了就重读（客户改完立即生效）。读坏保留上一次。"""
    try:
        st = os.stat(LAYERS_PATH)
        sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        sig = ('missing',)
    if not force and _LAYERS_STATE['data'] is not None and sig == _LAYERS_STATE['sig']:
        return _LAYERS_STATE['data']
    if sig[0] == 'missing':
        _LAYERS_STATE.update({'sig': sig, 'error': 'layers.yaml 不存在'})
        return _LAYERS_STATE['data'] or {'layers': {}, 'models': []}
    try:
        data = yamlite.load_file(LAYERS_PATH)
        if not isinstance(data, dict):
            raise ValueError('顶层不是映射')
    except Exception as e:
        _LAYERS_STATE.update({'sig': sig, 'error': '%s: %s' % (type(e).__name__, e)})
        return _LAYERS_STATE['data'] or {'layers': {}, 'models': []}
    _LAYERS_STATE.update({'sig': sig, 'data': data, 'error': None})
    return data


def resolve_layer(role):
    """返回某一层的配置；layers.yaml 缺失时退回 coordinator.json 的 workers 配置。"""
    key = resolve_role(role) or role
    data = layers_config() or {}
    layer = (data.get('layers') or {}).get(key)
    if isinstance(layer, dict):
        out = dict(layer)
        out['id'] = key
        return out
    cfg = load_cfg()
    w = ((cfg.get('workers') or {}).get(key) or {})
    co = cfg.get('coordinator') or {}
    return {'id': key, 'enabled': bool(w), 'model': w.get('model') or co.get('model'),
            'temperature': w.get('temperature', co.get('temperature', 0.7)),
            'max_tokens': w.get('max_tokens'), '_from': 'coordinator.json'}


def layers_public():
    """给 UI 的层清单：配置 + 实际会用的模型 + 是否可用。"""
    data = layers_config() or {}
    models = data.get('models') or []
    model_ids = {m.get('id') for m in models if isinstance(m, dict)}
    out = []
    for key in LAYER_ORDER:
        layer = resolve_layer(key)
        model = layer.get('model') or ''
        out.append({
            'id': key,
            'label': layer.get('label') or key,
            'description': layer.get('description') or '',
            'enabled': bool(layer.get('enabled', True)),
            'model': model,
            'temperature': layer.get('temperature'),
            'max_tokens': layer.get('max_tokens'),
            'model_known': (model in model_ids) if model_ids else None,
            '_from': layer.get('_from') or 'layers.yaml',
        })
    return {'layers': out, 'models': models,
            'error': _LAYERS_STATE.get('error'),
            'path': LAYERS_PATH}


SPATIAL_LAYERS = ('writing', 'research', 'thinking')
_SPATIAL = {'sig': None, 'text': '', 'path': None}
_STATE = {'sig': None, 'text': '', 'path': None}

SPATIAL_TEMPLATE = (
    '\n\n【你必须遵守的空间与行程约束】\n'
    '下面是本书的世界地图事实（相对位置 / 交通方式与速度 / 本书已记录的行程）：\n\n'
    '%s\n\n'
    '写正文时：\n'
    '1. 先确认人物此刻在哪、要去哪\n'
    '2. 确认他用什么方式赶路（空手/挑担/骑马/飞）\n'
    '3. 按速度表算出耗时，正文里的时间描写必须与之一致'
    '（表写「挑担三十里/日」，就别写挑着担半天走完三十里）\n'
    '4. 遇到速度表里没有的能力（比如突然会飞），先在正文里交代原因，不要凭空提速\n'
    '5. 表里标「待定/未明」的不要自己编具体数字；能含糊就含糊（「远着咧」），'
    '必须给数就先回去补地图\n'
)


def spatial_map_path(cfg=None):
    """世界地图路径：config.spatial.map_path > projects/*/设定库/世界地图.md（取第一本）。"""
    cfg = cfg if isinstance(cfg, dict) else load_cfg()
    sp = cfg.get('spatial') if isinstance(cfg.get('spatial'), dict) else {}
    p = sp.get('map_path')
    if p:
        if not os.path.isabs(p):
            p = os.path.join(ROOT, p)
        return p if os.path.exists(p) else None
    proj = projects_root()
    if os.path.isdir(proj):
        for name in sorted(os.listdir(proj)):
            cand = os.path.join(proj, name, '设定库', '世界地图.md')
            if os.path.exists(cand):
                return cand
    return None


STATE_TEMPLATE = (
    '\n\n【角色当前状态（写这一章之前）】\n'
    '%s\n\n'
    '写作时遵守：\n'
    '1. 不要让人物凭空出现在别处；他此刻在哪、怎么到的，以这张表为准\n'
    '2. 物品、伤势、钱要与表连续；本章如果有变化（丢了/受伤/花钱），正文里要交代\n'
    '3. 表里写「未说明」的，要么在正文里补上，要么保持含糊，不要自己编\n'
)


def state_path_for(cfg=None):
    """角色状态表：config.spatial.state_path > projects/*/设定库/角色状态.md。"""
    cfg = cfg if isinstance(cfg, dict) else load_cfg()
    sp = cfg.get('spatial') if isinstance(cfg.get('spatial'), dict) else {}
    p = sp.get('state_path')
    if p:
        if not os.path.isabs(p):
            p = os.path.join(ROOT, p)
        return p if os.path.exists(p) else None
    proj = projects_root()
    if os.path.isdir(proj):
        for name in sorted(os.listdir(proj)):
            cand = os.path.join(proj, name, '设定库', '角色状态.md')
            if os.path.exists(cand):
                return cand
    return None


LEDGER_TEMPLATE = (
    '\n\n【本章可用的账本约束（时间线 / 伏笔 / 力量体系）】\n'
    '%s\n\n'
    '写作时遵守：\n'
    '1. 本章发生在第几天，必须与时间线一致；跨天要交代怎么过的\n'
    '2. 未收的伏笔可以推进，不要凭空多出一条收线；新埋的伏笔会在本章审完后登记\n'
    '3. 主角还不能用超出「成长记录」的能力；要破格必须先在正文里给代价和铺垫\n'
)


def _settings_dir_for(cfg=None):
    p = spatial_map_path(cfg)
    if p:
        return os.path.dirname(p)
    st = state_path_for(cfg)
    if st:
        return os.path.dirname(st)
    return None


def _md_table_rows(text, header_keys, limit=None):
    rows, header = [], None
    for ln in text.split('\n'):
        s = ln.strip()
        if not s.startswith('|'):
            header = header if rows else None
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if header is None:
            if all(any(k in c for c in cells) for k in header_keys):
                header = cells
            continue
        if set(''.join(cells)) <= set('-: '):
            continue
        rows.append(' | '.join(cells))
        if limit and len(rows) >= limit:
            break
    return rows


MEMORY_HEADER = (
    '\n\n【软件记忆检索：写这一章前请先读，缺什么以这份资料为准】\n'
)


def memory_bundle(cfg=None, chapter_hint=None):
    """用 recall.recall() 一次性取回本章要用的记忆（角色/地点/事件/伏笔/规矩）。"""
    base = _settings_dir_for(cfg)
    if not base:
        return ''
    book = os.path.basename(os.path.dirname(base))
    try:
        import recall as _recall          # 延迟导入，避免 recall -> coordinator 循环
        text = _recall.recall(book, chapter_hint)
    except Exception:
        return ''
    if not text:
        return ''
    return MEMORY_HEADER + text


def ledger_digest(cfg=None):
    """给写作层的轻量账本摘要：时间线最近 3 章 + 未收伏笔 + 力量硬约束。"""
    base = _settings_dir_for(cfg)
    if not base:
        return ''
    parts = []
    tl = os.path.join(base, '时间线.md')
    if os.path.exists(tl):
        with open(tl, encoding='utf-8-sig') as f:
            rows = _md_table_rows(f.read(), ['章', '故事内时间'])
        if rows:
            parts.append('时间线（最近记录）：\n  ' + '\n  '.join(rows[-3:]))
    fs = os.path.join(base, '伏笔.md')
    if os.path.exists(fs):
        with open(fs, encoding='utf-8-sig') as f:
            txt = f.read()
        seg = txt.split('## 已埋未收', 1)
        if len(seg) == 2:
            body = seg[1].split('\n## ', 1)[0]
            rows = _md_table_rows(body, ['编号', '埋在哪章'], limit=8)
            if rows:
                parts.append('未收伏笔：\n  ' + '\n  '.join(rows))
    pw = os.path.join(base, '力量体系.md')
    if os.path.exists(pw):
        with open(pw, encoding='utf-8-sig') as f:
            txt = f.read()
        m = re.search(r'##\s*三、硬约束(.*?)(?=\n##\s)', txt, re.S)
        if m:
            hard = re.sub(chr(96) * 3, '', m.group(1)).strip()
            parts.append('力量硬约束：\n' + hard[:600])
    return '\n\n'.join(parts)


def character_state_text(cfg=None):
    """角色状态表正文（去掉尾部「更新规则」「审稿团怎么用」这类说明节），mtime 缓存。"""
    path = state_path_for(cfg)
    if not path:
        return ''
    try:
        st = os.stat(path)
        sig = (st.st_mtime_ns, st.st_size, path)
    except OSError:
        return ''
    if _STATE['sig'] == sig:
        return _STATE['text']
    try:
        with open(path, encoding='utf-8-sig') as f:
            text = f.read()
    except OSError:
        return ''
    cut = text.find('\n## 更新规则')
    if cut > 0:
        text = text[:cut]
    text = text.strip()
    _STATE.update({'sig': sig, 'text': text, 'path': path})
    return text


def spatial_constraints(cfg=None):
    """取地图的「一 相对位置表 / 二 交通方式与速度 / 三 已记录的行程」，mtime 缓存。"""
    path = spatial_map_path(cfg)
    if not path:
        return ''
    try:
        st = os.stat(path)
        sig = (st.st_mtime_ns, st.st_size, path)
    except OSError:
        return ''
    if _SPATIAL['sig'] == sig:
        return _SPATIAL['text']
    try:
        with open(path, encoding='utf-8-sig') as f:
            text = f.read()
    except OSError:
        return ''
    parts = []
    for pat in (r'##\s*一、[^\n]*\n(.*?)(?=\n##\s*二、|\Z)',
                r'##\s*二、[^\n]*\n(.*?)(?=\n##\s*三、|\Z)',
                r'##\s*三、[^\n]*\n(.*?)(?=\n##\s*四、|\Z)'):
        m = re.search(pat, text, re.S)
        if m:
            parts.append(m.group(1).strip())
    body = '\n\n'.join(parts)
    _SPATIAL.update({'sig': sig, 'text': body, 'path': path})
    return body


_WORKER_CALLS = []


def reset_worker_calls():
    _WORKER_CALLS.clear()


def take_worker_calls():
    out = list(_WORKER_CALLS)
    _WORKER_CALLS.clear()
    return out


def load_cfg(name='config/coordinator.json'):
    return json.load(open(os.path.join(ROOT, name), encoding='utf-8'))


def search_enabled(cfg=None):
    """联网搜索开关：config/coordinator.json 的 search.enabled，缺省 False（关闭）。

    默认关闭是产品决定，不是漏配：搜索源是 Bing 的 RSS，它那句版权声明只允许
    「出于个人的非商业用途在 RSS 聚合器中呈现必应结果」，这套软件是卖给客户商用的，
    默认开着等于替客户做了这个选择。要开让客户自己在「设置 → 通用 → 联网搜索」里点开。

    cfg 传进来的常常是 coordinator / worker 子配置（里面没有 search），
    这时回全局配置找，和 gateway_cfg() 的处理方式一致。
    """
    if not isinstance(cfg, dict) or 'search' not in cfg:
        try:
            cfg = load_cfg()
        except Exception:
            return False          # 配置读不了就按关闭处理，绝不放行
    s = cfg.get('search')
    if not isinstance(s, dict):
        return False
    v = s.get('enabled')
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ('1', 'true', 'yes', 'on')
    return False


# ---------------- new-api 网关（统一计费） ----------------
#
# 所有模型调用走本地 new-api（默认 127.0.0.1:3000），响应里的 usage 换成本地计费对象：
#   quota → cny = quota / quota_per_unit * price   （new-api 的 /api/status 给这两个值）
#   服务费 = cny - cny/(1+fee_rate)
# 计费口径必须和 new-api 日志一致，所以用网关模型名去 /api/pricing 取 ratio 本地核算。

try:
    import edition as ED
except Exception:
    ED = None

GATEWAY_DEFAULTS = {
    'enabled': True,
    'base': 'http://127.0.0.1:3000/v1',
    'downstream_key': '',
    'fee_rate': 0.0,          # 2026-11-10：默认按官方价收（要恢复 5% 就改 0.05）
    'pricing_ttl': 300,
    'quota_per_unit': 500000,
    'price_ratio': 7.3,
    'timeout': 300,
    'db_path': r'D:\relay\data\new-api.db',
    # 网关认原名（abilities 表里就有 deepseek-flash / glm-5.3-flash / kimi-k3 …）。
    # 不要映射到 default/long/pro：那些通道的 ratio 与真实模型不同，会按错价收费。
    # 确实需要指定通道时，才在 config/coordinator.json 里加例外。
    'model_map': {},
}

_PRICING = {'at': 0, 'models': {}, 'group_ratio': {}, 'quota_per_unit': 500000,
            'price': 7.3, 'error': None}


def _read_downstream_key_file():
    for name in ('config/downstream_key.txt', 'config/gateway_key.txt'):
        p = os.path.join(ROOT, name)
        try:
            with open(p, encoding='utf-8') as f:
                k = f.read().strip()
            if k:
                return k
        except OSError:
            continue
    return ''


class GatewayAuthError(RuntimeError):
    """没有登录令牌 —— 必须让用户先登录，绝不静默 fallback 到开发密钥。"""


def gateway_cfg(cfg=None):
    """网关配置。

    安全规则（见 docs/支付与计费安全.md）：
      1. 只认 config/user_token.json（客户登录后签发的专属令牌，有额度上限）
      2. 绝不再回退到 config/coordinator.json 的 downstream_key（开发用，出厂必须为空）
      3. 开发/联调需要时，显式设置 NOVELAPP_ALLOW_DEV_KEY=1 才允许用环境变量里的 key
    """
    if not isinstance(cfg, dict):
        cfg = load_cfg()
    g = dict(GATEWAY_DEFAULTS)
    user = cfg.get('gateway')
    if not isinstance(user, dict):
        # chat() 传进来的常是 coordinator/worker 子配置，回全局配置找 gateway
        try:
            user = load_cfg().get('gateway')
        except Exception:
            user = None
    if isinstance(user, dict):
        g.update({k: v for k, v in user.items() if v is not None})
    saved = load_saved_user_token()
    dev_allowed = os.environ.get('NOVELAPP_ALLOW_DEV_KEY') == '1'
    dev_key = ''
    if dev_allowed:
        dev_key = (os.environ.get('NOVELAPP_DOWNSTREAM_KEY', '')
                   or (g.get('downstream_key') if isinstance(cfg.get('gateway'), dict) else '')
                   or _read_downstream_key_file())

    if saved:
        g['downstream_key'] = saved
        g['key_source'] = 'user_token'
    elif dev_key:
        g['downstream_key'] = dev_key
        g['key_source'] = 'dev'
    else:
        g['downstream_key'] = ''
        g['key_source'] = 'none'
    g['need_login'] = not bool(g['downstream_key'])
    g['enabled'] = bool(g.get('enabled', True)) and bool(g['downstream_key'])
    # 计费口径：以 edition 的费率为准，放在最后覆盖，避免配置里的 0 吞掉它。
    if ED is not None:
        try:
            ed = ED.load()
            g['fee_rate'] = float(ed.get('fee_rate', g.get('fee_rate') or 0.0))
            g['edition'] = ed.get('edition')
        except Exception:
            pass
    return g


USER_TOKEN_PATH = None   # 显式覆盖（测试用）；默认走 data_dir()/config


def data_dir():
    """客户数据目录：NOVELAPP_DATA > <ROOT>/data > %APPDATA%/novelapp-desktop/data。

    安装目录（resources/）在客户机上可能只读，所以 token 不写那里。
    """
    d = os.environ.get('NOVELAPP_DATA')
    if d:
        return d
    # 打包后 main.ts 会设 NOVELAPP_DATA；开发态统一用 APPDATA，
    # 不能再优先 <ROOT>/data —— 否则仓库里残留的 data/config 会顶掉客户令牌。
    if os.environ.get('APPDATA'):
        return os.path.join(os.environ['APPDATA'], 'novelapp-desktop', 'data')
    root = os.environ.get('NOVELAPP_ROOT')
    if root:
        return os.path.join(root, 'data')
    return os.path.join(ROOT, 'data')


def user_token_path():
    return USER_TOKEN_PATH or os.path.join(data_dir(), 'config', 'user_token.json')


def projects_root():
    """客户项目目录（与插件 projectsRoot()、server.projects_root() 同一套优先级）。"""
    p = os.environ.get('NOVELAPP_PROJECTS')
    if p:
        return os.path.abspath(p)
    d = os.environ.get('NOVELAPP_DATA')
    if d:
        return os.path.join(os.path.abspath(d), 'projects')
    if os.environ.get('APPDATA'):
        return os.path.join(os.environ['APPDATA'], 'novelapp-desktop', 'data', 'projects')
    return os.path.join(ROOT, 'projects')


def legacy_token_path():
    return os.path.join(ROOT, 'config', 'user_token.json')


def migrate_legacy_token():
    """老位置（ROOT/config）有令牌、新位置没有 -> 搬过去并删老的。返回做了什么都行。"""
    new, old = user_token_path(), legacy_token_path()
    if os.path.abspath(new) == os.path.abspath(old):
        return None
    if os.path.exists(new) or not os.path.exists(old):
        return None
    try:
        os.makedirs(os.path.dirname(new), exist_ok=True)
        with open(old, encoding='utf-8') as f:
            raw = f.read()
        tmp = new + '.tmp~'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(raw)
        os.replace(tmp, new)
        os.remove(old)
        return 'migrated %s -> %s' % (old, new)
    except OSError:
        return None


def load_saved_user_token():
    migrate_legacy_token()
    """config/user_token.json 里客户登录后签发的令牌（明文只存这一处）。"""
    try:
        with open(user_token_path(), encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        return ''
    # 兼容两种写法：{"token": "..."} 和 {"key": "..."}
    if not isinstance(d, dict):
        return ''
    tok = d.get('token') or d.get('key') or ''
    return tok.strip() if isinstance(tok, str) else ''


def gateway_base(g=None):
    g = g or gateway_cfg()
    return str(g['base']).rstrip('/').removesuffix('/v1')


def map_model(g, model):
    """把界面/配置里的模型名映射成网关的映射名（default/long/pro/local…）。"""
    mm = g.get('model_map') or {}
    if not model:
        return 'default'
    return mm.get(model, model)


def gateway_pricing(force=False, ttl=None):
    """拉 /api/pricing + /api/status，缓存 ttl 秒；失败保留上次结果。"""
    g = gateway_cfg()
    ttl = ttl if ttl is not None else float(g.get('pricing_ttl') or 300)
    now = time.time()
    if not force and _PRICING['at'] and now - _PRICING['at'] < ttl:
        return _PRICING
    # 上次拉取失败：30 秒内不再尝试，否则每个模型都要等两次 5 秒超时
    if not force and _PRICING.get('failed_at') and now - _PRICING['failed_at'] < 30:
        return _PRICING
    base = gateway_base(g)
    models, group_ratio = {}, {}
    try:
        with request.urlopen(base + '/api/pricing', timeout=5) as r:
            data = json.loads(r.read().decode('utf-8', 'replace'))
        for m in data.get('data') or []:
            name = m.get('model_name')
            if not name:
                continue
            models[name] = {'ratio': float(m.get('model_ratio') or 0),
                            'completion': float(m.get('completion_ratio') or 1),
                            'price': float(m.get('model_price') or 0),
                            'quota_type': int(m.get('quota_type') or 0)}
        group_ratio = data.get('group_ratio') or {}
    except Exception as e:
        _PRICING['error'] = 'pricing: %s' % e
        _PRICING['failed_at'] = time.time()
    quota_per_unit, price = _PRICING['quota_per_unit'], _PRICING['price']
    try:
        with request.urlopen(base + '/api/status', timeout=5) as r:
            st = json.loads(r.read().decode('utf-8', 'replace'))
        d = st.get('data') or {}
        quota_per_unit = float(d.get('quota_per_unit') or quota_per_unit)
        price = float(d.get('price') or price)
    except Exception as e:
        _PRICING['error'] = 'status: %s' % e
    if models:
        _PRICING.update({'at': now, 'models': models, 'group_ratio': group_ratio,
                         'quota_per_unit': quota_per_unit, 'price': price})
    return _PRICING


def quota_to_cny(quota, pricing=None):
    p = pricing or _PRICING
    qpu = float(p.get('quota_per_unit') or 500000)
    price = float(p.get('price') or 7.3)
    return round(float(quota or 0) / qpu * price, 6)


def compute_billing(gw_model, usage, g=None, group='default', pricing=None):
    """按 new-api 的口径本地核算：quota = (prompt + completion*completion_ratio) * ratio * group_ratio。"""
    g = g or gateway_cfg()
    pricing = pricing if pricing is not None else gateway_pricing()
    prompt = int(usage.get('prompt_tokens') or 0)
    completion = int(usage.get('completion_tokens') or 0)
    total_tokens = int(usage.get('total_tokens') or (prompt + completion))
    meta = (pricing.get('models') or {}).get(gw_model) or {}
    ratio = float(meta.get('ratio') or 0)
    c_ratio = float(meta.get('completion') or 1)
    gr = float((pricing.get('group_ratio') or {}).get(group, 1) or 1)
    # new-api 用四舍五入取整（int(x+0.5)），不是 ceil：67.71→68、6.06→6、29.2→29
    quota_raw = (prompt + completion * c_ratio) * ratio * gr
    quota = float(int(quota_raw + 0.5))
    cny = quota_to_cny(quota, pricing)
    _fv = g.get('fee_rate')
    if ED is not None:
        try:
            _fv = ED.load().get('fee_rate', _fv)          # 版本分档说了算（内部 0 / 客户 0.05）
        except Exception:
            pass
    fee_rate = float(_fv) if _fv is not None else 0.0   # 0 是合法值，别用 or 0.05 把 0 吞掉
    official = round(cny / (1 + fee_rate), 6)
    fee = round(cny - official, 6)
    return {
        'model': gw_model,
        'prompt_tokens': prompt,
        'completion_tokens': completion,
        'total_tokens': total_tokens,
        'quota': quota,
        'quota_raw': round(quota_raw, 4),
        'model_ratio': ratio,
        'completion_ratio': c_ratio,
        'official_cny': official,
        'fee_cny': fee,
        'total_cny': cny,
        'fee_rate': fee_rate,
        'pricing_ok': bool(meta),
    }


def _gateway_chat(cfg, messages, tools, g):
    model = map_model(g, cfg.get('model'))
    body = {'model': model, 'messages': messages,
            'temperature': (1 if model == 'pro' else cfg.get('temperature', 0.3))}
    if cfg.get('max_tokens'):
        body['max_tokens'] = int(cfg['max_tokens'])
    extra_keys = []
    if isinstance(cfg.get('extra_body'), dict):
        extra_keys = list(cfg['extra_body'])
        body.update(cfg['extra_body'])
    if tools:
        body['tools'] = tools
        body['tool_choice'] = 'auto'

    url = str(g['base']).rstrip('/') + '/chat/completions'
    timeout = float(g.get('timeout') or 300)

    def _send(payload):
        req = request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                              headers={'Content-Type': 'application/json',
                                       'Authorization': 'Bearer ' + str(g['downstream_key'])},
                              method='POST')
        with request.urlopen(req, timeout=timeout) as r:
            return r.read(), dict(r.headers)

    try:
        raw, hdrs = _send(body)
    except HTTPError as e:
        # 有些厂商不认 thinking / reasoning 之类的扩展参数，400 时去掉重试一次
        detail = b''
        try:
            detail = e.read()[:300]
        except Exception:
            pass
        _kind = classify_gateway_error(e.code, detail)
        if _kind == 'auth':
            raise GatewayAuthError(friendly_gateway_error(e.code, detail))
        if _kind == 'db':
            raise WorkerError(DB_HINT + '（HTTP %s）' % e.code)
        if e.code in (400, 403) and extra_keys:
            for k in extra_keys:
                body.pop(k, None)
            raw, hdrs = _send(body)
        else:
            raise HTTPError(e.url, e.code, e.msg, e.hdrs,
                            __import__('io').BytesIO(detail or b''))

    resp = json.loads(raw.decode('utf-8', 'replace'))
    usage = resp.get('usage') or {}
    billing = compute_billing(model, usage, g)
    billing['request_id'] = hdrs.get('X-Oneapi-Request-Id') or hdrs.get('X-Request-Id')
    billing['upstream_model'] = resp.get('model')
    resp['_billing'] = billing
    return resp


def chat_stream(cfg, messages, on_delta=None, tools=None, timeout=None):
    """流式调用网关。on_delta(kind, piece) 会被逐块回调：kind = "reasoning" | "content"。

    返回与 chat() 同形状的 resp（含 _billing），保证上层代码不用改。
    usage 缺失时按字符估算，并标 usage_estimated=True（绝不静默记 0）。
    """
    g = gateway_cfg(cfg if isinstance(cfg, dict) else None)
    if not g['enabled']:
        raise GatewayAuthError(
            '尚未登录：找不到客户专属令牌（config/user_token.json）。'
            '请先在软件里登录账号，再使用模型功能。')
    model = map_model(g, cfg.get('model'))
    body = {'model': model, 'messages': messages,
            'temperature': (1 if model == 'pro' else cfg.get('temperature', 0.3)),
            'stream': True, 'stream_options': {'include_usage': True}}
    if cfg.get('max_tokens'):
        body['max_tokens'] = int(cfg['max_tokens'])
    extra_keys = []
    if isinstance(cfg.get('extra_body'), dict):
        extra_keys = list(cfg['extra_body'])
        body.update(cfg['extra_body'])
    if tools:
        body['tools'] = tools
        body['tool_choice'] = 'auto'

    url = str(g['base']).rstrip('/') + '/chat/completions'
    tm = float(timeout or g.get('timeout') or 300)
    req = request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                          headers={'Content-Type': 'application/json',
                                   'Accept': 'text/event-stream',
                                   'Authorization': 'Bearer ' + str(g['downstream_key'])},
                          method='POST')

    text, reasoning, usage = '', '', None
    try:
        resp = request.urlopen(req, timeout=tm)
    except HTTPError as e:
        detail = b''
        try:
            detail = e.read()[:300]
        except Exception:
            pass
        _kind = classify_gateway_error(e.code, detail)
        if _kind == 'auth':
            raise GatewayAuthError(friendly_gateway_error(e.code, detail))
        if _kind == 'db':
            raise WorkerError(DB_HINT + '（HTTP %s）' % e.code)
        if e.code in (400, 403) and extra_keys:
            for k in extra_keys:
                body.pop(k, None)
            req = request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                  headers={'Content-Type': 'application/json',
                                           'Accept': 'text/event-stream',
                                           'Authorization': 'Bearer ' + str(g['downstream_key'])},
                                  method='POST')
            resp = request.urlopen(req, timeout=tm)
        else:
            raise HTTPError(e.url, e.code, e.msg, e.hdrs,
                            __import__('io').BytesIO(detail or b''))

    with resp:
        for raw in resp:
            line = raw.decode('utf-8', 'replace').strip()
            if not line.startswith('data:'):
                continue
            payload = line[5:].strip()
            if payload == '[DONE]':
                break
            try:
                obj = json.loads(payload)
            except ValueError:
                continue
            if obj.get('usage'):
                usage = obj['usage']
            for ch in obj.get('choices') or []:
                d = ch.get('delta') or {}
                piece = d.get('content') or ''
                think = d.get('reasoning_content') or ''
                if think:
                    reasoning += think
                    if on_delta:
                        on_delta('reasoning', think)
                if piece:
                    text += piece
                    if on_delta:
                        on_delta('content', piece)
            if obj.get('error'):
                raise WorkerError('上游返回错误：%s' % str(obj['error'])[:200])

    estimated = False
    if not usage:
        estimated = True
        pt = max(1, int(len(json.dumps(messages, ensure_ascii=False)) / 1.6))
        ct = max(1, int((len(text) + len(reasoning)) / 1.2))
        usage = {'prompt_tokens': pt, 'completion_tokens': ct,
                 'total_tokens': pt + ct}
    billing = compute_billing(model, usage, g)
    billing['usage_estimated'] = estimated
    # 估算 + 拿不到价格时 cny 会是 0：显式标出来，别让它看着像「免费」
    if estimated and float(billing.get('total_cny') or 0) == 0:
        billing['billing_uncertain'] = True
    billing['reasoning_chars'] = len(reasoning)
    resp_obj = {'choices': [{'message': {'role': 'assistant', 'content': text},
                             'finish_reason': 'stop'}],
                'usage': usage, 'model': resp.headers.get('X-Upstream-Model') or model,
                'reasoning_content': reasoning,
                '_billing': billing}
    return resp_obj


AUTH_HINT = '登录已失效，请重新登录（网关拒绝了这个令牌）'
DB_HINT = '网关数据库异常（令牌指向的用户可能已被删除），请稍后重试或联系管理员'


def classify_gateway_error(status, body):
    """返回 'auth' | 'db' | 'other'。

    - 401/403：真认证失败
    - 500/5xx + "database error" / "record not found"：网关数据问题（令牌孤儿），不是重登能解决
    - 500 + token/unauthorized：仍按认证失败
    - 其它：原样上抛
    """
    try:
        text = body.decode('utf-8', 'replace') if isinstance(body, (bytes, bytearray)) else str(body or '')
    except Exception:
        text = str(body)[:200]
    low = text.lower()
    if status in (401, 403):
        return 'auth'
    if status >= 500:
        if 'database error' in low or 'record not found' in low:
            return 'db'
        if 'token' in low or 'unauthorized' in low or 'invalid token' in low:
            return 'auth'
    if 'invalid token' in low:
        return 'auth'
    return 'other'


def friendly_gateway_error(status, body):
    kind = classify_gateway_error(status, body)
    if kind == 'auth':
        return AUTH_HINT
    if kind == 'db':
        return DB_HINT
    try:
        text = body.decode('utf-8', 'replace') if isinstance(body, (bytes, bytearray)) else str(body or '')
    except Exception:
        text = str(body)[:200]
    return text[:200] or ('HTTP %s' % status)


def chat(cfg, messages, tools=None):
    """调模型：只走本地 new-api 网关（统一计费 + 额度受控）。

    没有登录令牌时直接报错，不退回直连厂商、也不用开发密钥兜底 ——
    否则客户机一旦漏出 key，就是平台替别人付钱。
    """
    g = gateway_cfg(cfg if isinstance(cfg, dict) else None)
    if g['enabled']:
        return _gateway_chat(cfg, messages, tools, g)
    raise GatewayAuthError(
        '尚未登录：找不到客户专属令牌（config/user_token.json）。'
        '请先在软件里登录账号，再使用模型功能。')

# ---------------- 工具实现 ----------------
#
# 权限模型（2026-11-10 按 YG 要求放开）：助手默认可读写整台机器。
#   config/coordinator.json → agent.full_access（默认 true）
#   agent.read_limit / cmd_timeout / cmd_output_limit 控制单次上限，防止上下文被顶爆。
# 关掉 full_access 就回到老行为：一切路径相对 ROOT，出界拒绝。

AGENT_DEFAULTS = {'full_access': True, 'read_limit': 20000, 'cmd_timeout': 120, 'cmd_output_limit': 8000}


def _agent_cfg():
    try:
        a = (load_cfg() or {}).get('agent') or {}
        if not isinstance(a, dict):
            a = {}
    except Exception:
        a = {}
    out = dict(AGENT_DEFAULTS)
    out.update({k: v for k, v in a.items() if v is not None})
    return out


def _agent_root():
    """助手的工作根：客户数据目录（projects/ 的上一级），不是安装目录 resources。

    2026-11-10 修：以前 list_files/run_command 默认落在 ROOT（win-unpacked/resources），
    而 run_qc 的项目根在 data/projects —— 同一个 "projects" 在两个工具里指向不同地方，
    不报错但会改错文件。现在统一成数据根。
    """
    try:
        pr = os.path.abspath(projects_root())
        parent = os.path.dirname(pr)
        if os.path.isdir(parent):
            return parent
    except Exception:
        pass
    return os.path.abspath(ROOT)


def _resolve_path(path, want_dir=False):
    """把工具参数解析成真实路径。

    full_access=true：绝对路径照用，相对路径仍相对 ROOT（方便模型写 projects/...）。
    full_access=false：老规则，只许 ROOT 之内。
    返回 (abs_path, error)。
    """
    raw = str(path or '').strip().strip('"').strip("'")
    cfg_ = _agent_cfg()
    base_root = _agent_root()
    if cfg_.get('full_access'):
        if not raw:
            return base_root, None
        p = raw if os.path.isabs(raw) else os.path.join(base_root, raw)
        p = os.path.abspath(os.path.expandvars(os.path.expanduser(p)))
        return p, None
    root = base_root
    p = os.path.abspath(os.path.join(root, raw))
    if p != root and not p.startswith(root + os.sep):
        return None, '[不能跳出项目目录] %s' % raw
    return p, None


def tool_read_file(path):
    p, err = _resolve_path(path)
    if err:
        return err
    if os.path.isdir(p):
        return '[这是目录，用 list_files] %s' % p
    if not os.path.exists(p):
        return f'[不存在] {path}'
    # 只从磁盘拿前 4MB：以前是整文件读进来再截 20000 字，
    # 模型一旦去读 400MB 的 app.asar 就会卡住几十秒（2026-11-10 自检卡死的元凶之一）
    READ_BYTES = 4 * 1024 * 1024
    try:
        fsize = os.path.getsize(p)
        with open(p, 'rb') as f:
            blob = f.read(READ_BYTES + 1)
    except OSError as e:
        return '[读不了] %s: %s' % (type(e).__name__, e)
    file_truncated = len(blob) > READ_BYTES
    if file_truncated:
        blob = blob[:READ_BYTES]
    for enc in ('utf-8', 'gbk', 'gb18030', 'utf-16'):
        try:
            txt = blob.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return '[编码认不出来（试过 utf-8/gbk/gb18030/utf-16）] %s' % p
    limit = int(_agent_cfg().get('read_limit') or 20000)
    if len(txt) > limit:
        return txt[:limit] + '\n…[截断：只给了前 %d 字；文件 %.1f MB%s]' % (
            limit, fsize / 1024.0 / 1024.0, '，超过 4MB 只读了开头' if file_truncated else '')
    if file_truncated:
        return txt + '\n…[文件 %.1f MB，只读了开头 4MB]' % (fsize / 1024.0 / 1024.0)
    return txt


LAST_COMMIT_AUTO = {}


def _maybe_commit_chapter(path, content):
    """写章工具落了正文之后，自动提取事实并提交（正文与账本解耦，失败不动正文）。"""
    if os.environ.get('NOVELAPP_AUTO_COMMIT') == '0':
        return None
    norm = str(path or '').replace('\\', '/')
    m = re.search(r'projects/([^/]+)/章节/(\d{3})[^/]*\.md$', norm)
    if not m:
        return None
    book, ch = m.group(1), m.group(2)
    try:
        import chapter_commit as CC
        import stages as ST
        import precheck as PC
        pre = PC.precheck(book, ch, content)
        if not pre.get('passed'):
            reason = '机检未过：%s' % (pre['blocking'][0].get('detail') if pre.get('blocking') else '未知')
            ST.set_stage(book, ch, 'blocked', reason=reason, source='writing', action='retry')
            LAST_COMMIT_AUTO.clear()
            LAST_COMMIT_AUTO.update({'ok': False, 'chapter': ch, 'error': reason,
                                     'precheck': pre})
            return {'ok': False, 'chapter': ch, 'stage': 'blocked', 'error': reason,
                    'precheck': pre}
        res = CC.commit_chapter(book, ch, content, precheck=pre)
        LAST_COMMIT_AUTO.clear()
        LAST_COMMIT_AUTO.update(res)
        if res.get('ok'):
            st, reason, action = 'awaiting', '已完成四层流水线，已入账 %d 条事件' % (
                res.get('events') or 0), 'confirm'
        else:
            st, reason, action = 'blocked', res.get('error') or '事实入账失败', 'retry'
        ST.set_stage(book, ch, st, reason=reason, source='writing', action=action)
        return res
    except Exception as e:
        LAST_COMMIT_AUTO.clear()
        LAST_COMMIT_AUTO.update({'ok': False, 'chapter': ch,
                                 'error': '%s: %s' % (type(e).__name__, e)})
        return None


def tool_write_file(path, content):
    p, err = _resolve_path(path)
    if err:
        return err
    if os.path.isdir(p):
        return '[这是目录，得给文件名] %s' % p
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # 覆盖前留一份备份，别让一次误写毁掉正文
    if os.path.exists(p):
        try:
            bak = p + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
            with open(p, encoding='utf-8') as f:
                old = f.read()
            with open(bak, 'w', encoding='utf-8') as f:
                f.write(old)
        except OSError:
            pass
    open(p, 'w', encoding='utf-8').write(content)
    return f'已写入 {path}（{len(content)} 字）'


# ---------------- 后台任务（job_*）：长命令不再被 120 秒掐死 ----------------
JOB_SEQ = {'n': 0}


def _jobs_dir():
    d = os.path.join(projects_root(), '..', 'agent-jobs')
    d = os.path.abspath(d)
    os.makedirs(d, exist_ok=True)
    return d


def _job_state(jid):
    p = os.path.join(_jobs_dir(), jid + '.json')
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _job_alive(pid):
    if not pid:
        return False
    try:
        out = subprocess.run(['tasklist', '/FI', 'PID eq %d' % int(pid), '/NH'],
                             capture_output=True, timeout=10)
        txt = (out.stdout or b'').decode('utf-8', 'replace') + (out.stderr or b'').decode('utf-8', 'replace')
        return str(int(pid)) in txt
    except Exception:
        return False


# ---------------- 子代理（subagent）：独立的工具循环，跑完只回结论 ----------------
SUBAGENT_SYSTEM = {
    'research': '你是资料研究员子代理。只查能核对的事实与结构，不写正文。做完给结论 + 关键依据，别复述过程。',
    'thinking': '你是剧情参谋子代理。给结构化判断：结论 / 依据 / 风险 / 分支，300 字内。',
    'writing': '你是写手子代理。只输出正文或片段，不解释、不点评、不用代码块。',
    'quality': '你是质检子代理。只报问题：哪一处、为什么、怎么改。不重写全文。',
}


def _subagent_run(task, role, cfg, max_steps=8):
    """一个独立的小 agent：自己的对话、自己的工具循环，跑完只把结论交回去。"""
    sys_prompt = SUBAGENT_SYSTEM.get(resolve_role(role) or '', SUBAGENT_SYSTEM['research'])
    msgs = [{'role': 'system', 'content': sys_prompt},
            {'role': 'user', 'content': str(task or '')[:8000]}]
    for _ in range(max_steps):
        resp = chat(cfg, msgs, TOOLS)
        msg = ((resp.get('choices') or [{}])[0].get('message') or {})
        calls = msg.get('tool_calls') or []
        content = (msg.get('content') or '').strip()
        if not calls:
            return content or '[子任务没有输出]'
        msgs.append({'role': 'assistant', 'content': content, 'tool_calls': calls})
        for tc in calls:
            fn = tc.get('function') or {}
            name = fn.get('name') or ''
            try:
                args = json.loads(fn.get('arguments') or '{}')
            except Exception:
                args = {}
            try:
                out = dispatch_tool(name, args, cfg)
            except Exception as ex:
                out = '[工具异常] %s: %s' % (name, ex)
            msgs.append({'role': 'tool', 'tool_call_id': tc.get('id'), 'content': str(out)[:8000]})
    return '[子任务跑到 %d 步没收敛]' % max_steps


def tool_subagent(task, role='research', cfg=None):
    """派一个带工具的独立子任务，等它给结论。"""
    a = _agent_cfg()
    if not a.get('subagents', True):
        return '[子代理已关闭]（设置 → 通用 → 子代理）'
    if not str(task or '').strip():
        return '[task 不能为空]'
    try:
        return _subagent_run(task, role, cfg or load_cfg().get('coordinator', {}))
    except Exception as ex:
        return '[子任务失败] %s: %s' % (type(ex).__name__, ex)


def tool_subagent_parallel(tasks, cfg=None):
    """并行跑多个子任务。客户开关：agent.parallel_subagents（默认关，开了才花钱）。"""
    import threading
    a = _agent_cfg()
    if not a.get('subagents', True):
        return '[子代理已关闭]（设置 → 通用 → 子代理）'
    if not a.get('parallel_subagents'):
        return '[并行子任务没开]（设置 → 通用 → 并行子任务）；可以改用 subagent 一个个来'
    try:
        items = json.loads(tasks) if isinstance(tasks, str) else list(tasks or [])
    except Exception:
        return '[tasks 要 JSON 数组] 例如 [{"role":"research","task":"查 XX"},{"role":"quality","task":"查这段的问题"}]'
    if not isinstance(items, list) or not items:
        return '[tasks 要是非空数组]'
    if len(items) > 4:
        items = items[:4]
    results = [None] * len(items)
    c = cfg or load_cfg().get('coordinator', {})

    def run(i, it):
        results[i] = _subagent_run(it.get('task', ''), it.get('role', 'research'), c)

    threads = [threading.Thread(target=run, args=(i, it), daemon=True) for i, it in enumerate(items)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=180)
    out = []
    for i, it in enumerate(items):
        out.append('[%d] %s（%s）\n%s' % (i + 1, str(it.get('task', ''))[:60], it.get('role', 'research'),
                                          results[i] or '（超时/无结果）'))
    return '\n\n'.join(out)


# ---------------- 问客户（ask_user）：由宿主注册回调，模型能弹选项 ----------------
ASK_HOOK = None


def tool_ask_user(question, options=''):
    """把问题抛给客户并等回答。真正的弹窗由宿主（server /api/assistant）注册的 ASK_HOOK 做。"""
    q = str(question or '').strip()[:400]
    if not q:
        return '[问题不能为空]'
    opts = [x.strip() for x in str(options or '').replace('，', '|').replace(',', '|').split('|') if x.strip()][:6]
    hook = ASK_HOOK
    if hook is None:
        return '[当前通道不支持弹窗提问] 直接把问题写在回答里，让客户回一句'
    try:
        ans = hook(q, opts)
    except Exception as ex:
        return '[提问失败] %s: %s' % (type(ex).__name__, ex)
    return '客户的回答：%s' % (ans or '（没有回答）')


def tool_job_start(cmd, cwd='', name=''):
    """起一个后台任务：立即返回 job id，输出落到日志文件，随时用 job_output 看。"""
    if not str(cmd or '').strip():
        return '[命令是空的]'
    cfg_ = _agent_cfg()
    raw = str(cwd or '').strip().strip('"')
    base = os.path.abspath(raw) if raw and os.path.isabs(raw) else os.path.abspath(os.path.join(_agent_root(), raw))
    if not os.path.isdir(base):
        return '[目录不存在] %s' % (cwd or base)
    JOB_SEQ['n'] += 1
    jid = 'j%s-%d' % (time.strftime('%Y%m%d-%H%M%S'), JOB_SEQ['n'])
    d = _jobs_dir()
    logp = os.path.join(d, jid + '.log')
    wrapped = '(chcp 65001 >nul) & ' + str(cmd)
    try:
        lf = open(logp, 'wb')
        proc = subprocess.Popen(wrapped, shell=True, cwd=base, stdout=lf,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    except Exception as ex:
        return '[起不来] %s: %s' % (type(ex).__name__, ex)
    meta = {'id': jid, 'cmd': str(cmd), 'cwd': base, 'pid': proc.pid,
            'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'name': str(name or '')[:40],
            'log': logp}
    try:
        with open(os.path.join(d, jid + '.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False)
    except OSError:
        pass
    return ('已起后台任务 %s（pid %d，cwd %s）\n看进度：job_output %s；停下：job_kill %s'
            % (jid, proc.pid, base, jid, jid))


def tool_job_output(jid, tail=4000):
    """看后台任务的输出尾巴 + 状态。"""
    jid = str(jid or '').strip()
    meta = _job_state(jid)
    if not meta:
        return '[没有这个任务] %s\n用 job_list 看现有任务' % (jid or '(空)')
    alive = _job_alive(meta.get('pid'))
    try:
        size = os.path.getsize(meta['log'])
        with open(meta['log'], 'rb') as f:
            f.seek(max(0, size - int(tail or 4000) * 3))
            blob = f.read()
        txt = ''
        for enc in ('utf-8', 'gbk'):
            try:
                txt = blob.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if not txt:
            txt = blob.decode('utf-8', 'replace')
    except Exception as ex:
        txt = '[读日志失败] %s: %s' % (type(ex).__name__, ex)
    head = '任务 %s（%s）pid=%s %s\n命令：%s\ncwd：%s\n--- 输出尾部 ---\n' % (
        jid, meta.get('started'), meta.get('pid'),
        '运行中' if alive else '已结束', meta.get('cmd'), meta.get('cwd'))
    return head + (txt.strip() or '（还没有输出）')


def tool_job_list():
    """列出所有后台任务。"""
    d = _jobs_dir()
    rows = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.json'):
            continue
        meta = _job_state(fn[:-5])
        if not meta:
            continue
        rows.append('%s  %s  %s  pid=%s  %s' % (
            meta.get('id'), '运行中' if _job_alive(meta.get('pid')) else '已结束',
            meta.get('started'), meta.get('pid'), (meta.get('cmd') or '')[:60]))
    if not rows:
        return '[没有后台任务]'
    return '共 %d 个：\n%s' % (len(rows), '\n'.join(rows))


def tool_job_kill(jid):
    """杀掉后台任务（连子进程一起）。"""
    jid = str(jid or '').strip()
    meta = _job_state(jid)
    if not meta:
        return '[没有这个任务] %s' % (jid or '(空)')
    pid = meta.get('pid')
    if not _job_alive(pid):
        return '任务 %s 已经结束了（pid %s）' % (jid, pid)
    try:
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                       capture_output=True, timeout=20)
    except Exception as ex:
        return '[杀不掉] %s: %s' % (type(ex).__name__, ex)
    time.sleep(1)
    return '已杀 %s（pid %s）：%s' % (jid, pid, '还在跑' if _job_alive(pid) else '已停止')


def tool_edit(path, old_string, new_string, replace_all=False):
    """片段替换（同 dsh 的 edit）：只改命中的那一段，不整文件重写。

    规则：
      · old_string 必须原样出现；出现多处时默认报错（要求给得更长），replace_all=true 才全换
      · 找不到就把文件里最接近的行提示出来，让模型自己修正
      · 改前照旧留 .bak-时间戳
    """
    p, err = _resolve_path(path)
    if err:
        return err
    if not os.path.isfile(p):
        return '[文件不存在] %s' % p
    try:
        with open(p, encoding='utf-8') as f:
            cur = f.read()
    except UnicodeDecodeError:
        return '[不是 UTF-8 文本，edit 只能改文本文件] %s' % p
    old = '' if old_string is None else str(old_string)
    new = '' if new_string is None else str(new_string)
    if old == '':
        return '[old_string 不能为空] 要整文件重写请用 write_file'
    hits = cur.count(old)
    if hits == 0:
        # 给个线索：找最像的一行
        needle = old.strip().splitlines()[0][:30] if old.strip() else ''
        near = ''
        if needle:
            for line in cur.splitlines():
                if needle[:8] and needle[:8] in line:
                    near = '\n最接近的一行：' + line.strip()[:120]
                    break
        return '[没找到要替换的片段] %s%s\n提示：先用 read_file 或 grep 确认原文（空格/全角半角都要一致）' % (p, near)
    if hits > 1 and not replace_all:
        return '[片段出现 %d 次，改哪一处不明确] %s\n把 old_string 写长一点（带上上下文），或传 replace_all=true' % (hits, p)
    bak = p + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
    n = 1
    while os.path.exists(bak):          # 同一秒改两次也别互相覆盖
        bak = '%s.bak-%s-%d' % (p, time.strftime('%Y%m%d-%H%M%S'), n)
        n += 1
    try:
        with open(bak, 'w', encoding='utf-8') as f:
            f.write(cur)
    except OSError:
        pass
    out = cur.replace(old, new) if replace_all else cur.replace(old, new, 1)
    try:
        with open(p, 'w', encoding='utf-8') as f:
            f.write(out)
    except OSError as ex:
        return '[写不进去] %s: %s' % (type(ex).__name__, ex)
    delta = len(out) - len(cur)
    return '已改 %s：%d 处，长度 %+d 字（备份 %s）' % (
        p, hits if replace_all else 1, delta, os.path.basename(bak))


def tool_grep(pattern, path='', include='', max_hits=200):
    """正则搜索文件内容（纯 Python，不依赖 rg；中文安全）。"""
    pat = str(pattern or '')
    if not pat:
        return '[pattern 不能为空]'
    try:
        rx = re.compile(pat)
    except re.error as ex:
        return '[正则写错了] %s' % ex
    root, err = _resolve_path(path or '.')
    if err:
        return err
    exts = [e.strip().lower() for e in str(include or '').split(',') if e.strip()]
    skip_dirs = {'.git', 'node_modules', '__pycache__', '.layers', 'dist', 'build', 'app.asar.unpacked'}
    files = []
    if os.path.isfile(root):
        files = [root]
    else:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                low = fn.lower()
                if exts and not any(low.endswith(x if x.startswith('.') else '.' + x) for x in exts):
                    continue
                files.append(os.path.join(dirpath, fn))
    out, scanned = [], 0
    for fp in files:
        try:
            if os.path.getsize(fp) > 8 * 1024 * 1024:
                continue
            with open(fp, 'rb') as f:
                blob = f.read()
        except OSError:
            continue
        txt = None
        for enc in ('utf-8', 'gbk'):
            try:
                txt = blob.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if txt is None:
            continue
        scanned += 1
        for i, line in enumerate(txt.splitlines(), 1):
            if rx.search(line):
                out.append('%s:%d: %s' % (fp, i, line.strip()[:200]))
                if len(out) >= max_hits:
                    break
        if len(out) >= max_hits:
            break
    if not out:
        return '[没有命中] pattern=%r 扫了 %d 个文件（%s）' % (pat, scanned, root)
    head = '命中 %d 条（扫了 %d 个文件，最多列 %d）：\n' % (len(out), scanned, max_hits)
    return head + '\n'.join(out)


def tool_glob(pattern, path='', max_hits=300):
    """按通配符找文件（* ** ?），返回路径列表。"""
    import fnmatch
    pat = str(pattern or '').strip()
    if not pat:
        return '[pattern 不能为空]'
    root, err = _resolve_path(path or '.')
    if err:
        return err
    pat_norm = pat.replace('\\', '/')
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('.git', 'node_modules', '__pycache__')]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace('\\', '/')
            if fnmatch.fnmatch(rel, pat_norm) or fnmatch.fnmatch(fn, pat_norm):
                out.append(full)
                if len(out) >= max_hits:
                    break
        if len(out) >= max_hits:
            break
    if not out:
        return '[没有匹配] %r（在 %s 下）' % (pat, root)
    return '匹配 %d 个（最多列 %d）：\n%s' % (len(out), max_hits, '\n'.join(out))


def tool_list_files(sub=''):
    p, err = _resolve_path(sub, want_dir=True)
    if err:
        return err
    if os.path.isfile(p):
        return '[这是文件，不是目录] %s' % p
    if not os.path.isdir(p):
        return f'[不是目录] {sub}'
    try:
        names = sorted(os.listdir(p))
    except OSError as e:
        return '[列不了] %s: %s' % (type(e).__name__, e)
    lines = []
    for n in names[:600]:
        full = os.path.join(p, n)
        try:
            lines.append(n + ('/' if os.path.isdir(full) else '  %d B' % os.path.getsize(full)))
        except OSError:
            lines.append(n)
    if len(names) > 600:
        lines.append('…[共 %d 项，只列前 600]' % len(names))
    return '\n'.join(lines)


def _unesc(s):
    try:
        from html import unescape
        return unescape(str(s or ''))
    except Exception:
        return str(s or '')


# --- 技能库：扫项目根的 skills/novel，读 SKILL.md 的 frontmatter ---------------
# 为什么 Python 侧也要一套：客户日常用的是右栏助手（/api/chat → 这里的 agent），
# 不是 DSH 原生会话。技能只进 DSH 的话，面板能看、助理用不上，等于没有。

def _skill_roots():
    out = []
    env = os.environ.get('NOVELAPP_SKILLS')
    if env:
        out.append(env)
    out.append(os.path.join(ROOT, 'skills', 'novel'))
    return [p for p in out if os.path.isdir(p)]


def _frontmatter(text):
    """取 SKILL.md 头里的 name / description。

    要支持 YAML 块标量：description 经常写成 `description: |` 或 `>` 再换行缩进，
    只按单行正则取会拿到一个「|」或「>」（第一版就是这么错的）。
    """
    if not text.startswith('---'):
        return {}
    end = text.find('\n---', 3)
    if end < 0:
        return {}
    lines = text[3:end].splitlines()
    out = {}
    i = 0
    while i < len(lines):
        m = re.match(r'^\s*(name|description)\s*:\s*(.*)$', lines[i])
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in ('|', '>', '|-', '>-', '|+', '>+'):
            parts = []
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i][:1] in (' ', '\t')):
                if lines[i].strip():
                    parts.append(lines[i].strip())
                i += 1
            out[key] = ' '.join(parts)
            continue
        out[key] = val.strip('\'"')
        i += 1
    return out


def _data_skills_dir():
    base = os.environ.get('NOVELAPP_DATA') or os.path.join(
        os.path.expanduser('~'), 'AppData', 'Roaming', 'novelapp-desktop', 'data')
    return os.path.join(base, 'skills')


def _skill_overrides():
    """面板里关掉哪些技能。存在 data/skills/_overrides.json，Node 侧和这里共用一份。"""
    try:
        with open(os.path.join(_data_skills_dir(), '_overrides.json'), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def list_skills():
    """两套技能合并成一份清单。

    为什么要合：面板读的是 data/skills（内置 6 个可开关），agent 以前只认
    skills/novel 的 SKILL.md（写作体系 8 个）。结果客户在面板里关技能对 agent
    无效、agent 有的技能面板上又看不见 —— 两边各说各话。

    返回 [{id, name, category, desc, enabled, source, chars, path}]，
    字段和 Node 侧 /novelapp/skills 对齐，前端不用分辨来源。
    """
    out = []
    seen = set()
    ov = _skill_overrides()

    # ① 内置：data/skills/<id>/{skill.json, prompt.md}
    base = _data_skills_dir()
    try:
        names = sorted(os.listdir(base))
    except OSError:
        names = []
    for nm in names:
        d = os.path.join(base, nm)
        if not os.path.isdir(d):
            continue
        meta = {}
        try:
            with open(os.path.join(d, 'skill.json'), encoding='utf-8') as f:
                meta = json.load(f)
        except Exception:
            meta = {}
        pm = os.path.join(d, 'prompt.md')
        chars = 0
        try:
            with open(pm, encoding='utf-8', errors='replace') as f:
                chars = len(f.read().strip())
        except OSError:
            chars = 0
        sid = str(meta.get('id') or nm)
        out.append({'id': sid, 'name': str(meta.get('name') or nm),
                    'category': str(meta.get('category') or '正文'),
                    'desc': str(meta.get('desc') or ''),
                    'enabled': meta.get('enabled') is not False,
                    'source': 'builtin', 'chars': chars,
                    'path': pm if chars else ''})
        seen.add(sid)

    # ② 写作体系：skills/novel/**/SKILL.md
    for root in _skill_roots():
        for dirpath, _, files in os.walk(root):
            for fn in files:
                if fn.lower() != 'skill.md':
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    with open(p, encoding='utf-8', errors='replace') as f:
                        txt = f.read()
                except OSError:
                    continue
                fm = _frontmatter(txt[:4000])
                nm = str(fm.get('name') or os.path.basename(dirpath))
                if nm in seen:
                    continue
                desc = ' '.join((fm.get('description') or '').split())
                out.append({'id': nm, 'name': nm, 'category': '写作体系',
                            'desc': desc, 'enabled': ov.get(nm) is not False,
                            'source': 'novel', 'chars': len(txt.strip()), 'path': p})
                seen.add(nm)

    out.sort(key=lambda x: (x['source'] != 'builtin', x['name']))
    return out


def load_skill(name, limit=8000):
    """按 id 取技能正文：内置读 prompt.md，写作体系读 SKILL.md。关掉的不给。"""
    want = str(name or '').strip()
    items = list_skills()
    hit = None
    for it in items:
        if it['id'] == want or it['name'] == want:
            hit = it
            break
    if not hit:
        names = '、'.join(i['id'] for i in items if i['enabled']) or '（库里没有技能）'
        return '[没有这个技能] %s。现有：%s' % (want, names)
    if not hit['enabled']:
        return '[这个技能被关掉了] %s —— 去「技能」面板重新打开' % hit['name']
    if not hit['path']:
        return '[这个技能还没有内容] %s（prompt.md 是空的，先去面板里填）' % hit['name']
    try:
        with open(hit['path'], encoding='utf-8', errors='replace') as f:
            return f.read()[:limit]
    except OSError as e:
        return '[读不了] %s' % e


def skill_catalog():
    """给 system 消息用的清单：只列开着的、名字 + 一句描述，正文按需取。"""
    items = [i for i in list_skills() if i['enabled']]
    if not items:
        return ''
    lines = ['可用技能（需要正文就调 skill 工具取，不要凭名字猜内容）：']
    for it in items:
        d = (it['desc'] or '（无描述）')
        if it['source'] == 'builtin':
            lines.append('- %s：%s' % (it['id'], d[:70]))
        else:
            lines.append('- %s：%s' % (it['id'], d[:70]))
    return '\n'.join(lines)


# 搜索没开时返回给模型的那句话。前端设置页那行小字是同一层意思，改文案要两边一起改。
SEARCH_OFF_MSG = ('[联网搜索没开] 去「设置」打开「联网搜索」才能用。'
                  '默认关闭是因为搜索源是 Bing 的 RSS，它只允许个人非商业用途；'
                  '开之前请自己确认这个用法对你没问题。')


def tool_web_search(query, limit=5):
    """联网搜索：走 Bing 的 RSS 结果（不需要 key、不需要账号）。

    为什么不走网关：网关（new-api）里没有搜索渠道，DeepSeek 也不支持
    tools:[{type:web_search}]，所以只能直连一个结果源。
    RSS 只给标题/链接/摘要，正文要用 read_web_page 再读。

    默认关闭（search.enabled 缺省 false）：Bing 的 RSS 只允许个人非商业用途。
    关着时这个工具仍然留在 TOOLS 里 —— 模型调了会拿到 SEARCH_OFF_MSG 的明确指引，
    比它压根不知道有这个工具要好。read_web_page 不受这个开关限制（那是客户给的具体链接）。
    """
    if not search_enabled():
        return SEARCH_OFF_MSG
    q = str(query or '').strip()
    if not q:
        return '[搜索词是空的]'
    try:
        from urllib.parse import quote
        url = 'https://www.bing.com/search?q=' + quote(q) + '&format=rss'
        req = request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with request.urlopen(req, timeout=15) as r:
            raw = r.read().decode('utf-8', 'replace')
    except Exception as e:
        return '[搜索失败] %s: %s' % (type(e).__name__, str(e)[:90])
    try:
        n = max(1, min(int(limit or 5), 8))
    except Exception:
        n = 5
    items = re.findall(r'<item>(.*?)</item>', raw, re.S)
    out = []
    for it in items[:n]:
        t = re.search(r'<title>(.*?)</title>', it, re.S)
        l = re.search(r'<link>(.*?)</link>', it, re.S)
        d = re.search(r'<description>(.*?)</description>', it, re.S)
        out.append('- %s\n  %s\n  %s' % (
            _unesc(t.group(1)).strip() if t else '',
            _unesc(l.group(1)).strip() if l else '',
            _unesc(d.group(1)).strip()[:220] if d else ''))
    return '\n'.join(out) if out else '[没有结果]'


def tool_read_web_page(url, chars=4000):
    """抓一个网页的正文：去 script/style、去标签、压空白，截前 chars 字。"""
    u = str(url or '').strip()
    if not u.lower().startswith(('http://', 'https://')):
        return '[只支持 http/https 地址] %s' % u[:60]
    try:
        req = request.Request(u, headers={
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        try:
            resp = request.urlopen(req, timeout=20)
            note = ''
        except Exception as e1:
            if 'CERTIFICATE' not in str(e1).upper():
                raise
            # 本机装了抓包/代理时会用自签证书；这类客户机上只能跳过校验，
            # 但要明说，不要偷偷降级。
            import ssl
            resp = request.urlopen(req, timeout=20, context=ssl._create_unverified_context())
            note = '（已跳过证书校验：这台机器的网络有中间人代理）\n'
        with resp as r:
            charset = 'utf-8'
            try:
                ct = r.headers.get('Content-Type') or ''
                m = re.search(r'charset=([\w-]+)', ct)
                if m:
                    charset = m.group(1)
            except Exception:
                pass
            raw = r.read().decode(charset, 'replace')
    except Exception as e:
        return '[打开失败] %s: %s（有些站点会挡程序访问，换一个链接试试）' % (type(e).__name__, str(e)[:90])
    txt = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', raw)
    txt = re.sub(r'(?s)<!--.*?-->', ' ', txt)
    txt = re.sub(r'(?is)<(br|/p|/div|/li|/h\d)[^>]*>', '\n', txt)
    txt = re.sub(r'(?s)<[^>]+>', ' ', txt)
    txt = _unesc(txt)
    txt = re.sub(r'[ \t\r\f\v]+', ' ', txt)
    txt = re.sub(r'\n\s*\n+', '\n\n', txt).strip()
    try:
        k = max(500, min(int(chars or 4000), 12000))
    except Exception:
        k = 4000
    if not txt:
        return '[页面没有可取的文字]'
    return note + txt[:k]


def tool_run_command(cmd, cwd=''):
    """在整台机器上跑一条命令（默认 cwd = 项目根），返回退出码 + 输出。

    权限：full_access=true 时 cwd 可以是任意绝对路径（2026-11-10 按 YG 要求放开）；
    关掉就回到「cwd 不许跳出 ROOT」。命令本身不拦 —— 这是操作者在自己机器上让 AI 干活。
    超时与输出上限读 config 的 agent.cmd_timeout / agent.cmd_output_limit。
    """
    if not str(cmd or '').strip():
        return '[命令是空的]'
    cfg_ = _agent_cfg()
    if cfg_.get('full_access'):
        raw = str(cwd or '').strip().strip('"')
        base = os.path.abspath(raw) if raw and os.path.isabs(raw) else os.path.abspath(os.path.join(_agent_root(), raw))
    else:
        root = _agent_root()
        base = os.path.abspath(os.path.join(root, cwd or ''))
        if base != root and not base.startswith(root + os.sep):
            return '[不能跳出项目目录] %s' % cwd
    if not os.path.isdir(base):
        return '[目录不存在] %s' % (cwd or base)
    to = int(cfg_.get('cmd_timeout') or 120)
    olim = int(cfg_.get('cmd_output_limit') or 8000)
    # 中文坑：cmd 默认代码页 936，脚本输出 UTF-8 → 全乱码；中文当参数也会因为编码对不上匹配失败。
    # 先切 65001，再跑；解码按 utf-8 → gbk → replace 三级回退。
    wrapped = '(chcp 65001 >nul) & ' + cmd
    try:
        p = subprocess.run(wrapped, shell=True, cwd=base, capture_output=True, timeout=to)
    except subprocess.TimeoutExpired:
        return '[超时 %d 秒] %s' % (to, cmd)
    except Exception as e:
        return '[%s] %s' % (type(e).__name__, e)
    out = (p.stdout or b'') + (p.stderr or b'')
    txt = ''
    for enc in ('utf-8', 'gbk'):
        try:
            txt = out.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not txt:
        txt = out.decode('utf-8', 'replace')
    txt = txt.strip() or '（无输出）'
    if len(txt) > olim:
        txt = txt[:olim] + '\n…[输出截断：共 %d 字]' % len(txt)
    return '[exit %d @ %s]\n%s' % (p.returncode, base, txt)


def tool_run_qc(chapter):
    """跑 L1/L2 质检；给文件名时在 projects/ 下自动找。"""
    # 2026-11-10 修：这里原来把找到的文件 relpath 成相对 ROOT 的路径，
    # ROOT 在 C:、项目在 D: 时直接 ValueError: path is on mount 'C:', start on mount 'D:'。
    # 现在全程绝对路径，并且给目录/不存在两种情况都说清楚。
    raw = str(chapter or '').strip().strip('"')
    if not raw:
        return '[要给章节名] 例如 <书名>/章节/001-柴没砍完.md'
    if os.path.isabs(raw):
        cand = raw
    else:
        # 客户/模型可能写 <书名>/章节/x.md、projects/<书名>/...、或只给文件名，逐个试
        rel = raw[9:] if raw.lower().startswith('projects/') or raw.lower().startswith('projects\\') else raw
        cands = [os.path.join(_agent_root(), raw), os.path.join(projects_root(), rel), os.path.join(projects_root(), raw)]
        cand = next((c for c in cands if os.path.exists(c)), cands[0])
    if os.path.isdir(cand):
        try:
            names = sorted(n for n in os.listdir(cand) if n.endswith('.md'))[:15]
        except OSError:
            names = []
        return '[这是目录，不是章节文件] %s\n目录里的章节：%s' % (
            cand, ('、'.join(names) if names else '（没有 .md）'))
    if not os.path.exists(cand):
        found = None
        base = raw if raw.endswith('.md') else raw + '.md'
        for dirpath, _, files in os.walk(projects_root()):
            for f in files:
                if not f.endswith('.md'):
                    continue
                if f == base or f == raw or base in f or raw in f:
                    found = os.path.join(dirpath, f)   # 绝对路径，不 relpath
                    break
            if found:
                break
        if not found:
            try:
                books = sorted(n for n in os.listdir(projects_root()) if os.path.isdir(os.path.join(projects_root(), n)))
            except OSError:
                books = []
            return '[找不到章节] %s\n现有书：%s\n可以先用 list_files(\'projects\') 看结构' % (
                raw, ('、'.join(books) if books else '（空）'))
        cand = found
    chapter = cand
    try:
        env = dict(os.environ)
        env.setdefault('NOVELAPP_ROOT', ROOT)
        _t0 = time.time()
        r = subprocess.run(script_cmd('scripts/l1_l2_check.py', [chapter]),
                           cwd=ROOT, capture_output=True, timeout=60, env=env)
        # text=True 会用系统代码页解码（cp936），脚本吐 UTF-8 就乱码/报错；这里自己解
        def _dec(b):
            for enc in ('utf-8', 'gbk'):
                try:
                    return (b or b'').decode(enc)
                except UnicodeDecodeError:
                    continue
            return (b or b'').decode('utf-8', 'replace')
        r_stdout, r_stderr = _dec(r.stdout), _dec(r.stderr)
        log_qc_run('scripts/l1_l2_check.py',
                   {'exit': r.returncode, 'ms': int((time.time() - _t0) * 1000)}, r_stderr)
        return (r_stdout or r_stderr)[-1500:]
    except PermissionError as e:
        return '[没有权限跑质检脚本] %s（脚本路径：%s）' % (e, ROOT)
    except Exception as e:
        return f'质检失败: {type(e).__name__}: {e}'


# ---------------- worker 路由 ----------------

ROLE_ALIASES = {
    'research': 'research', 'researcher': 'research', 'scout': 'research',
    '研究': 'research', '研究层': 'research', '资料': 'research',
    'thinking': 'thinking', 'think': 'thinking', 'planner': 'thinking', 'plan': 'thinking',
    '思考': 'thinking', '思考层': 'thinking', '参谋': 'thinking', '策划': 'thinking',
    'writing': 'writing', 'write': 'writing', 'writer': 'writing', 'author': 'writing',
    '写作': 'writing', '写作层': 'writing', '写手': 'writing', '正文': 'writing',
    'quality': 'quality', 'qc': 'quality', 'review': 'quality', 'reviewer': 'quality',
    '质检': 'quality', '质检层': 'quality', '校验': 'quality', '审稿': 'quality',
    'yanjiu': 'research', 'ziliao': 'research',
    'sikao': 'thinking', 'qianzhi': 'thinking', 'cemou': 'thinking',
    'xiezuo': 'writing', 'xieshou': 'writing', 'zhengwen': 'writing',
    'zhijian': 'quality', 'shengao': 'quality',
}

WORKER_SYSTEM = {
    'research': '你是资料研究员。只给可核查的事实、设定依据与参考结构，不写正文。'
                '不要开场白，不要解释自己是谁。',
    'thinking': '你是剧情参谋。给结构化判断：结论 / 依据 / 风险 / 可选分支。'
                '不写正文，篇幅控制在 300 字内。',
    'writing': '你是网文写手。只输出正文或正文片段，不解释、不点评、不写"以下是"。'
               '不加 markdown 代码块。\n'
               '标题只写一次：正文开头可以写一行「# 第 N 章 标题」，'
               '后面不要再出现任何章节标题（不要再写 ## 第 N 章）。\n'
               '正文要写够，不要为了简洁省细节。写完之后自己数一下：'
               '字数不够就补——环境、动作、心理、对话，用具体场面补，不要用概述带过。\n'
               '\n【硬约束·七条：每条都能被规则查出来，不靠感觉】\n'
               '1 动作客观可见。只写看得见、听得到、能计量的东西：谁做了什么、什么东西变了、在哪、多久。'
               '情绪不许贴标签——「心中一凛」「心中一紧」「心里一沉」「感到一阵」一律不写；'
               '情绪只能由动作、身体反应、物件、对话落地（他把茶盏推回去半寸 / 她数了三遍铜板）。'
               '（查：正则 心中一|心里一沉|感到一阵；补字数也不许用情绪直写凑）\n'
               '2 对白只能是人物真说出口的话。引号里不写心理、不写解释、不写旁白，不用引号包叙述；'
               '「他暗想：……」这类一律不许。'
               '（查：正则 “[^”]{0,40}(心想|暗想|想道|内心|心里)）\n'
               '3 引号与标点。只用中文双引号“”，引内再引用‘’；不用「」『』、不用半角引号；左右必须成对。'
               '破折号 0 个，阿拉伯数字 0 个，单段不超过 100 字。'
               '（查：quote_pairs / dash_count / arabic_number / paragraph_length）\n'
               '4 否定式。旁白不许用「他不X／他没X」代替情绪或态度（他不怕／他没恼／他不慌／他没当回事）；'
               '纯事实否定不算（他不识字／天没亮／他没说话）。'
               '（查：短语表 他不怕|他没恼|他不慌|他没当回事|他不心疼）\n'
               '5 转折对仗。「不是……而是……」「不是……，是……」一章最多 1 处，且只许出现在人物对话里；'
               '旁白要对比就把两件事并排放，让读者自己判（他站在那儿，手心出了汗，嘴上还在笑）。'
               '（查：正则 不是[^。！？]{0,20}(而是|是)，数出来）\n'
               '6 时间。不许用「过了几天／许久之后／不知过了多久」跳时间；时间要给可见标记：'
               '日头到哪儿、影子多长、几更、饭点、柴烧到第几根。'
               '（查：短语表 + L4 时间规则）\n'
               '7 不解释不总结。不写「总之／也就是说／这说明／换句话说／不得不说」，'
               '不替读者总结人物动机，不在段尾升华。'
               '（查：正则 总之|也就是说|这说明|换句话说|不得不说|由此可见|仅仅是开始）\n'
               '\n【风格红线：这几条机检查不出来，但审稿会扣分】\n'
               '1 人称。主角名每千字 3–8 次就够——长篇靠「他/她」承接，不靠反复点全名；'
               '同一段里全名不超过 1 次；同一段不许用「我」和「他」指同一个人。'
               '（实测本书 001–004 章是每千字 3.7 / 8.1 / 5.5 次，别按每章 20 次去堆）\n'
               '2 禁用词，出现就改：仿佛 宛如 不禁 若有所思 深邃 眼眸 勾勒 交织 弥漫 氤氲 '
               '彷徨 震撼 淋漓 悄然 一丝 一抹 涌上心头。\n'
               '3 比喻从人物干过的行当里取（樵夫用柴、木、斧、山、雨），不从作者的书架上取；'
               '不用生僻字、不用读者要停下来查字典的词。\n'
               '4 章末留钩子，用动作收或留白收。不升华、不总结、不预告下一章。\n'
               '5 每句台词不配手部动作（点头、笑了笑、叹了口气）。有活才写动作，动作是内容不是标点。\n'
               '\n【写完自查：在同一次输出里做，不许另起一段汇报】\n'
               '正文写完不要交清单，不要写「自查」「检查结果」「以下是」，也不许把上面这些条抄一遍。'
               '按 1→7 默读一遍刚写的字，只做两件事：① 不合格就地改——删套话、把情绪换成动作、'
               '删掉引号外的解释、把「不是…是…」并排改写；② 字数不够就接着往下写场面。'
               '最后只交一份干净正文：没有草稿、没有标记、没有说明。'
               '先扫最容易犯的三条：引号成对 / 破折号与阿拉伯数字 / 「不是…是…」。',
    'quality': '你是质检编辑。按行号列问题：行号 / 问题类型 / 原文片段 / 改法。'
               '只报问题，不改写全文，不改稿。',
}

def cliche_ban_block():
    """写作层禁令：词表来自 config/cliche.json —— 与质检 scripts/l1_l2_check.py 共用同一份，
    改词表不用改代码，两处同时生效。"""
    cands = [os.path.join(ROOT, 'config', 'cliche.json')]
    try:
        import coordinator as _self  # noqa: F401  (占位，避免循环导入问题)
    except Exception as e:
        try:
            _lg = os.path.join(os.environ.get('NOVELAPP_DATA') or '', 'logs')
            os.makedirs(_lg, exist_ok=True)
            with open(os.path.join(_lg, 'prompt-log-error.log'), 'a', encoding='utf-8') as _f:
                _f.write('%s %s\n' % (type(e).__name__, e))
        except Exception:
            pass
    data = None
    for p in cands:
        try:
            with open(p, encoding='utf-8-sig') as f:
                data = json.load(f)
            break
        except Exception:
            data = None
    if not isinstance(data, dict):
        return ''
    groups = data.get('groups') or {}
    if not groups:
        return ''
    lines = ['', '【这一章不许用的句式（质检会打回，写完自己先删干净）】']
    idx = 0
    for key, g in groups.items():
        if not isinstance(g, dict):
            continue
        ph = [str(x) for x in (g.get('phrases') or [])][:14]
        pats = list(g.get('patterns') or [])
        standalone = [str(x) for x in (g.get('standalone') or [])][:8]
        idx += 1
        lines.append('%d. %s' % (idx, g.get('label') or key))
        if ph:
            lines.append('   禁用：' + '、'.join(ph))
        if standalone:
            lines.append('   不许单独成句：' + '、'.join(standalone))
        if pats:
            lines.append('   不许写这类比较：比之前/比刚才/比上次 + 重/轻/稳/平/强 之类')
        hint = g.get('hint')
        if hint:
            lines.append('   换成：' + str(hint))
    lines.append('总则：不许用短句互评（“稳”“我认”“行”）、不许用比较词代替具体刻度、')
    lines.append('不许用“我记下了”代替动作。字数不够就补场面（环境/动作/物件），不要补评语。')
    return '\n'.join(lines)

_SPECIAL_TOKEN_RE = re.compile(r'<[|｜][^<>]{0,80}[|｜]>|<</?SYS>>|\[/?INST\]|</?s>|(?:<\s*){3,}')
_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_ZW_RE = re.compile(r'[\u200b-\u200f\u202a-\u202e\u2060\ufeff]')


class WorkerError(Exception):
    pass


def _log_worker(msg):
    """worker 侧告警落地（logs/worker.log），别只吞在返回值里。"""
    try:
        d = os.path.join(ROOT, 'logs')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'worker.log'), 'a', encoding='utf-8') as f:
            f.write('[%s] %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except OSError:
        pass


class WorkerDisabled(Exception):
    """该层被客户关掉了（layers.yaml enabled: false）——不是错误，是 skipped。"""


_CHAPTER_HEAD_RE = re.compile(r'^#{1,4}\s*第\s*[0-9零一二三四五六七八九十百]{1,6}\s*章')


def _dedupe_heading(text):
    """正文开头重复写同一章标题（# 第 8 章 / ## 第 8 章）时，只留第一个。"""
    lines = text.split('\n')
    seen = False
    out = []
    for ln in lines:
        if _CHAPTER_HEAD_RE.match(ln.strip()):
            if seen:
                continue
            seen = True
        out.append(ln)
    return '\n'.join(out)


_CN_NUM = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
           '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '百': 100}


def _parse_ch_no(s):
    s = str(s or '').strip()
    if s.isdigit():
        return int(s)
    if '十' in s:
        head, _, tail = s.partition('十')
        return (_CN_NUM.get(head, 1) if head else 1) * 10 + (_CN_NUM.get(tail, 0) if tail else 0)
    return _CN_NUM.get(s, 0)


def strip_leading_heading(text, expect_chapter=None):
    """去掉正文开头的章节标题行（写盘时统一成「# 第 N 章」）。

    返回 (清洗后的正文, 警告文本)。expect_chapter 给了且模型写的章号不同，
    警告里会说明——方便查「模型老写错章号」，但落盘永远是正确章号。
    """
    lines = (text or '').split('\n')
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    warning = ''
    if i < len(lines) and _CHAPTER_HEAD_RE.match(lines[i].strip()):
        head = lines[i].strip()
        m = re.search(r'第\s*([0-9零一二三四五六七八九十百]{1,6})\s*章', head)
        if m and expect_chapter:
            got = _parse_ch_no(m.group(1))
            want = _parse_ch_no(str(expect_chapter).lstrip('0') or '0')
            if got and want and got != want:
                warning = ('模型标题章号不匹配（写了第 %s 章），已统一为第 %s 章'
                           % (got, want))
        del lines[i:i + 1]
        while i < len(lines) and not lines[i].strip():
            del lines[i:i + 1]
    return '\n'.join(lines), warning


def sanitize_worker_text(text, limit=None):
    """把 worker 输出清洗成可直接展示/落盘的纯文本。"""
    if text is None:
        return ''
    if not isinstance(text, str):
        text = str(text)
    text = _SPECIAL_TOKEN_RE.sub('', text)
    text = _ZW_RE.sub('', text)
    text = _CTRL_RE.sub('', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'^\s*(assistant|system|user|tool)\s*[:：]?\s*\n', '', text, flags=re.I)
    text = _dedupe_heading(text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    if limit:
        text = text[:limit]
    return text


def resolve_role(role):
    if not isinstance(role, str):
        return None
    key = role.strip()
    if not key:
        return None
    low = key.lower()
    squeezed = re.sub(r'[\s_\-]+', '', low)
    for cand in (low, squeezed, key):
        if cand in ROLE_ALIASES:
            return ROLE_ALIASES[cand]
    return None


def _extract_content(resp):
    """从 OpenAI 兼容响应里取正文；兼容 content 为 str / 分段数组 / 全在 reasoning。"""
    if not isinstance(resp, dict):
        raise WorkerError('响应不是 JSON 对象：' + repr(resp)[:120])
    if resp.get('error'):
        err = resp['error']
        msg = err.get('message') if isinstance(err, dict) else str(err)
        raise WorkerError('上游返回错误：' + str(msg)[:200])
    choices = resp.get('choices') or []
    if not choices:
        raise WorkerError('响应里没有 choices：' + json.dumps(resp, ensure_ascii=False)[:160])
    msg = choices[0].get('message') or {}
    content = msg.get('content')
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                parts.append(p.get('text') or p.get('content') or '')
        content = ''.join(parts)
    if content is None:
        rc = msg.get('reasoning_content') or msg.get('reasoning')
        if isinstance(rc, str) and rc.strip():
            content = rc
        elif msg.get('tool_calls'):
            raise WorkerError('worker 只回了工具调用，没有正文（换个 prompt 再派）')
        else:
            content = ''
    return str(content)


def _log_prompt(role_key, model, system, prompt, sub):
    """NOVELAPP_LOG_PROMPTS=1 时把 worker 的 system/prompt 落盘，用于基线对比。"""
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
            'role': role_key,
            'model': model,
            'temperature': sub.get('temperature'),
            'max_tokens': sub.get('max_tokens'),
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

def chat_worker(role, prompt, cfg, timeout=None):
    """派活给一层：模型/温度/max_tokens 全部按 layers.yaml 走，返回 (清洗后文本, meta)。"""
    key = resolve_role(role)
    if not key:
        raise WorkerError('未知角色 %r，可用：%s' % (role, ', '.join(LAYER_ORDER)))
    layer = resolve_layer(key)
    if not layer.get('enabled', True):
        raise WorkerDisabled('层「%s」已关闭（layers.yaml enabled: false）' % (layer.get('label') or key))
    if not isinstance(prompt, str) or not prompt.strip():
        raise WorkerError('prompt 为空，worker 不接空活')

    co = (cfg or {}).get('coordinator') or {}
    model = layer.get('model') or co.get('model') or ''
    if not model:
        raise WorkerError('层 %s 没有可用模型（layers.yaml 里 model 为空且 coordinator 也没配）' % key)

    system = layer.get('system') or WORKER_SYSTEM.get(key)
    if key == 'writing':
        _ban = cliche_ban_block()
        if _ban:
            system = ((system or '') + '\n' + _ban).strip()
    if key in SPATIAL_LAYERS:
        memory = memory_bundle(cfg)
        if memory:
            system = (system or '') + '\n\n' + memory
        else:
            # 账本缺失时退回旧的三块拼接（地图 / 角色状态 / 账本摘要）
            spatial = spatial_constraints(cfg)
            if spatial:
                system = (system or '') + (SPATIAL_TEMPLATE % spatial)
            state = character_state_text(cfg)
            if state:
                system = (system or '') + (STATE_TEMPLATE % state)
    messages = []
    if system:
        messages.append({'role': 'system', 'content': system})
    messages.append({'role': 'user', 'content': prompt.strip()})

    sub = {'model': model, 'temperature': layer.get('temperature', co.get('temperature', 0.7))}
    if layer.get('max_tokens'):
        sub['max_tokens'] = int(layer['max_tokens'])

    # 目标字数（layers.yaml 的 target_words；不配就不强制）
    target_words = layer.get('target_words')
    if target_words and str(target_words).isdigit():
        target_words = int(target_words)
        system = (system or '') + (
            '\n\n【字数要求】本章正文不少于 %d 字（中文字符）。'
            '写完先数字数：不够就继续写，补环境、动作、心理、对话，'
            '用具体场面补够，不要用概述、总结或"时间流逝"带过。' % target_words)

    # 思考开关（layers.yaml 每层显式配，别让它默认漂移）
    #   true  -> 不传参数，用模型默认（思考型模型默认会思考）
    #   false -> thinking: disabled
    #   auto / 缺省 -> 不干预
    thinking = layer.get('thinking')
    if thinking is False:
        sub['extra_body'] = {'thinking': {'type': 'disabled'}}
        think_state = 'off'
    elif thinking is True:
        think_state = 'on'
    else:
        think_state = 'auto'

    _log_prompt(key, model, system, prompt, sub)
    resp = chat(sub, messages)          # 统一走网关，返回里带 _billing
    raw = _extract_content(resp)
    text = sanitize_worker_text(raw)
    finish = ((resp.get('choices') or [{}])[0]).get('finish_reason')
    usage = resp.get('usage') or {}
    billing0 = resp.get('_billing') or {}
    empty_warning = None
    if not text:
        if finish == 'length':
            empty_warning = ('思考吃光预算：completion_tokens=%s，content 为空'
                             '（prompt=%s），建议加大 max_tokens 或把 thinking 关掉'
                             % (billing0.get('completion_tokens') or usage.get('completion_tokens'),
                                billing0.get('prompt_tokens') or usage.get('prompt_tokens')))
            _log_worker(empty_warning + ' [%s / %s / thinking=%s]' % (key, model, think_state))
        raise WorkerError('worker 返回空内容（%s / %s%s）'
                          % (key, model, '，' + empty_warning if empty_warning else ''))

    billing = resp.get('_billing') or {}
    meta = {'role': key,
            'layer': layer.get('label') or key,
            'model': model,
            'gateway_model': billing.get('model'),
            'upstream_model': billing.get('upstream_model'),
            'temperature': sub.get('temperature'),
            'max_tokens': sub.get('max_tokens'),
            'prompt_tokens': int(billing.get('prompt_tokens') or 0),
            'completion_tokens': int(billing.get('completion_tokens') or 0),
            'total_tokens': int(billing.get('total_tokens') or 0),
            'quota': float(billing.get('quota') or 0),
            'total_cny': float(billing.get('total_cny') or 0),
            'chars': len(text),
            'thinking': think_state,
            'finish_reason': finish}
    if finish == 'length':
        meta['truncated'] = True
        _log_worker('输出被 max_tokens 截断：%s/%s completion=%s（正文 %d 字）'
                    % (key, model, meta['completion_tokens'], len(text)))
    _WORKER_CALLS.append(dict(meta))
    return text, meta


def tool_call_worker(role, prompt, cfg):
    """给 agent 循环用的稳定入口：永不抛异常；层被关掉时返回 [skipped]。"""
    key = resolve_role(role) or role
    try:
        text, meta = chat_worker(role, prompt, cfg)
    except WorkerDisabled as e:
        _WORKER_CALLS.append({'role': key, 'skipped': True, 'reason': str(e),
                              'model': None, 'prompt_tokens': 0, 'completion_tokens': 0,
                              'total_tokens': 0, 'quota': 0.0, 'total_cny': 0.0})
        return '[skipped] ' + str(e)
    except WorkerError as e:
        return '[worker 错误] ' + str(e)
    except Exception as e:  # 兜底，别让 agent 循环整条挂掉
        return '[worker 错误] %s: %s' % (type(e).__name__, e)
    return text


TOOLS = [
    {'type': 'function', 'function': {
        'name': 'list_files', 'description': '列出目录下的文件（可给绝对路径，如 D:\\资料；空为项目根）',
        'parameters': {'type': 'object', 'properties': {
            'sub': {'type': 'string', 'description': '目录路径，绝对或相对项目根，空为项目根'}}}}},
    {'type': 'function', 'function': {
        'name': 'read_file', 'description': '读取文件内容（可给绝对路径；超过 20000 字会截断）',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': '文件路径，绝对或相对项目根'}}, 'required': ['path']}}},
    {'type': 'function', 'function': {
        'name': 'write_file', 'description': '写文件（可给绝对路径；覆盖前自动留 .bak 备份）',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': '目标路径，绝对或相对项目根'},
            'content': {'type': 'string'}},
            'required': ['path', 'content']}}},
    {'type': 'function', 'function': {
        'name': 'subagent', 'description': '派一个带工具的独立子任务（自己的对话，跑完只回结论）。适合"查资料/审一段/写一小段"这种能单干的活',
        'parameters': {'type': 'object', 'properties': {
            'task': {'type': 'string', 'description': '要它做什么，写清目标和边界'},
            'role': {'type': 'string', 'description': 'research / thinking / writing / quality，默认 research'}},
            'required': ['task']}}},
    {'type': 'function', 'function': {
        'name': 'subagent_parallel', 'description': '并行跑 2-4 个子任务（客户开关打开才可用）。适合互不依赖的活，比如一边查资料一边审稿',
        'parameters': {'type': 'object', 'properties': {
            'tasks': {'type': 'string', 'description': 'JSON 数组：[{"role":"research","task":"…"},{"role":"quality","task":"…"}]'}},
            'required': ['tasks']}}},
    {'type': 'function', 'function': {
        'name': 'ask_user', 'description': '问客户一个问题并等回答（可给 2-6 个选项让客户点）。拿不准方向、要删改文件前先用它',
        'parameters': {'type': 'object', 'properties': {
            'question': {'type': 'string', 'description': '问题，一句话'},
            'options': {'type': 'string', 'description': '选项，用 | 分隔，可空'}},
            'required': ['question']}}},
    {'type': 'function', 'function': {
        'name': 'job_start', 'description': '起一个后台任务（长命令、构建、批处理）。立即返回 job id，不会像 run_command 那样 120 秒被掐',
        'parameters': {'type': 'object', 'properties': {
            'cmd': {'type': 'string', 'description': '要跑的命令（cmd 语法）'},
            'cwd': {'type': 'string', 'description': '工作目录，可给绝对路径，默认数据根'},
            'name': {'type': 'string', 'description': '给任务起个好认的名字'}},
            'required': ['cmd']}}},
    {'type': 'function', 'function': {
        'name': 'job_output', 'description': '看后台任务的输出尾巴和状态（运行中/已结束）',
        'parameters': {'type': 'object', 'properties': {
            'jid': {'type': 'string', 'description': 'job id，如 j20261110-183000-1'},
            'tail': {'type': 'integer', 'description': '要看多少字，默认 4000'}},
            'required': ['jid']}}},
    {'type': 'function', 'function': {
        'name': 'job_list', 'description': '列出所有后台任务及其状态',
        'parameters': {'type': 'object', 'properties': {}}}},
    {'type': 'function', 'function': {
        'name': 'job_kill', 'description': '停掉一个后台任务（连子进程）',
        'parameters': {'type': 'object', 'properties': {
            'jid': {'type': 'string'}}, 'required': ['jid']}}},
    {'type': 'function', 'function': {
        'name': 'edit', 'description': '改文件里的某一段（片段替换，不整文件重写）。原文必须逐字匹配；命中多处会要求写长一点或传 replace_all',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': '文件路径，绝对或相对数据根'},
            'old_string': {'type': 'string', 'description': '要被替换的原文（逐字，含缩进）'},
            'new_string': {'type': 'string', 'description': '替换成什么'},
            'replace_all': {'type': 'boolean', 'description': '命中多处时是否全换，默认 false'}},
            'required': ['path', 'old_string', 'new_string']}}},
    {'type': 'function', 'function': {
        'name': 'grep', 'description': '按正则搜文件内容，返回 文件:行:内容（中文安全，跨盘可用）',
        'parameters': {'type': 'object', 'properties': {
            'pattern': {'type': 'string', 'description': '正则，如 伏笔|承诺'},
            'path': {'type': 'string', 'description': '目录或文件，默认数据根'},
            'include': {'type': 'string', 'description': '只搜这些后缀，逗号分隔，如 .md,.py'}},
            'required': ['pattern']}}},
    {'type': 'function', 'function': {
        'name': 'glob', 'description': '按通配符找文件（* ** ?），返回绝对路径列表',
        'parameters': {'type': 'object', 'properties': {
            'pattern': {'type': 'string', 'description': '如 **/章节/*.md'},
            'path': {'type': 'string', 'description': '从哪个目录开始找，默认数据根'}},
            'required': ['pattern']}}},
    {'type': 'function', 'function': {
        'name': 'run_qc', 'description': '对一章跑 L1/L2 质检并返回报告',
        'parameters': {'type': 'object', 'properties': {
            'chapter': {'type': 'string'}}, 'required': ['chapter']}}},
    {'type': 'function', 'function': {
        'name': 'run_command',
        'description': '在本机执行一条命令（统计、改名、跑脚本、装依赖、看系统信息都行）。返回退出码和输出，最多 8000 字，超时 120 秒',
        'parameters': {'type': 'object', 'properties': {
            'cmd': {'type': 'string', 'description': '要执行的命令，按当前系统的 shell 语法（Windows 用 cmd）'},
            'cwd': {'type': 'string', 'description': '工作目录，可给绝对路径，空为项目根'}},
            'required': ['cmd']}}},
    {'type': 'function', 'function': {
        'name': 'skill',
        'description': '取出一份写作技能的全文（世界观策划、大纲、写作核心、质检等）。先看 system 里的技能清单，再按名字取',
        'parameters': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'description': '技能名，如 novel-outliner'}},
            'required': ['name']}}},
    {'type': 'function', 'function': {
        'name': 'web_search',
        'description': '联网搜索（查资料、核事实、找参考）。返回标题 / 链接 / 摘要，最多 8 条。需要这台机器能上网',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'description': '搜索词'},
            'limit': {'type': 'integer', 'description': '要几条，默认 5，最多 8'}},
            'required': ['query']}}},
    {'type': 'function', 'function': {
        'name': 'read_web_page',
        'description': '打开一个网址，取回正文（去标签，最多 4000 字）。配合 web_search 用：先搜、再读感兴趣的链接',
        'parameters': {'type': 'object', 'properties': {
            'url': {'type': 'string', 'description': 'http/https 地址'},
            'chars': {'type': 'integer', 'description': '最多取多少字，默认 4000'}},
            'required': ['url']}}},
    {'type': 'function', 'function': {
        'name': 'call_worker', 'description': '派活给指定层的研究/思维/写作/质检模型',
        'parameters': {'type': 'object', 'properties': {
            'role': {'type': 'string', 'enum': ['research', 'thinking', 'writing', 'quality']},
            'prompt': {'type': 'string'}}, 'required': ['role', 'prompt']}}},
]

SYSTEM = '''你是小说创作软件的总指挥。

职责：
1. 理解用户意图，决定下一步做什么
2. 需要信息时调工具（list_files / read_file）
3. 需要分析或写作时派给 worker（call_worker）
4. 需要质检时调 run_qc
5. 产出落盘用 write_file
6. 需要在本地跑命令（统计字数、批量改名、转换格式）就调 run_command
7. 遇到「怎么策划世界观 / 怎么写大纲 / 怎么写好一章 / 怎么质检」这类方法论问题，
   先用 skill 工具把对应技能取出来照着做，不要自己编一套
8. 这台机器是 Windows：run_command 用 cmd 语法（dir / type / findstr / copy / where），
   不要用 ls / cat / grep 这些 Unix 命令
9. 你有整台机器的读写权限：D:\\ 下的绝对路径可以直接 list_files / read_file / write_file，
   run_command 的 cwd 也能给任意目录。不确定路径先用 run_command 跑 dir 查一下，别猜
10. 中文相关命令用 PowerShell（Select-String / Get-Content / Set-Content）：
   cmd 的 findstr、type 只认 ANSI，UTF-8 中文会匹配不到或显示乱码
11. 改代码用 edit（片段替换），别用 write_file 整文件重写：先用 grep 定位行、再用 edit 改那一段；
   找文件用 glob。write_file 只用于新建文件或确实全量重写
12. 超过 1 分钟的任务（构建、批量质检、装依赖、长脚本）一律用 job_start 起后台，再用 job_output 看进度；
   不要用 run_command 硬等（120 秒会被掐）。job_list 看全部，job_kill 停
13. 方向不明、要覆盖/删除文件、要在几种写法里选一种时，先用 ask_user 问客户（能给选项就给），
   别自己猜着往下做
14. 能单干的活派给 subagent（查资料 / 审一段 / 写一小段），别把它塞进主对话；互不依赖的活可并行
   （subagent_parallel，客户在设置里开了并行才可用；没开就用单个 subagent 顺序来）

规则：
- 你只读摘要和状态，不读整章正文（正文太长会爆上下文）
- 派给 worker 时，prompt 要写清楚任务和约束
- 每完成一步，简短说明你做了什么
- 用户没让你改的东西，不要改
- 不确定就问用户，不要猜

当前项目目录：D:\\NovelApp
'''

# 联网搜索那一条不再写死在 SYSTEM 里：默认关闭时连提示都不给，
# 免得模型一直去调一个只会返回「没开」的工具。由 core/server.py 的 _agent_loop
# 在拼 system 时按 search_enabled() 追加（关闭 = 不追加）。
SYSTEM_SEARCH_RULE = (
    '\n联网搜索（客户已在「设置 → 通用 → 联网搜索」里打开）：\n'
    '- 需要查资料、核事实就调 web_search 搜，想细看再 read_web_page 读那一页\n'
    '- 搜索源是 Bing 的 RSS，只允许个人非商业用途，不要拿它对整站批量抓取'
)


def dispatch_tool(name, args, cfg):
    """统一分发；单个工具炸了不拖垮整个 agent 循环。"""
    if name == 'list_files':
        return tool_list_files(args.get('sub', ''))
    if name == 'read_file':
        return tool_read_file(args.get('path', ''))
    if name == 'write_file':
        _p = args.get('path', '')
        _c = args.get('content', '')
        _out = tool_write_file(_p, _c)
        try:
            _maybe_commit_chapter(_p, _c)
        except Exception:
            pass
        return _out
    if name == 'subagent':
        return tool_subagent(args.get('task', ''), args.get('role', 'research'), cfg)
    if name == 'subagent_parallel':
        return tool_subagent_parallel(args.get('tasks', ''), cfg)
    if name == 'ask_user':
        return tool_ask_user(args.get('question', ''), args.get('options', ''))
    if name == 'job_start':
        return tool_job_start(args.get('cmd', ''), args.get('cwd', ''), args.get('name', ''))
    if name == 'job_output':
        return tool_job_output(args.get('jid', ''), args.get('tail', 4000))
    if name == 'job_list':
        return tool_job_list()
    if name == 'job_kill':
        return tool_job_kill(args.get('jid', ''))
    if name == 'edit':
        return tool_edit(args.get('path', ''), args.get('old_string', ''),
                         args.get('new_string', ''), bool(args.get('replace_all')))
    if name == 'grep':
        return tool_grep(args.get('pattern', ''), args.get('path', ''), args.get('include', ''))
    if name == 'glob':
        return tool_glob(args.get('pattern', ''), args.get('path', ''))
    if name == 'run_qc':
        return tool_run_qc(args.get('chapter', ''))
    if name == 'run_command':
        return tool_run_command(args.get('cmd', ''), args.get('cwd', ''))
    if name == 'skill':
        return load_skill(args.get('name', ''))
    if name == 'web_search':
        return tool_web_search(args.get('query', ''), args.get('limit', 5))
    if name == 'read_web_page':
        return tool_read_web_page(args.get('url', ''), args.get('chars', 4000))
    if name == 'call_worker':
        return tool_call_worker(args.get('role', ''), args.get('prompt', ''), cfg)
    return f'[未知工具] {name}'


def run(user_input, cfg):
    messages = [{'role': 'system', 'content': SYSTEM},
                {'role': 'user', 'content': user_input}]
    max_steps = cfg.get('max_steps', 20)

    for step in range(1, max_steps + 1):
        resp = chat(cfg['coordinator'] if 'coordinator' in cfg else cfg, messages, TOOLS)
        msg = resp['choices'][0]['message']
        messages.append(msg)

        calls = msg.get('tool_calls') or []
        if not calls:
            print('\n[总指挥] ' + (msg.get('content') or '').strip())
            return msg.get('content')

        for tc in calls:
            name = tc['function']['name']
            try:
                args = json.loads(tc['function']['arguments'] or '{}')
            except Exception:
                args = {}
            print(f'  [{step}] {name}({", ".join(f"{k}={str(v)[:30]}" for k, v in args.items())})')

            try:
                out = dispatch_tool(name, args, cfg)
            except Exception as e:
                out = f'[工具异常] {name}: {type(e).__name__}: {e}'

            out = str(out)
            print(f'      -> {out[:120].replace(chr(10), " ")}')
            messages.append({'role': 'tool', 'tool_call_id': tc['id'], 'content': out})

    print('[达到最大步数]')
    return None


if __name__ == '__main__':
    if '--run-script' in sys.argv:
        exec_script(sys.argv)
    cfg = load_cfg()
    task = ' '.join(sys.argv[1:]) or '列出当前项目里有哪些文件'
    print(f'任务: {task}\n')
    run(task, cfg)