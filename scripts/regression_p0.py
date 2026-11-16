# -*- coding: utf-8 -*-
"""P0 回归：副作用断言（不是「接口 200」，而是「磁盘/状态/上游行为对不对」）

用法:
    python scripts/regression_p0.py                 # 自己起 stub 网关 + 临时后端
    python scripts/regression_p0.py --base 18760    # 打到已运行的服务（需 --book 指定的临时书）

覆盖六项：
    1 abort   : 客户端硬关闭 → 1.5 秒内状态 cancel、不落盘、上游提前断
    2 newbook : /api/project 建出的目录结构（4 子目录 + 项目信息）
    3 missing : 有状态没文件的章节 → missing=true
    4 title   : 模型写两个标题 → 落盘只有 1 行标题
    5 draft   : 机检失败 → 存 .draft、没有 .md、没有 commit
    6 paths   : 路径基准（客户数据在 %APPDATA%、程序在 D: 的跨盘场景）
                —— 读/写/统计都必须 200，且落盘内容与独立统计一致，越界仍 400
"""
import http.client, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'core'))

STUB_PORT = 19380
API_PORT = 19381
BOOK = '_regress'

results = []


def record(name, ok, detail):
    results.append((name, ok, detail))
    print(('PASS  ' if ok else 'FAIL  ') + name + '  ' + detail)


def record_skip(name, detail):
    print('SKIP  ' + name + '  ' + detail)


def http_json(url, method='GET', body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def sse_events(raw):
    out = []
    for chunk in raw.split('\n\n'):
        line = chunk.strip()
        if line.startswith('data:'):
            try:
                out.append(json.loads(line[5:].strip()))
            except ValueError:
                pass
    return out


STUB = '''
import json, os, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
PARA = ('雾没散。他从铺子门口退出来，米袋在肩上搭着，一只手扶着袋口。新草鞋踩在湿草上，'
        '鞋底陷下去，泥从鞋帮边挤出来，又拔出来，带起一小撮草屑。走十几步回头，那灯还亮着。')
LONG = '# 第 2 章 雾' + chr(10)*2 + '## 第 2 章' + chr(10)*2 + PARA * 40
SHORT = '雾没散。他退出来。'
PROG = os.path.join(os.environ.get('REGRESS_DIR', os.getcwd()), '_stub_progress.txt')
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n).decode('utf-8', 'replace')
        slow = 'SLOW' in raw
        text = SHORT if 'SHORT' in raw else LONG
        open(PROG, 'w').write('0')
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        sent = 0
        try:
            for i in range(0, len(text), 120):
                piece = text[i:i+120]
                self.wfile.write(('data: ' + json.dumps({'choices': [{'delta': {'content': piece}}]}, ensure_ascii=False) + chr(10)*2).encode())
                self.wfile.flush()
                sent += 1
                open(PROG, 'w').write(str(sent))
                if slow:
                    time.sleep(0.05)
            self.wfile.write(('data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 200, 'completion_tokens': 900, 'total_tokens': 1100}}) + chr(10)*2).encode())
            self.wfile.write((b'data: [DONE]' + (chr(10) * 2).encode()))
            self.wfile.flush()
        except Exception:
            open(PROG, 'w').write(str(sent) + ':aborted')
ThreadingHTTPServer(('127.0.0.1', %d), H).serve_forever()
''' % STUB_PORT


def prepare():
    import server as S
    d = os.path.join(S.PROJECTS, BOOK)
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(os.path.join(S.PROJECTS, '<书名>'), d)
    for f in os.listdir(os.path.join(d, '章节')):
        os.remove(os.path.join(d, '章节', f))
    with open(os.path.join(d, '章节', '001-第1章.md'), 'w', encoding='utf-8') as f:
        f.write('# 第 1 章' + chr(10) + chr(10) + '占位正文。' + chr(10))
    return d


def check_abort(d):
    body = json.dumps({'book': BOOK, 'chapter': '002', 'prompt': 'SLOW 写第二章', 'force': True}).encode()
    req = ('POST /api/write HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nContent-Type: application/json\r\n'
           'Content-Length: %d\r\n\r\n' % (API_PORT, len(body))).encode() + body
    s = socket.create_connection(('127.0.0.1', API_PORT), timeout=10)
    s.sendall(req)
    time.sleep(0.25)
    s.recv(1500)
    s.shutdown(socket.SHUT_RDWR)
    s.close()
    time.sleep(1.5)
    import stages as ST
    st = ST.get_detail(BOOK, '002')
    files = [f for f in os.listdir(os.path.join(d, '章节')) if f.startswith('002-') and f.endswith('.md')]
    prog = open(os.path.join(ROOT, 'build', '_stub_progress.txt')).read()
    ok = (st.get('action') == 'cancel' and st.get('reason') == '客户中断'
          and not files and 'aborted' in prog)
    record('1 abort 立刻停 / 不落盘 / cancel', ok,
           'action=%s reason=%s md=%s upstream=%s' % (st.get('action'), st.get('reason'), files, prog))


def check_newbook(base):
    name = '_regress_proj'
    code, body = http_json(base + '/api/project', 'POST', {'name': name, 'genre': '玄幻'})
    proj = os.path.join(os.path.dirname(PROJECTS_ROOT), 'projects', name)
    dirs = sorted(os.listdir(proj)) if os.path.isdir(proj) else []
    ok = (code == 200 and set(['章节', '设定库', '大纲', 'reports']).issubset(set(dirs))
          and '项目信息.md' in dirs)
    record('2 新建书 4 子目录 + 项目信息', ok, 'http=%s dirs=%s' % (code, dirs))
    # 2b: 0 章的新书必须出现在 /novelapp/projects（前端曾把 chapters=0 的书过滤掉）
    try:
        st, body = http_json('http://127.0.0.1:18760/novelapp/projects', timeout=8)
        books = (json.loads(body) or {}).get('books') or []
        hit = [b for b in books if b.get('name') == name]
        ok2 = bool(hit) and int(hit[0].get('chapters') or 0) == 0
        record('2b 0 章新书出现在项目列表', ok2,
               'books=%s hit=%s' % ([b.get('name') for b in books], hit))
    except Exception as e:
        record_skip('2b 0 章新书出现在项目列表', '18760 不可达: %s' % str(e)[:50])
    shutil.rmtree(proj, ignore_errors=True)


def check_missing():
    code, body = http_json('http://127.0.0.1:%d/novelapp/stages' % API_PORT, 'POST',
                           {'book': BOOK, 'chapter': '007', 'stage': 'blocked',
                            'reason': '机检未过', 'force': True}) if False else (0, '')
    import stages as ST
    ST.set_stage(BOOK, '007', 'blocked', reason='机检未过', force=True)
    miss = ST.missing_map(BOOK)
    ok = miss.get('007') is True and not miss.get('001')
    record('3 幽灵章节 missing=true', ok, 'missing=%s' % json.dumps(miss))


def check_title(d):
    code, raw = http_json('http://127.0.0.1:%d/api/write' % API_PORT, 'POST',
                          {'book': BOOK, 'chapter': '002', 'prompt': 'LONG 写第二章', 'force': True})
    evs = sse_events(raw)
    done = next((e for e in evs if e.get('type') == 'done'), {})
    p = os.path.join(d, '章节', os.path.basename(done.get('path') or ''))
    heads = 0
    if os.path.exists(p):
        heads = sum(1 for l in open(p, encoding='utf-8').read().split('\n') if l.strip().startswith('#'))
    ok = bool(done) and heads == 1
    record('4 标题只出现一次', ok, 'heads=%d warnings=%s' % (heads, done.get('warnings')))


def check_draft(d):
    commits_dir = os.path.join(d, '.story', 'commits')
    before = set(os.listdir(commits_dir)) if os.path.isdir(commits_dir) else set()
    code, raw = http_json('http://127.0.0.1:%d/api/write' % API_PORT, 'POST',
                          {'book': BOOK, 'chapter': '003', 'prompt': 'SHORT 写第三章', 'force': True})
    evs = sse_events(raw)
    err = next((e for e in evs if e.get('type') == 'error'), {})
    draft = err.get('draft') or ''
    p = os.path.join(PROJECTS_ROOT, draft[len('projects/'):].replace('/', os.sep)) if draft else ''
    after = set(os.listdir(commits_dir)) if os.path.isdir(commits_dir) else set()
    new_commits = sorted(after - before)
    files = sorted(f for f in os.listdir(os.path.join(d, '章节')) if f.startswith('003-') and f.endswith('.md'))
    ok = bool(draft) and os.path.exists(p) and not files and not new_commits
    record('5 机检失败存 .draft', ok,
           'draft=%s exists=%s md=%s new_commits=%s' % (draft, os.path.exists(p) if p else False, files, new_commits))


def check_paths(d):
    r"""路径基准回归（v0.7.8 修的 P0）。

    历史 bug：safe_rel 用 ROOT 作基准、stats_path/tree 用 os.path.relpath(full, ROOT)，
    客户数据在 C:\…\AppData 而程序在 D:\NovelApp 时：
      · safe_rel  → 两条路径永远不相等 → /api/file /api/save /api/file/new 全 400
      · relpath   → ValueError: path is on mount 'C:', start on mount 'D:' → /api/stats 500
    断言用副作用：读到的正文对、字数与独立正则统计一致、落盘的字节对、越界仍然 400。
    """
    import re as _re
    base = 'http://127.0.0.1:%d' % API_PORT
    chap = 'projects/%s/章节/001-第1章.md' % BOOK
    q = urllib.parse.quote(chap, safe='')

    code, body = http_json(base + '/api/file?path=' + q)
    try:
        j = json.loads(body)
    except ValueError:
        j = {}
    ok_read = code == 200 and '占位正文' in (j.get('content') or '')
    record('6a /api/file 读章节不再 400', ok_read,
           'http=%s chars=%s detail=%s' % (code, j.get('chars'), body[:90]))

    code2, body2 = http_json(base + '/api/stats?path=' + q)
    try:
        s = json.loads(body2)
    except ValueError:
        s = {}
    full = os.path.join(PROJECTS_ROOT, BOOK, '章节', '001-第1章.md')
    want = 0
    if os.path.exists(full):
        with open(full, encoding='utf-8') as fh:
            want = len(_re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]', fh.read()))
    ok_stats = (code2 == 200 and s.get('chars_cn') == want
                and str(s.get('path') or '').startswith('projects/'))
    record('6b /api/stats 汉字数与独立统计一致', ok_stats,
           'http=%s got=%s want=%s path=%s' % (code2, s.get('chars_cn'), want, s.get('path')))

    rel = 'projects/%s/章节/009-路径测试.md' % BOOK
    text = '# 路径测试' + chr(10) + chr(10) + '写盘副作用验证。' + chr(10)
    code3, body3 = http_json(base + '/api/save', 'POST', {'path': rel, 'content': text, 'force': True})
    disk = os.path.join(PROJECTS_ROOT, BOOK, '章节', '009-路径测试.md')
    got = None
    if os.path.exists(disk):
        with open(disk, encoding='utf-8') as fh:
            got = fh.read()
    ok_save = code3 == 200 and got == text
    record('6c /api/save 落盘字节与请求一致', ok_save,
           'http=%s exists=%s equal=%s' % (code3, got is not None, got == text))
    if os.path.exists(disk):
        os.remove(disk)

    code4, _ = http_json(base + '/api/save', 'POST',
                         {'path': '../../evil.md', 'content': 'x', 'force': True})
    code5, _ = http_json(base + '/api/save', 'POST',
                         {'path': 'D:/evil.md', 'content': 'x', 'force': True})
    code6, _ = http_json(base + '/api/file?path=' + urllib.parse.quote('projects/../evil.md', safe=''))
    ok_neg = code4 == 400 and code5 == 400 and code6 == 400
    record('6d 越界/绝对路径仍然 400', ok_neg,
           'dotdot=%s abs=%s read=%s' % (code4, code5, code6))

    code7, body7 = http_json(base + '/api/stats?path=' + urllib.parse.quote('projects/%s' % BOOK, safe=''))
    try:
        s7 = json.loads(body7)
    except ValueError:
        s7 = {}
    ok_dir = code7 == 200 and s7.get('path') == 'projects/%s' % BOOK and int(s7.get('files') or 0) >= 1
    record('6e 目录统计跨盘不 500', ok_dir,
           'http=%s path=%s files=%s' % (code7, s7.get('path'), s7.get('files')))


if __name__ == '__main__':
    import server as S
    PROJECTS_ROOT = S.PROJECTS
    cfg_path = os.path.join(ROOT, 'config', 'coordinator.json')
    backup = cfg_path + '.regress.bak'
    procs = []
    try:
        shutil.copy2(cfg_path, backup)
        cfg = json.load(open(cfg_path, encoding='utf-8'))
        cfg.setdefault('gateway', {})['base'] = 'http://127.0.0.1:%d' % STUB_PORT
        json.dump(cfg, open(cfg_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

        stub_py = os.path.join(tempfile.gettempdir(), '_regress_stub.py')
        open(stub_py, 'w', encoding='utf-8').write(STUB)
        env = dict(os.environ); env['REGRESS_DIR'] = os.path.join(ROOT, 'build')
        procs.append(subprocess.Popen([sys.executable, stub_py], cwd=os.path.join(ROOT, 'build'), env=env))
        procs.append(subprocess.Popen([sys.executable, os.path.join(ROOT, 'core', 'server.py'),
                                       str(API_PORT), '--no-browser'], cwd=ROOT))
        time.sleep(5)

        d = prepare()
        check_abort(d)
        check_newbook('http://127.0.0.1:%d' % API_PORT)
        check_missing()
        check_title(d)
        check_draft(d)
        check_paths(d)
    finally:
        for pr in procs:
            try: pr.terminate()
            except Exception: pass
        shutil.copy2(backup, cfg_path)
        os.remove(backup)
        import server as S2
        shutil.rmtree(os.path.join(S2.PROJECTS, BOOK), ignore_errors=True)

    bad = [n for n, ok, _ in results if not ok]
    print()
    print('结果: %d/%d PASS' % (len(results) - len(bad), len(results)))
    sys.exit(1 if bad else 0)
