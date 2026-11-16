# -*- coding: utf-8 -*-
"""API 自测：打真实的 8770 服务，覆盖新老端点 + 路径穿越 + 幂等。"""
import coordinator as CO  # noqa: E402
import json, shutil, os, sys
from urllib import request
from urllib.error import HTTPError

BASE = os.environ.get('NOVELAPP_TEST_BASE', 'http://127.0.0.1:8770')
ROOT = r'D:\NovelApp'
PROJ = '_自测项目'
fails = []


def call(method, path, body=None, raw=False):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as r:
            payload = r.read()
            code = r.status
    except HTTPError as e:
        payload = e.read()
        code = e.code
    if raw:
        return code, payload.decode('utf-8', 'replace')
    try:
        return code, json.loads(payload.decode('utf-8'))
    except Exception:
        return code, {'_raw': payload.decode('utf-8', 'replace')[:200]}


def check(label, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + label + ('' if cond else ' | ' + str(detail)[:300]))
    if not cond:
        fails.append(label)


root_proj = os.path.join(CO.projects_root(), PROJ)
if os.path.isdir(root_proj):
    shutil.rmtree(root_proj)

# ---------- 旧端点回归 ----------
c, j = call('GET', '/api/tree')
check('R1 /api/tree 200 + tree 字段', c == 200 and isinstance(j.get('tree'), list) and j.get('root'))
check('R2 树里能看到已有项目 <书名>', any(n['name'] == '<书名>' for n in j['tree']))

c, j = call('GET', '/api/file?path=' + request.quote('projects/<书名>/项目信息.md'))
check('R3 /api/file 读已有文件', c == 200 and '<书名>' in j.get('content', ''))

c, j = call('GET', '/api/config')
check('R4 /api/config 返回 coordinator 模型', c == 200 and j.get('coordinator', {}).get('model'))

c, j = call('GET', '/')
check('R5 / 返回 HTML', c == 200 and '<html' in j.get('_raw', '').lower() if '_raw' in j else c == 200)

# ---------- POST /api/project ----------
c, j = call('POST', '/api/project', {'name': PROJ, 'genre': '玄幻', 'author': '自测'})
check('N1 新建项目 ok', c == 200 and j.get('ok') is True and j.get('path') == 'projects/' + PROJ, j)

for sub in ('章节', '设定库', '大纲', 'reports'):
    check('N2 目录 %s 已建' % sub, os.path.isdir(os.path.join(root_proj, sub)))
for f in ('项目信息.md',):
    check('N3 文件 %s 已建' % f, os.path.isfile(os.path.join(root_proj, f)))
for f in ('力量体系.md', '势力.md', '角色.md', '地点.md'):
    check('N4 设定库 %s' % f, os.path.isfile(os.path.join(root_proj, '设定库', f)))
for f in ('全书大纲.md', '分卷大纲.md'):
    check('N5 大纲 %s' % f, os.path.isfile(os.path.join(root_proj, '大纲', f)))

c, j = call('POST', '/api/project', {'name': PROJ, 'genre': '玄幻'})
check('N6 重名项目被拒 exists', c == 409 and j.get('ok') is False and j.get('error') == 'exists', j)

c, j = call('POST', '/api/project', {'name': 'a/../../etc'})
check('N7 项目名带 .. 被拒', c == 400 and j.get('ok') is False, j)

c, j = call('POST', '/api/project', {'name': 'bad:name*'})
check('N8 项目名非法字符被拒', c == 400 and j.get('ok') is False, j)

c, j = call('POST', '/api/project', {'name': ''})
check('N9 空项目名被拒', c == 400 and j.get('ok') is False, j)

c, j = call('GET', '/api/tree')
check('N10 新项目出现在树里', any(n['name'] == PROJ for n in j['tree']))

# ---------- POST /api/file/new ----------
chap = 'projects/%s/章节/001-第一章-自测.md' % PROJ
c, j = call('POST', '/api/file/new', {'path': chap, 'content': '# 第一章\n\n第一段。\n'})
check('F1 新建文件 ok', c == 200 and j.get('ok') is True and j.get('chars', 0) > 0, j)
check('F2 文件真落盘', os.path.isfile(os.path.join(ROOT, chap.replace('/', os.sep))))

c, j = call('POST', '/api/file/new', {'path': chap})
check('F3 同名文件 exists', c == 200 and j.get('ok') is False and j.get('error') == 'exists', j)

# ---------- POST /api/save ----------
body = '# 第一章\n\n第一段。\n第二段，改过了。\n'
c, j = call('POST', '/api/save', {'path': chap, 'content': body})
check('S1 保存 ok + bytes', c == 200 and j.get('ok') is True and j.get('bytes') == len(body.encode('utf-8')), j)
with open(os.path.join(ROOT, chap.replace('/', os.sep)), encoding='utf-8') as f:
    check('S2 落盘内容一致', f.read() == body)

long_body = body + ('第三段，需要超过两百字才会触发缩水保护。' * 30)
call('POST', '/api/save', {'path': chap, 'content': long_body, 'force': True})
c, j = call('POST', '/api/save', {'path': chap, 'content': 'x'})
check('S3 缩水保护拦截', c == 409 and j.get('ok') is False and j.get('error') == 'content_shrunk', j)

c, j = call('POST', '/api/save', {'path': chap, 'content': 'x', 'force': True})
check('S4 force 可覆盖', c == 200 and j.get('ok') is True, j)
call('POST', '/api/save', {'path': chap, 'content': body, 'force': True})

c, j = call('POST', '/api/save', {'path': chap})
check('S5 content 非字符串被拒', c == 400 and j.get('ok') is False, j)

# ---------- 路径穿越（全部必须 400） ----------
bad = [
    '../core/server.py',
    'projects/../../core/server.py',
    'core/server.py',
    'C:/Windows/win.ini',
    '\\\\server\\share\\x.md',
    'projects/<书名>/../../../x.md',
    'projects/x\x00.md',
    '/etc/passwd',
]
for b in bad:
    c, j = call('POST', '/api/save', {'path': b, 'content': 'pwn', 'force': True})
    check('T 穿越被拒 %r' % b, c == 400 and 'error' in j, (c, j))
for b in bad[:4]:
    c, j = call('GET', '/api/file?path=' + request.quote(b))
    check('T 读穿越被拒 %r' % b, c == 400, (c, j))
    c, j = call('GET', '/api/stats?path=' + request.quote(b))
    check('T 统计穿越被拒 %r' % b, c == 400, (c, j))
check('T 越界文件未生成', not os.path.exists(os.path.join(ROOT, 'x.md')))

# ---------- GET /api/stats ----------
c, j = call('GET', '/api/stats?path=' + request.quote(chap))
check('ST1 文件统计字段齐全', c == 200 and all(k in j for k in ('chars_cn', 'chars_all', 'paragraphs', 'lines')), j)
check('ST2 统计数值合理', j['chars_cn'] > 0 and j['chars_all'] >= j['chars_cn'] and j['lines'] >= 1, j)

c, j = call('GET', '/api/stats?path=' + request.quote('projects/' + PROJ))
check('ST3 目录统计 files>=1', c == 200 and j.get('files', 0) >= 1, j)

c, j = call('GET', '/api/stats')
check('ST4 无 path 统计整个 projects', c == 200 and j.get('files', 0) >= 2, j)

c, j = call('GET', '/api/stats?path=' + request.quote('projects/<书名>/章节/001-第一章-柴没砍完.md'))
check('ST5 真实章节统计', c == 200 and j['chars_cn'] > 1000, j)

# ---------- /api/file 截断与 full=1 ----------
big = 'projects/%s/章节/002-大文件.md' % PROJ
bigtext = '汉' * 25000
call('POST', '/api/file/new', {'path': big, 'content': bigtext})
c, j = call('GET', '/api/file?path=' + request.quote(big))
check('L1 默认全量不截断', c == 200 and j.get('truncated') is False and len(j['content']) == 25000,
      {k: j.get(k) for k in ('truncated', 'chars', 'total_chars')})
check('L2 带 total_chars', c == 200 and j.get('total_chars') == 25000, j.get('total_chars'))
c, j = call('GET', '/api/file?path=' + request.quote(big) + '&full=1')
check('L3 full=1 仍兼容', c == 200 and len(j['content']) == 25000, j.get('truncated'))
c, j = call('GET', '/api/file?path=' + request.quote(big) + '&offset=20000&limit=5000')
check('L4 offset/limit 分块', c == 200 and len(j['content']) == 5000 and j.get('truncated') is True,
      {k: j.get(k) for k in ('offset', 'truncated')})

# 保存上限：明确 413，不静默截断，原文件不变
huge = '汉' * (5_000_001)
c, j = call('POST', '/api/save', {'path': big, 'content': huge, 'force': True})
check('L5 超限保存 413 明示', c == 413 and j.get('ok') is False and j.get('error') == 'too_large', {k: j.get(k) for k in ('error', 'chars', 'max_chars')})
with open(os.path.join(ROOT, big.replace('/', os.sep)), encoding='utf-8') as f:
    check('L6 超限后原文件未被改', len(f.read()) == 25000)

# ---------- 幂等：连跑两遍同样请求 ----------
c1, j1 = call('POST', '/api/save', {'path': chap, 'content': body, 'force': True})
c2, j2 = call('POST', '/api/save', {'path': chap, 'content': body, 'force': True})
check('I1 重复保存幂等', c1 == c2 == 200 and j1.get('bytes') == j2.get('bytes'), (j1, j2))

# ---------- GET /api/qc ----------
rc = 'projects/%s/章节/003-质检样本.md' % PROJ
with open(os.path.join(ROOT, 'samples', 'ch001_bad.md'), encoding='utf-8') as f:
    badtext = f.read()
call('POST', '/api/file/new', {'path': rc, 'content': badtext})
c, j = call('GET', '/api/qc?path=' + request.quote(rc))
check('Q1 /api/qc 200 + ok', c == 200 and j.get('ok') is True, {k: j.get(k) for k in ('ok', 'error')})
check('Q2 issues 是列表且非空', isinstance(j.get('issues'), list) and len(j['issues']) > 0, len(j.get('issues') or []))
check('Q3 每条 issue 五字段齐全',
      all(all(k in i for k in ('rule', 'severity', 'line', 'message', 'snippet')) for i in j['issues']),
      j['issues'][:1])
check('Q4 severity 取值合法',
      all(i['severity'] in ('error', 'warn', 'info') for i in j['issues']))
check('Q5 stats 含 file/l3l4/l1l2',
      all(k in j.get('stats', {}) for k in ('file', 'l3l4', 'l1l2')), list((j.get('stats') or {}).keys()))
check('Q6 检出 L3 路线距离错误',
      any(i['rule'].startswith('L3') for i in j['issues']),
      [i['rule'] for i in j['issues']][:6])
check('Q7 L1L2 走 JSON 而非文本', j['stats']['l1l2'].get('_from') == 'json', j['stats']['l1l2'])
rep_dir = os.path.join(CO.projects_root(), PROJ, 'reports')
_leaked = [x for x in (os.listdir(rep_dir) if os.path.isdir(rep_dir) else [])
            if x.endswith('.json') and x != '.qc-cache.json']
check('Q15 --json 指到临时目录，不写 projects/reports（只允许 .qc-cache.json）',
      not _leaked, _leaked)
check('Q8 summary 计数自洽',
      j['summary']['total'] == len(j['issues']) and
      j['summary']['error'] + j['summary']['warn'] + j['summary']['info'] == len(j['issues']), j.get('summary'))

c, j = call('GET', '/api/qc?path=' + request.quote('projects/<书名>/章节/001-第一章-柴没砍完.md'))
check('Q9 真实章节可跑', c == 200 and j.get('ok') is True and 'issues' in j, j.get('error'))
check('Q10 真实章节未报 error 级', j.get('summary', {}).get('error', 1) == 0, j.get('summary'))

c, j = call('GET', '/api/qc?path=' + request.quote('../core/server.py'))
check('Q11 穿越被拒 400', c == 400 and j.get('ok') is False and j.get('issues') == [], j)
c, j = call('GET', '/api/qc?path=' + request.quote('projects/不存在的项目/x.md'))
check('Q12 不存在 404 且不炸', c == 404 and j.get('ok') is False and 'error' in j, j)
c, j = call('GET', '/api/qc')
check('Q13 缺 path 400', c == 400 and j.get('ok') is False, j)
c, j = call('GET', '/api/qc?path=' + request.quote('projects/' + PROJ + '/项目信息.md') + '&x=1')
check('Q14 非章节 md 也能跑不 500', c == 200 and isinstance(j.get('issues'), list), c)

# ---------- 配置引导 /api/setup/* ----------
import re as _re
cfg_file = os.path.join(ROOT, 'config', 'coordinator.json')
raw_orig = open(cfg_file, encoding='utf-8').read()
cfg_orig = json.loads(raw_orig)
co_orig = cfg_orig.get('coordinator', {})
orig_ep = co_orig.get('endpoint')
orig_key = co_orig.get('api_key')
orig_model = co_orig.get('model')

# 出厂配置里的 api_key 已清空（安全要求），测试连网关时要显式给令牌：
#   NOVELAPP_TEST_KEY=sk-…  +  endpoint 走网关 base，避免依赖厂商原始 key
_gw = call('GET', '/api/gateway/status')
_gw_base = (_gw[1].get('base') if _gw[0] == 200 else '') or ''
_test_key = os.environ.get('NOVELAPP_TEST_KEY') or os.environ.get('NOVELAPP_DOWNSTREAM_KEY') or ''
if _gw_base and _test_key:
    orig_ep = _gw_base.rstrip('/')
    orig_key = _test_key
_has_key = bool(orig_key)

try:
    c, j = call('GET', '/api/setup/status')
    check('S1 status 200 + 字段齐全',
          c == 200 and all(k in j for k in ('configured', 'current', 'providers', 'local_ollama')), j)
    ids = [p['id'] for p in j['providers']]
    check('S2 providers 三个预置', ids == ['deepseek', 'moonshot', 'ollama'], ids)
    check('S3 providers 字段齐全',
          all(all(k in p for k in ('id', 'name', 'endpoint', 'model', 'note')) for p in j['providers']) and
          all('key_url' in p for p in j['providers'] if p['id'] != 'ollama'), j['providers'])
    check('S4 ollama 预置带 api_key', j['providers'][2].get('api_key') == 'ollama', j['providers'][2])
    check('S5 local_ollama 结构正确',
          isinstance(j['local_ollama'].get('detected'), bool) and isinstance(j['local_ollama'].get('models'), list),
          j['local_ollama'])
    check('S6 current.api_key 已脱敏',
          '*' in (j['current']['api_key'] or '') or j['current']['api_key'] == '', j['current'])
    check('S7 脱敏只漏前6后4',
          len(orig_key) <= 10 or (j['current']['api_key'].startswith(orig_key[:6]) and
                                  j['current']['api_key'].endswith(orig_key[-4:]) and
                                  orig_key not in j['current']['api_key']), j['current']['api_key'])
    if _has_key:
        check('S8 初始 configured=true（配置里有真 key）', j['configured'] is True, j['configured'])
    else:
        print('SKIP 出厂配置无 key：S8')

    c, j = call('GET', '/api/config')
    if _has_key:
        check('S9 /api/config 里 api_key 也脱敏', orig_key not in json.dumps(j, ensure_ascii=False), '')
    else:
        print('SKIP 无 key：S9')

    # --- test 分支 ---
    c, j = call('POST', '/api/setup/test', {'endpoint': 'http://127.0.0.1:9/v1', 'api_key': 'sk-TESTONLY-000000', 'model': 'x'})
    check('T1 连不上 -> connect_failed', c == 200 and j.get('ok') is False and j.get('error') == 'connect_failed', j)
    _port = BASE.rsplit(':', 1)[-1].split('/')[0]
    c, j = call('POST', '/api/setup/test', {'endpoint': 'http://127.0.0.1:%s/v1' % _port, 'api_key': 'sk-TESTONLY-000000', 'model': 'x'})
    check('T2 404 -> not_found', c == 200 and j.get('ok') is False and j.get('error') in ('not_found', 'http_404'), j)
    c, j = call('POST', '/api/setup/test', {'endpoint': 'file:///etc/passwd', 'api_key': 'sk-TESTONLY-000000', 'model': 'x'})
    check('T3 非 http endpoint 被拒 400', c == 400 and j.get('ok') is False, j)
    c, j = call('POST', '/api/setup/test', {'endpoint': orig_ep, 'api_key': 'sk-TESTONLY-000000', 'model': orig_model})
    check('T4 假 key -> unauthorized', c == 200 and j.get('ok') is False and j.get('error') in ('unauthorized', 'http_401', 'http_403'), j)
    c, j = call('POST', '/api/setup/test', {'endpoint': orig_ep, 'api_key': orig_key, 'model': 'model-not-exist-zzz'})
    check('T5 假模型 -> model_not_found/not_found', c == 200 and j.get('ok') is False and
          j.get('error') in ('model_not_found', 'not_found', 'bad_request', 'upstream_error', 'http_400'), j)
    c, j = call('POST', '/api/setup/test', {'endpoint': orig_ep, 'api_key': orig_key, 'model': orig_model})
    check('T6 真 key -> ok:true 且有 reply', c == 200 and j.get('ok') is True and isinstance(j.get('reply'), str), j)
    check('T7 任何返回都不含完整 key', orig_key not in json.dumps(j, ensure_ascii=False), '')

    # --- save 分支 ---
    c, j = call('POST', '/api/setup/save', {'endpoint': orig_ep, 'api_key': 'sk-TESTONLY-000000', 'model': orig_model})
    check('V1 占位 key 也能写（但 configured=false）', c == 200 and j.get('ok') is True and j.get('configured') is False, j)
    c, j = call('GET', '/api/setup/status')
    check('V2 占位 key -> configured=false', j.get('configured') is False, j['current'])
    check('V3 备份文件已生成', os.path.exists(cfg_file + '.bak'), cfg_file + '.bak')
    c, j = call('POST', '/api/setup/test', {'endpoint': orig_ep, 'api_key': 'sk-TESTONLY-000000', 'model': orig_model})
    check('V4 占位 key 调不通', j.get('ok') is False, j.get('error'))

    c, j = call('POST', '/api/setup/save', {'endpoint': orig_ep, 'api_key': orig_key, 'model': 'setup-test-model'})
    check('V5 真 key 保存 -> configured=true', c == 200 and j.get('ok') is True and j.get('configured') is True, j)
    c, j = call('GET', '/api/config')
    check('V6 保存后 /api/config 立即生效（不用重启）',
          j.get('coordinator', {}).get('model') == 'setup-test-model', j.get('coordinator'))
    check('V7 workers 四层同步',
          all(w.get('model') == 'setup-test-model' for w in j.get('workers', {}).values()) and len(j.get('workers', {})) == 4,
          j.get('workers'))
    c, j = call('GET', '/api/setup/status')
    check('V8 status.configured 变 true', j.get('configured') is True, j.get('current'))
    c, j = call('POST', '/api/setup/save', {'endpoint': 'ftp://x', 'api_key': orig_key, 'model': orig_model})
    check('V9 非法 endpoint 被拒 400', c == 400 and j.get('ok') is False, j)
finally:
    # 还原：先走 save 让内存配置回到原值，再把文件字节还原
    call('POST', '/api/setup/save', {'endpoint': orig_ep, 'api_key': orig_key, 'model': orig_model})
    with open(cfg_file, 'w', encoding='utf-8', newline='') as f:
        f.write(raw_orig)
    c, j = call('GET', '/api/setup/status')
    check('S10 还原后 configured=true 且模型回原值', j.get('configured') is True and j['current']['model'] == orig_model, j.get('current'))

# ---------- 配置热重载（mtime） ----------
raw_orig2 = open(cfg_file, encoding='utf-8').read()
co2 = json.loads(raw_orig2)['coordinator']
log_cfg = os.path.join(ROOT, 'logs', 'config.log')
try:
    mod = json.loads(raw_orig2)
    mod['coordinator']['model'] = 'hot-reload-model-x'
    open(cfg_file, 'w', encoding='utf-8').write(json.dumps(mod, ensure_ascii=False, indent=2))
    c, j = call('GET', '/api/config')
    check('W1 人工改配置后 /api/config 立即生效',
          j.get('coordinator', {}).get('model') == 'hot-reload-model-x', j.get('coordinator'))
    c, j = call('GET', '/api/setup/status')
    check('W2 status.runtime 已同步且 in_sync',
          j['runtime']['model'] == 'hot-reload-model-x' and j['runtime']['in_sync'] is True, j.get('runtime'))
    check('W3 auto_reload 有计数、无错误',
          j['auto_reload']['reloads'] >= 1 and j['auto_reload']['last_error'] is None, j.get('auto_reload'))

    open(cfg_file, 'w', encoding='utf-8').write('{ "coordinator": { "model": ')
    c, j = call('GET', '/api/config')
    check('W4 配置写坏后不崩且保留旧配置',
          c == 200 and j.get('coordinator', {}).get('model') == 'hot-reload-model-x', j.get('coordinator'))
    c, j = call('GET', '/api/setup/status')
    check('W5 写坏时 last_error 有值且接口正常', c == 200 and bool(j['auto_reload']['last_error']), j.get('auto_reload'))
    txt = open(log_cfg, encoding='utf-8').read() if os.path.exists(log_cfg) else ''
    check('W6 重载失败写进 logs/config.log', '重载失败' in txt, txt[-200:])

    mod['coordinator']['model'] = 'hot-reload-model-y'
    open(cfg_file, 'w', encoding='utf-8').write(json.dumps(mod, ensure_ascii=False, indent=2))
    c, j = call('GET', '/api/config/reload')
    check('W7 /api/config/reload 强制重载',
          c == 200 and j.get('ok') is True and j.get('model_after') == 'hot-reload-model-y', j)

    os.replace(cfg_file, cfg_file + '.hidden')
    try:
        c, j = call('GET', '/api/config')
        check('W8 配置文件被删也不崩', c == 200 and 'coordinator' in j, j.get('error'))
    finally:
        os.replace(cfg_file + '.hidden', cfg_file)
    c, j = call('GET', '/api/config')
    check('W9 文件恢复后配置跟着恢复',
          j.get('coordinator', {}).get('model') == 'hot-reload-model-y', j.get('coordinator'))
finally:
    with open(cfg_file, 'w', encoding='utf-8', newline='') as f:
        f.write(raw_orig2)
    c, j = call('GET', '/api/config')
    check('W10 还原后 /api/config 回原 model',
          j.get('coordinator', {}).get('model') == co2['model'], j.get('coordinator'))

# ---------- new-api 网关 / 账户 ----------
def post_sse(body, timeout=180):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = request.Request(BASE + '/api/chat', data=data,
                          headers={'Content-Type': 'application/json'}, method='POST')
    events, buf = [], ''
    with request.urlopen(req, timeout=timeout) as r:
        while True:
            chunk = r.read(4096)
            if not chunk:
                break
            buf += chunk.decode('utf-8', 'replace')
            while '\n\n' in buf:
                part, buf = buf.split('\n\n', 1)
                part = part.strip()
                if part.startswith('data:'):
                    try:
                        events.append(json.loads(part[5:].strip()))
                    except Exception:
                        pass
    return events


c, gs = call('GET', '/api/gateway/status')
check('A1 /api/gateway/status 可用', c == 200 and 'enabled' in gs, gs)
gw_on = bool(gs.get('enabled'))
if gw_on:
    check('A2 网关定价已加载', (gs.get('quota_per_unit') or 0) > 0 and (gs.get('price') or 0) > 0, gs)
    events = post_sse({'message': '用三个字回答'})
    kinds = [e.get('type') for e in events]
    check('A3 SSE 有 final 事件', 'final' in kinds, kinds)
    fin = [e for e in events if e.get('type') == 'final']
    usage = (fin[-1].get('usage') if fin else None) or {}
    check('A4 final 带 usage 对象', isinstance(usage, dict) and usage.get('total_tokens', 0) > 0, usage)
    check('A5 usage 字段齐全',
          all(k in usage for k in ('prompt_tokens', 'completion_tokens', 'official_cny', 'fee_cny', 'total_cny')), usage)
    check('A6 计费自洽：total = official + fee',
          abs(round(usage.get('official_cny', 0) + usage.get('fee_cny', 0), 5) - usage.get('total_cny', 0)) <= 1e-5, usage)
    check('A7 服务费率 0（按官方价）', abs((usage.get('fee_rate') if usage.get('fee_rate') is not None else 0) - 0.0) < 1e-9, usage.get('fee_rate'))
    check('A8 走的是网关映射名', usage.get('models') == ['default'], usage.get('models'))
else:
    print('SKIP 网关未启用（没有 downstream_key）：A2–A8')

gw_user = os.environ.get('NOVELAPP_TEST_USER', '')
gw_pass = os.environ.get('NOVELAPP_TEST_PASS', '')
if gw_on and gw_user:
    c, j = call('POST', '/api/account/login', {'username': gw_user, 'password': 'wrong-password-zzz'})
    check('B1 错误密码 -> unauthorized', c == 401 and j.get('ok') is False and j.get('error') == 'unauthorized', j)

    c, j = call('POST', '/api/account/login', {'username': gw_user, 'password': gw_pass})
    check('B2 登录成功并返回 session', c == 200 and j.get('ok') is True and j.get('session'), j)
    sid = j.get('session')
    qpu = gs.get('quota_per_unit') or 500000
    price = gs.get('price') or 7.3
    check('B3 登录返回余额换算正确',
          abs((j.get('balance_cny') or 0) - (j.get('quota') or 0) / qpu * price) < 1e-4, j)

    hdr = {'X-Novela-Session': sid}
    url = BASE + '/api/account/balance'
    req = request.Request(url, headers=hdr)
    with request.urlopen(req, timeout=30) as r:
        jb = json.loads(r.read().decode('utf-8'))
    check('B4 带 session 查余额', jb.get('ok') is True and 'quota' in jb and 'used_quota' in jb, jb)

    req = request.Request(BASE + '/api/account/usage?limit=5', headers=hdr)
    with request.urlopen(req, timeout=30) as r:
        ju = json.loads(r.read().decode('utf-8'))
    check('B5 带 session 查明细', ju.get('ok') is True and isinstance(ju.get('usage'), list), ju)
    if ju.get('usage'):
        row = ju['usage'][0]
        check('B6 明细行字段齐全',
              all(k in row for k in ('time', 'model', 'prompt_tokens', 'completion_tokens',
                                     'quota', 'official_cny', 'fee_cny', 'total_cny')), row)
    else:
        print('SKIP 该账号暂无调用记录：B6')

    code, jn = call('GET', '/api/account/balance?session=deadbeef')
    check('B7 伪造 session -> 401 no_session', code == 401 and jn.get('error') == 'no_session', (code, jn))
else:
    print('SKIP 未提供测试账号（NOVELAPP_TEST_USER/PASS）：B1–B7')

# ---------- 客户专属令牌 /api/account/setup ----------
if gw_on and gw_user:
    c, j = call('POST', '/api/account/setup', {'username': gw_user, 'password': 'wrong-zzz'})
    check('C1 setup 密码错 -> 401 unauthorized', c == 401 and j.get('error') == 'unauthorized', j)

    c, j = call('POST', '/api/account/setup', {'username': gw_user, 'password': gw_pass})
    tok = j.get('token') or ''
    check('C2 setup 返回完整令牌', c == 200 and j.get('ok') is True and tok.startswith('sk-') and len(tok) > 20, j)
    check('C3 令牌名按客户区分', j.get('token_name') == 'novelapp-' + gw_user, j.get('token_name'))
    check('C4 返回余额/额度', (j.get('quota') is not None) and (j.get('balance_cny') is not None), j)

    c, j2 = call('GET', '/api/account/token')
    check('C5 GET token 与签发一致', c == 200 and j2.get('token') == tok and j2.get('active') is True, j2)

    # 令牌真能用：直接打网关 /v1/models
    gw_ok = False
    try:
        req = request.Request((gs.get('base') or '').rstrip('/') + '/models',
                              headers={'Authorization': 'Bearer ' + tok})
        with request.urlopen(req, timeout=15) as r:
            gw_ok = (r.status == 200)
    except Exception:
        gw_ok = False
    check('C6 签发令牌可调网关', gw_ok, 'models 200?')

    c, j3 = call('POST', '/api/account/setup', {'username': gw_user, 'password': gw_pass})
    check('C7 重复 setup 复用同一令牌', j3.get('ok') is True and j3.get('token') == tok and j3.get('created') is False, j3)

    # 2026-11-17 R19 移除后：这两条从"注入环境"改为"通道已不存在"的反向证据
    c8, j4 = call('GET', '/api/account/dsh-env')
    check('C8 R19: dsh-env 已移除（404）', c8 == 404, c8)
    c9, j5 = call('POST', '/api/account/dsh/launch', {})
    check('C9 R19: dsh/launch 已移除（404）', c9 == 404, c9)

    c, j5 = call('GET', '/api/gateway/status')
    check('C10 gateway.status 反映客户令牌', j5.get('key_source') == 'user_token' and j5.get('token_ready') is True, j5.get('key_source'))
    check('C11 状态接口不泄露完整令牌', tok not in json.dumps(j5, ensure_ascii=False), '')

    c, j6 = call('POST', '/api/account/logout', {})
    check('C12 logout 清令牌', j6.get('ok') is True and j6.get('token_removed') is True, j6)
    c, j7 = call('GET', '/api/account/token')
    check('C13 logout 后 need_setup', j7.get('ok') is False and j7.get('need_setup') is True, j7)
    c, j8 = call('POST', '/api/account/setup', {'username': gw_user, 'password': gw_pass})
    check('C14 重新 setup 可恢复', j8.get('ok') is True and j8.get('token') == tok, j8)
else:
    print('SKIP 未启用网关或未提供测试账号：C1–C14')

# ---------- 清理 ----------
shutil.rmtree(root_proj, ignore_errors=True)
print('----')
print('清理测试项目:', not os.path.exists(root_proj))
print('FAILED: %d' % len(fails))
for f in fails:
    print('  ' + f)
sys.exit(1 if fails else 0)