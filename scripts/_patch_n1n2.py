#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.0.1 安全补丁 N1/N2（幂等）。

修什么：
  N1  Host 头伪造（DNS rebinding）       -> Host 只认回环 + NOVELAPP_ALLOW_HOSTS
  N2  跨站 Origin / text/plain 写文件     -> 写请求校验 Origin 同源 + 强制 application/json
  N3  /api/chat 无令牌可白嫖模型          -> 没令牌 401
  N4  /api/tree?path=.. 目录穿越           -> safe_rel 校验，越界 400

用法：
  python scripts/_patch_n1n2.py --dry-run   # 只看会改什么
  python scripts/_patch_n1n2.py             # 应用（已应用的条目自动跳过）
重复跑第二遍必须是 no-op。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, 'core', 'server.py')
INDEX = os.path.join(ROOT, 'web', 'index.html')

PATCHES = []


def add(path, name, old, new, marker):
    PATCHES.append({'file': path, 'name': name, 'old': old, 'new': new, 'marker': marker})


# ---------------- P1 模块级常量与辅助 ----------------
P1_OLD = "MAX_BODY = 16 * 1024 * 1024          # POST body 上限\n"
P1_NEW = """MAX_BODY = 16 * 1024 * 1024          # POST body 上限

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
    \"\"\"Host 头 -> 纯主机名（小写、去端口、去 IPv6 方括号）。解析不了返回 ''。\"\"\"
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
    \"\"\"Origin 是否同源：http(s) + 回环主机 + 本服务端口。Origin: null 一律拒。\"\"\"
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
    \"\"\"进程内随机令牌：没有 NOVELAPP_BACKEND_TOKEN 时用它给界面注入 chat 令牌。\"\"\"
    global _SESSION_TOKEN
    if not _SESSION_TOKEN:
        _SESSION_TOKEN = 'nvls-' + os.urandom(16).hex()
    return _SESSION_TOKEN
# ==== SEC-GUARD-END ====
"""
add(SERVER, 'P1 常量与 Host/Origin 辅助函数', P1_OLD, P1_NEW, '==== SEC-GUARD-BEGIN')


# ---------------- P2 H 类的 guard / chat_ok ----------------
P2_OLD = "    def _auth_ok(self):\n"
P2_NEW = """    # ---- v1.0.1 入口防护：Host / Origin / Content-Type ----
    def _guard(self):
        \"\"\"拦在鉴权之前：假 Host、跨站 Origin、非 JSON 写请求一律 403。\"\"\"
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
        \"\"\"对话接口必须带令牌：环境变量优先，否则用进程内随机令牌（由页面注入）。\"\"\"
        got = (self.headers.get('X-Novelapp-Token') or '').strip()
        expect = os.environ.get('NOVELAPP_BACKEND_TOKEN') or _session_token()
        return bool(got) and got == expect

    def _auth_ok(self):
"""
add(SERVER, 'P2 H._guard / H._chat_ok', P2_OLD, P2_NEW, 'def _guard(self):')


# ---------------- P3 do_GET 入口 ----------------
P3_OLD = "    def do_GET(self):\n        if not self._auth_ok():\n"
P3_NEW = "    def do_GET(self):\n        if not self._guard():\n            return\n        if not self._auth_ok():\n"
add(SERVER, 'P3 do_GET 挂 guard', P3_OLD, P3_NEW, 'def do_GET(self):\n        if not self._guard():')


# ---------------- P4 do_POST 入口 ----------------
P4_OLD = "    def do_POST(self):\n        if not self._auth_ok():\n"
P4_NEW = "    def do_POST(self):\n        if not self._guard():\n            return\n        if not self._auth_ok():\n"
add(SERVER, 'P4 do_POST 挂 guard', P4_OLD, P4_NEW, 'def do_POST(self):\n        if not self._guard():')


# ---------------- P5 /api/tree 路径校验 ----------------
P5_OLD = """            elif u.path == '/api/tree':
                self._json({'tree': tree('projects'), 'root': ROOT})
"""
P5_NEW = """            elif u.path == '/api/tree':
                _rel = (q.get('path') or [''])[0].strip()
                if _rel:
                    _norm, _ = safe_rel(_rel)      # .. 穿越 / 绝对路径 -> PathError -> 400
                    self._json({'tree': tree(_norm), 'root': ROOT})
                else:
                    self._json({'tree': tree('projects'), 'root': ROOT})
"""
add(SERVER, 'P5 /api/tree 校验 path', P5_OLD, P5_NEW, "_norm, _ = safe_rel(_rel)")


# ---------------- P6 /api/chat 令牌 ----------------
P6_OLD = """            if u.path == '/api/chat':
                self._chat(data)
                return
"""
P6_NEW = """            if u.path == '/api/chat':
                if not self._chat_ok():
                    self._json({'ok': False, 'error': 'unauthorized'}, 401)
                    return
                self._chat(data)
                return
"""
add(SERVER, 'P6 /api/chat 强制令牌', P6_OLD, P6_NEW, 'if not self._chat_ok():')


# ---------------- P7 页面注入令牌 ----------------
P7_OLD = """        body = open(p, 'rb').read()
        self.send_response(200)
"""
P7_NEW = """        body = open(p, 'rb').read()
        # v1.0.1：给页面注入请求令牌（页面脚本据此带 X-Novelapp-Token 调 /api/chat）
        _tk = (os.environ.get('NOVELAPP_BACKEND_TOKEN') or _session_token()).encode('utf-8')
        body = body.replace(b'__NOVELAPP_TOKEN__', _tk)
        self.send_response(200)
"""
add(SERVER, 'P7 _index 注入请求令牌', P7_OLD, P7_NEW, "body.replace(b'__NOVELAPP_TOKEN__'")


# ---------------- P8 前端 fetch 自动带令牌 ----------------
P8_OLD = """<div class="toasts" id="toasts"></div>

<script>
'use strict';
"""
P8_NEW = """<div class="toasts" id="toasts"></div>

<script>
/* v1.0.1 入口防护：页面持有请求令牌，所有 /api/ 请求自动带上 */
(function(){
  var TK = '__NOVELAPP_TOKEN__';
  window.__NVL_TOKEN__ = TK;
  if (typeof window.fetch !== 'function') return;
  var raw = window.fetch;
  window.fetch = function(input, init){
    try {
      var url = (typeof input === 'string') ? input : ((input && input.url) || '');
      var hit = (typeof input === 'string' && input.indexOf('/api/') === 0)
        || url.indexOf(location.origin + '/api/') === 0;
      if (hit && TK) {
        init = init || {};
        var h = init.headers;
        if (!h) { h = {}; init.headers = h; }
        if (typeof Headers !== 'undefined' && h instanceof Headers) {
          if (!h.has('X-Novelapp-Token')) h.set('X-Novelapp-Token', TK);
        } else if (Array.isArray(h)) {
          var hasArr = h.some(function(p){ return String(p[0]).toLowerCase() === 'x-novelapp-token'; });
          if (!hasArr) h.push(['X-Novelapp-Token', TK]);
        } else {
          var found = false;
          for (var k in h) { if (String(k).toLowerCase() === 'x-novelapp-token') { found = true; break; } }
          if (!found) h['X-Novelapp-Token'] = TK;
        }
      }
    } catch (e) {}
    return raw.call(this, input, init);
  };
})();
</script>

<script>
'use strict';
"""
add(INDEX, 'P8 前端 fetch 自动带令牌', P8_OLD, P8_NEW, "v1.0.1 入口防护：页面持有请求令牌")


def read_text(path):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        raw = f.read()
    crlf = raw.count('\r\n')
    lf = raw.count('\n')
    if crlf and crlf != lf:
        raise SystemExit('换行风格混杂（crlf=%d lf=%d），停止：%s' % (crlf, lf, path))
    return raw.replace('\r\n', '\n'), bool(crlf)


def write_text(path, text, use_crlf):
    if use_crlf:
        text = text.replace('\n', '\r\n')
    tmp = path + '.tmp-patch'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    os.replace(tmp, path)


def main():
    dry = '--dry-run' in sys.argv
    cache = {}
    ok = skip = fail = 0
    for p in PATCHES:
        path = p['file']
        if path not in cache:
            cache[path] = read_text(path)
        text, use_crlf = cache[path]

        print('%-34s %-6s' % (p['name'], os.path.basename(path)), end='')
        if p['marker'] in text:
            print('SKIP（已应用）')
            skip += 1
            continue

        hits = text.count(p['old'])
        if hits != 1:
            print('FAIL（锚点命中 %d 次，需人工看）' % hits)
            fail += 1
            continue

        new_text = text.replace(p['old'], p['new'], 1)
        cache[path] = (new_text, use_crlf)
        print('OK' if not dry else 'WOULD-APPLY')
        ok += 1

    if not dry and ok:
        for path, (text, use_crlf) in cache.items():
            write_text(path, text, use_crlf)

    print()
    print('结果: applied=%d skipped=%d failed=%d%s' % (ok, skip, fail, '（dry-run）' if dry else ''))
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
