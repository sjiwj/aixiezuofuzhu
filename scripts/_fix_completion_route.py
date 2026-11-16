# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\core\server.py"
s = io.open(p, encoding="utf-8").read()

old_start = "    def _completion(self, q):"
i = s.find(old_start)
if i < 0:
    print("missing"); raise SystemExit(1)
j = s.find("    # \u5220\u9664\uff1a\u4e00\u5f8b\u5148\u8fdb data/.trash", i)
if j < 0:
    print("end missing"); raise SystemExit(1)

NEW = '''    def _completion(self, q):
        book = (q.get("book") or [""])[0]
        planned = (q.get("planned") or [""])[0]
        if not book:
            self._json({"ok": False, "error": "book \u5fc5\u586b"}, 400)
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
            self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)

'''
s = s[:i] + NEW + s[j:]
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("_completion rewritten -> analyze/report")