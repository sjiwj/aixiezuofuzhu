# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\core\server.py"
s = io.open(p, encoding="utf-8").read()
if "def _debt(" in s:
    print("ALREADY"); raise SystemExit

# 1) 两个 lib 加载器（跟在 scene_tag_lib 后面）
old = '    import scene_tag as _scene_tag' + chr(10) + '    return _scene_tag'
if old not in s:
    print("lib anchor missing"); raise SystemExit(1)
NEW_LIBS = old + chr(10) + chr(10) + chr(10) + '''def _script_lib(name):
    """按名字加载 scripts/ 下的模块（debt_view / completion_feasibility 等）。"""
    p = os.path.join(ROOT, "scripts")
    if p not in sys.path:
        sys.path.insert(0, p)
    return __import__(name)
'''
s = s.replace(old, NEW_LIBS, 1)

# 2) 两个方法（放在 _scene_tag_set 之后）
anchor = '    # \u5220\u9664\uff1a\u4e00\u5f8b\u5148\u8fdb data/.trash/<\u65f6\u95f4\u6233>/\uff0c\u5ba2\u6237\u540e\u6094\u80fd\u635e\u56de\u6765'
if anchor not in s:
    print("method anchor missing"); raise SystemExit(1)
METHODS = '''    # \u8bfb\u503a / \u5b8c\u7ed3\u53ef\u884c\u6027\uff1a\u63a5\u7684\u662f scripts/ \u91cc\u7684\u7eaf\u811a\u672c\uff0c\u4e0d\u91cd\u590d\u5b9e\u73b0\u4e00\u4efd
    def _debt(self, q):
        book = (q.get("book") or [""])[0]
        chapter = (q.get("chapter") or [""])[0]
        if not book:
            self._json({"ok": False, "error": "book \u5fc5\u586b"}, 400)
            return
        try:
            lib = _script_lib("debt_view")
            rep = lib.build_debt(book, chapter or None)
        except Exception as e:
            self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)
            return
        self._json(rep, 200 if rep.get("ok") else 404)

    def _completion(self, q):
        book = (q.get("book") or [""])[0]
        planned = (q.get("planned") or [""])[0]
        if not book:
            self._json({"ok": False, "error": "book \u5fc5\u586b"}, 400)
            return
        try:
            lib = _script_lib("completion_feasibility")
            rep = lib.run_report(book, int(planned) if str(planned).isdigit() else None)
        except AttributeError:
            # \u811a\u672c\u53ea\u66b4\u9732\u4e86 main()\uff1a\u7528 completion \u76f4\u63a5\u7b97
            try:
                import completion as _c
                rep = _c.build(book, int(planned) if str(planned).isdigit() else None)
            except Exception as e:
                self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)
                return
        except Exception as e:
            self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)
            return
        self._json(rep, 200)

'''
s = s.replace(anchor, METHODS + anchor, 1)

# 3) GET 路由（跟在 /api/scene-tag 后面那个 elif 之后）
old_route = "            elif u.path == '/api/scene-tag':" + chr(10) + "                self._scene_tag(q)"
if old_route not in s:
    print("route anchor missing"); raise SystemExit(1)
NEW_ROUTE = old_route + chr(10) + \
           "            elif u.path == '/api/debt':" + chr(10) + \
           "                self._debt(q)" + chr(10) + \
           "            elif u.path == '/api/completion':" + chr(10) + \
           "                self._completion(q)"
s = s.replace(old_route, NEW_ROUTE, 1)

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("routes + methods added")