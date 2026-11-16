# -*- coding: utf-8 -*-
"""小说工作台 HTTP（18771）：项目 / 卷章 / 工具带 / 创作向导 / 导出发布"""
from __future__ import annotations

import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import novel_api as N  # noqa: E402
import rank_api as R  # noqa: E402
import deai as D  # noqa: E402
import workflow as W  # noqa: E402
import chat as C  # noqa: E402
import prompts as P  # noqa: E402
import fusion as F  # noqa: E402
from ling import LingError  # noqa: E402

PORT = int(os.environ.get("NOVEL_PORT") or 18771)
HERE = os.path.dirname(os.path.abspath(__file__))



_HIDE_KEYS = ("in_ling", "out_ling", "total", "price", "in_price", "out_price",
              "cny", "cost", "cost_cny", "estimate", "tokens")


def _estimate_public(pid, data):
    """预估接口只回数量，不回钱（口径：界面不显示价格与预估金额）。"""
    est = N.estimate_generate(pid, data)
    return {k: v for k, v in est.items() if k not in _HIDE_KEYS}

class H(BaseHTTPRequestHandler):
    server_version = "NovelWorkbench/0.2"

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name, ctype):
        p = os.path.join(HERE, name)
        if not os.path.isfile(p):
            return self._json(404, {"error": "missing " + name})
        with open(p, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("[novel] " + (fmt % args) + "\n")

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            raise LingError("BAD_JSON", "请求体不是合法 JSON")

    def _redirect(self, to):
        """302 到工作台里的对应视图：旧页面不再单独存在。"""
        self.send_response(302)
        self.send_header("Location", to)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    # ---------------- GET ----------------
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            # 界面二（工作台 app.html）已从产品分离：这里只提供旧的四个页面
            if u.path in ("/", "/index.html", "/novel.html"):
                return self._file("novel.html", "text/html")
            if u.path in ("/rank", "/rank.html"):
                return self._file("rank.html", "text/html")
            if u.path in ("/tools", "/tools.html"):
                return self._file("tools.html", "text/html")
            if u.path in ("/workflow", "/workflow.html"):
                return self._file("workflow.html", "text/html")
            if u.path == "/api/novel/wizard/config":
                return self._json(200, {"channels": N.WCFG["channels"], "deck": N.DECK,
                                        "nine": N.NINE, "recipes": N.WCFG["recipes"]})
            if u.path == "/api/novel/prompts":
                return self._json(200, {"items": P.list_items((q.get("q") or [""])[0],
                                                              (q.get("category") or [""])[0],
                                                              (q.get("group") or [""])[0],
                                                              (q.get("sort") or ["uses"])[0]),
                                        "categories": P.CATEGORIES})
            if u.path == "/api/novel/workflow/sample":
                return self._json(200, W.sample())
            if u.path == "/api/novel/deai/presets":
                return self._json(200, {"types": [["novel", "小说"], ["script", "剧本"], ["media", "公众号/头条号"], ["paper", "报告"]],
                                        "versions": [["v3.3", "V3.3（综合性价比最佳）"], ["v4.0", "V4.0（最强自然表达）"], ["v1.0", "V1.0（学术）"]],
                                        "levels": [[1, "低"], [2, "中"], [3, "高"]],
                                        "limits": {"novel": 10000, "script": 10000, "media": 10000, "paper": 20000}})
            if u.path == "/api/novel/rank":
                qs = {k: (q.get(k) or [""])[0] for k in ("gender", "rank_type", "category_id", "force")}
                return self._json(200, R.rank(qs["gender"] or "1", qs["rank_type"] or "2",
                                              qs["category_id"] or "0", qs["force"] == "1"))
            if u.path == "/api/novel/trends":
                qs = {k: (q.get(k) or [""])[0] for k in ("gender", "rank_type", "category_id", "date", "expand", "force")}
                return self._json(200, R.trends(qs["gender"] or "1", qs["rank_type"] or "2", qs["category_id"] or "0",
                                                qs["date"], qs["expand"] == "true", qs["force"] == "1"))
            if u.path == "/api/novel/tools":
                return self._json(200, {"tools": N.TOOLS, "prompts": N.PROMPTS})
            if u.path == "/api/novel/edition":
                import edition as ED
                return self._json(200, {"fee_rate": ED.load().get("fee_rate", 0.0)})
            if u.path == "/api/novel/models":
                return self._json(200, {"models": N.LING.catalog.get("models", [])})
            if u.path == "/api/novel/projects":
                db = N.load_db()
                items = []
                for pj in db["projects"].values():
                    items.append({"id": pj["id"], "title": pj["title"], "channel": pj.get("channel"),
                                  "genre": pj.get("genre"), "word_goal": pj.get("word_goal"),
                                  "created": pj.get("created"), "chapters": len(pj.get("chapters") or []),
                                  "words": sum(c.get("words", 0) for c in pj.get("chapters") or []),
                                  "published": pj.get("published", False)})
                return self._json(200, {"projects": items})
            m = re.match(r"^/api/novel/chat/([0-9a-f]+)$", u.path)
            if m:
                cid = m.group(1)
                return self._json(200, {"conversation": C.get(cid), "path": C.path(cid), "tree": C.tree(cid)})
            m = re.match(r"^/api/novel/projects/([0-9a-f]+)$", u.path)
            if m:
                return self._json(200, N.get_project(m.group(1)))
            m = re.match(r"^/api/novel/projects/([0-9a-f]+)/export$", u.path)
            if m:
                return self._json(200, N.export_txt(m.group(1)))
            m = re.match(r"^/api/novel/chapters/([0-9a-f]+)/highfreq$", u.path)
            if m:
                return self._json(200, {"items": N.highfreq(m.group(1))})
            if u.path == "/api/ling/balance":
                return self._json(200, N.LING.balance((q.get("uid") or ["local"])[0]))
            return self._json(404, {"error": "not found"})
        except LingError as e:
            return self._json(404 if e.code == "NOT_FOUND" else 400, {"error": e.code, "message": str(e)})
        except Exception as e:
            import traceback; traceback.print_exc()
            return self._json(500, {"error": "internal", "message": "%s: %s" % (type(e).__name__, e)})

    # ---------------- POST ----------------
    def do_POST(self):
        u = urlparse(self.path)
        try:
            data = self._body()
            if u.path == "/api/novel/chat":
                return self._json(200, C.create(data.get("title") or "新对话"))
            if u.path == "/api/novel/prompts":
                return self._json(200, P.create(data))
            if u.path == "/api/novel/fusion":
                return self._json(200, F.fuse(data.get("books") or []))
            if u.path == "/api/novel/projects":
                return self._json(200, N.new_project(data))
            rules = [
                (r"^/api/novel/projects/([0-9a-f]+)/volumes$", lambda m: N.add_volume(m.group(1), data.get("title", ""))),
                (r"^/api/novel/projects/([0-9a-f]+)/chapters$", lambda m: N.add_chapter(m.group(1), data.get("title", ""), data.get("content", ""), data.get("volumeId", ""))),
                (r"^/api/novel/projects/([0-9a-f]+)/estimate$", lambda m: _estimate_public(m.group(1), data)),
                (r"^/api/novel/projects/([0-9a-f]+)/generate$", lambda m: N.generate(m.group(1), data, data.get("uid") or "local")),
                (r"^/api/novel/chapters/([0-9a-f]+)$", lambda m: N.update_chapter(m.group(1), data)),
                (r"^/api/novel/projects/([0-9a-f]+)/wizard$", lambda m: N.wizard_book(m.group(1), data, data.get("uid") or "local")),
                (r"^/api/novel/projects/([0-9a-f]+)/entries$", lambda m: N.save_entries(m.group(1), data.get("entries") or [])),
        (r"^/api/novel/projects/([0-9a-f]+)/book$", lambda m: N.wizard_book(m.group(1), data, data.get("uid") or "local")),
                (r"^/api/novel/workflow/run$", lambda m: W.run(data.get("workflow") or W.sample(),
                                                          data.get("inputs") or {}, data.get("refs") or {}, data.get("extras") or {})),
                (r"^/api/novel/workflow/validate$", lambda m: {"errors": W.validate(data.get("workflow") or W.sample())}),
                (r"^/api/novel/chat/([0-9a-f]+)/messages$", lambda m: C.append(m.group(1), data.get("role") or "user", data.get("content") or "", data.get("parent"))),
                (r"^/api/novel/chat/([0-9a-f]+)/fork$", lambda m: C.fork(m.group(1), data["message_id"], data.get("content") or "", data.get("role") or "user")),
                (r"^/api/novel/chat/([0-9a-f]+)/edit$", lambda m: C.edit(m.group(1), data["message_id"], data.get("content") or "")),
                (r"^/api/novel/chat/([0-9a-f]+)/switch$", lambda m: C.switch(m.group(1), data["message_id"])),
                (r"^/api/novel/prompts/([a-z0-9]+)/rate$", lambda m: P.rate(m.group(1), float(data.get("score") or 5))),
                (r"^/api/novel/prompts/([a-z0-9]+)/favorite$", lambda m: P.favorite(m.group(1), int(data.get("delta") or 1))),
                (r"^/api/novel/deai$", lambda m: D.rewrite(data.get("text", ""), data.get("type") or "novel",
                                                          data.get("version") or "v4.0", int(data.get("level") or 2),
                                                          use_llm=True)),
                (r"^/api/novel/wizard/step$", lambda m: N.wizard_step(data, data.get("uid") or "local")),
                (r"^/api/novel/wizard/draw$", lambda m: N.wizard_draw(data, data.get("uid") or "local")),
                (r"^/api/novel/wizard/imitate$", lambda m: N.wizard_imitate(data, data.get("uid") or "local")),
                (r"^/api/novel/wizard/parse$", lambda m: N.wizard_parse(data, data.get("uid") or "local")),
                (r"^/api/novel/wizard/furnace$", lambda m: N.wizard_furnace(data, data.get("uid") or "local")),
                (r"^/api/novel/projects/([0-9a-f]+)/publish$", lambda m: N.publish(m.group(1))),
                (r"^/api/novel/chapters/([0-9a-f]+)/approve$", lambda m: N.update_chapter(m.group(1), {"status": "approved"})),
                (r"^/api/novel/chapters/([0-9a-f]+)/action$", lambda m: N.run_text_tool(m.group(1), data, data.get("uid") or "local")),
                (r"^/api/novel/chapters/([0-9a-f]+)/replace$", lambda m: N.replace_in_chapter(m.group(1), data.get("find", ""), data.get("repl", ""))),
                (r"^/api/novel/chapters/([0-9a-f]+)/format$", lambda m: N.format_chapter(m.group(1))),
            ]
            for pat, fn in rules:
                m = re.match(pat, u.path)
                if m:
                    return self._json(200, fn(m))
            return self._json(404, {"error": "not found"})
        except LingError as e:
            return self._json(400, {"error": e.code, "message": str(e)})
        except Exception as e:
            import traceback; traceback.print_exc()
            return self._json(500, {"error": "internal", "message": "%s: %s" % (type(e).__name__, e)})

    # ---------------- PATCH ----------------
    def do_PATCH(self):
        u = urlparse(self.path)
        try:
            data = self._body()
            m = re.match(r"^/api/novel/chapters/([0-9a-f]+)$", u.path)
            if m:
                return self._json(200, N.update_chapter(m.group(1), data))
            m = re.match(r"^/api/novel/projects/([0-9a-f]+)$", u.path)
            if m:
                pj = N.get_project(m.group(1))
                for k in ("title", "channel", "genre", "word_goal", "idea", "protagonist",
                          "characters", "world", "golden_finger", "outline"):
                    if k in data:
                        pj[k] = data[k]
                N.put_project(pj)
                return self._json(200, pj)
            return self._json(404, {"error": "not found"})
        except LingError as e:
            return self._json(400, {"error": e.code, "message": str(e)})


class Srv(ThreadingHTTPServer):
    allow_reuse_address = False


def main():
    srv = Srv(("127.0.0.1", PORT), H)
    print("novel workbench on http://127.0.0.1:%d" % PORT, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()