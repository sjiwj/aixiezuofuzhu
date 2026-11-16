# -*- coding: utf-8 -*-
import io, sys
p = r"D:\NovelApp\core\server.py"
s = io.open(p, encoding="utf-8").read()
if "def _inspire" in s:
    print("ALREADY")
    sys.exit(0)

METHOD = r'''    def _inspire(self, data):
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
                send({'type': 'error', 'variant': idx, 'message': '%s: %s' % (type(e).__name__, e)})
                continue
            billing = resp.get('_billing') or {}
            text = CO.sanitize_worker_text(CO._extract_content(resp) or '').strip()
            if not text:
                send({'type': 'error', 'variant': idx, 'message': '模型空输出'})
                continue
            results.append(text)
            send({'type': 'variant', 'index': idx, 'text': text,
                  'tokens': int(billing.get('total_tokens') or 0),
                  'cny': round(float(billing.get('total_cny') or 0), 6)})
            log_usage('inspire', book, chapter, billing, {'variant': idx})
        send({'type': 'done', 'variants': len(results)})

'''
anchor = "    def _polish(self, data):"
i = s.find(anchor)
if i < 0:
    print("method anchor missing"); sys.exit(1)
s = s[:i] + METHOD + s[i:]

ROUTE = ("            if u.path == '/api/inspire':" + chr(10) +
         "                self._inspire(data)" + chr(10) +
         "                return" + chr(10))
old = "            if u.path == '/api/polish':"
j = s.find(old)
if j < 0:
    print("route anchor missing"); sys.exit(1)
s = s[:j] + ROUTE + s[j:]

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("inspire method + route added, len", len(s))
