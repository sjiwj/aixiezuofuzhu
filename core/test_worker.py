# -*- coding: utf-8 -*-
"""worker 路由自测：本地假 OpenAI 兼容服务，覆盖乱码来源的每一种形态。"""
import json, sys, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, 'core')
import coordinator as CO

STATE = {'mode': 'str', 'last_body': None}


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        STATE['last_body'] = json.loads(self.rfile.read(n).decode('utf-8'))
        m = STATE['mode']
        if m == 'http500':
            body = b'{"error":{"message":"upstream boom"}}'
            self.send_response(500)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if m == 'notjson':
            body = b'<html><body>502 Bad Gateway</body></html>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if m == 'str':
            msg = {'role': 'assistant', 'content': '正常一句话。'}
        elif m == 'list':
            msg = {'role': 'assistant', 'content': [
                {'type': 'text', 'text': '前半句，'},
                {'type': 'text', 'text': '后半句。'}]}
        elif m == 'reasoning':
            msg = {'role': 'assistant', 'content': None, 'reasoning_content': '思考出来的正文。'}
        elif m == 'tokens':
            msg = {'role': 'assistant', 'content': '<|im_start|>assistant\n<<< < < 标题\n【正文】他推开门。\n<|end of sentence|>'}
        elif m == 'empty':
            msg = {'role': 'assistant', 'content': '   '}
        elif m == 'toolcall':
            msg = {'role': 'assistant', 'content': None,
                   'tool_calls': [{'id': 'x', 'type': 'function',
                                   'function': {'name': 'f', 'arguments': '{}'}}]}
        elif m == 'errobj':
            obj = {'error': {'message': 'invalid api key'}}
            body = json.dumps(obj).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        else:
            msg = {'role': 'assistant', 'content': '?'}
        body = json.dumps({'choices': [{'index': 0, 'message': msg}]}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

EP = 'http://127.0.0.1:%d/v1' % PORT
CFG = {'coordinator': {'api_key': 'k'},
       'workers': {r: {'model': 'mock', 'endpoint': EP, 'api_key': 'k'}
                   for r in ('research', 'thinking', 'writing', 'quality')}}

fails = []


def check(label, got, want_pred, detail=''):
    ok = want_pred(got)
    print(('PASS ' if ok else 'FAIL ') + label + ' -> ' + repr(got)[:200])
    if not ok:
        fails.append(label + ' | got=' + repr(got)[:200] + (' | ' + detail if detail else ''))


# 1 正常 str
STATE['mode'] = 'str'
check('1 正常 str', CO.tool_call_worker('writing', '写一句', CFG), lambda s: s == '正常一句话。')

# 2 content 为分段数组（旧实现会吐 [{...}] 伪结构）
STATE['mode'] = 'list'
check('2 分段数组归一', CO.tool_call_worker('writing', '写一句', CFG),
      lambda s: s == '前半句，后半句。' and '[{' not in s)

# 3 content=None + reasoning_content
STATE['mode'] = 'reasoning'
check('3 reasoning 兜底', CO.tool_call_worker('thinking', '想一下', CFG),
      lambda s: s == '思考出来的正文。')

# 4 模板控制符号 <<< 与 <|im_start|> 必须清掉
STATE['mode'] = 'tokens'
out4 = CO.tool_call_worker('writing', '写一句', CFG)
check('4 控制符号清洗', out4,
      lambda s: '<' not in s and 'im_start' not in s and '他推开门。' in s)

# 5 HTTP 500 -> 可读错误，不抛异常
STATE['mode'] = 'http500'
check('5 HTTP500 可读', CO.tool_call_worker('writing', 'x', CFG),
      lambda s: s.startswith('[worker 错误]') and '500' in s)

# 6 非 JSON（网关错误页）
STATE['mode'] = 'notjson'
check('6 非JSON可读', CO.tool_call_worker('writing', 'x', CFG),
      lambda s: s.startswith('[worker 错误]') and 'JSON' in s)

# 7 error 字段
STATE['mode'] = 'errobj'
check('7 error字段可读', CO.tool_call_worker('writing', 'x', CFG),
      lambda s: s.startswith('[worker 错误]') and 'invalid api key' in s)

# 8 空内容
STATE['mode'] = 'empty'
check('8 空内容可读', CO.tool_call_worker('writing', 'x', CFG),
      lambda s: s.startswith('[worker 错误]') and '空内容' in s)

# 9 只有工具调用
STATE['mode'] = 'toolcall'
check('9 只有tool_calls可读', CO.tool_call_worker('writing', 'x', CFG),
      lambda s: s.startswith('[worker 错误]') and '工具调用' in s)

# 10 角色大小写 / 别名（旧实现直接判未知角色）
STATE['mode'] = 'str'
for alias in ('WRITING', 'Writing', '写作', 'writer', ' QianZhi ', 'qc', '研究'):
    check('10 角色别名 %r' % alias, CO.tool_call_worker(alias, '写一句', CFG),
          lambda s: s == '正常一句话。')

# 11 未知角色
check('11 未知角色', CO.tool_call_worker('nope', 'x', CFG),
      lambda s: '未知角色' in s and 'writing' in s)

# 12 空 prompt 不发给模型
STATE['mode'] = 'str'
STATE['last_body'] = None
check('12 空prompt拦截', CO.tool_call_worker('writing', '   ', CFG),
      lambda s: 'prompt 为空' in s and STATE['last_body'] is None)

# 13 writing 角色必须带 system 约束（旧实现裸调，模型会答 "How can I help you?"）
STATE['mode'] = 'str'
CO.tool_call_worker('writing', '写一句', CFG)
body = STATE['last_body']
check('13 writing 带system', body, lambda b: b['messages'][0]['role'] == 'system'
      and '正文' in b['messages'][0]['content'] and b['messages'][-1]['role'] == 'user')

srv.shutdown()
print('----')
print('FAILED: %d' % len(fails))
for f in fails:
    print('  ' + f)
sys.exit(1 if fails else 0)
