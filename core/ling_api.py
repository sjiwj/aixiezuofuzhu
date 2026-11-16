# -*- coding: utf-8 -*-
"""灵石 HTTP 接口（独立进程，不侵入 core/server.py）

端口 18770，只读公开模型表 + 账本操作，供前端与 curl 联调。
并入主服务时把 handle() 的分支搬进 server.py 的 do_GET/do_POST 即可。

  GET  /api/ling/health
  GET  /api/ling/models?tier=free
  GET  /api/ling/balance?uid=u1
  GET  /api/ling/statement?uid=u1
  POST /api/ling/quote    {"model","in_chars","out_chars"}
  POST /api/ling/reserve  {"uid","model","in_chars","out_chars_est"}
  POST /api/ling/commit   {"usage_id","out_chars"}
  POST /api/ling/refund   {"usage_id"}
  POST /api/ling/grant    {"uid","amount","bucket"?,"kind"?}
  POST /api/ling/invite   {"inviter","invitee"}
  POST /api/ling/tier     {"uid","tier"}
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ling import Ling, LingError, TIER_DAILY  # noqa: E402

PORT = int(os.environ.get("LING_PORT") or 18770)
LEDGER = Ling()


def _models(tier: str | None = None):
    out = []
    for m in LEDGER.catalog.get("models", []):
        if not m.get("enabled", True):
            continue
        item = {k: m.get(k) for k in
                ("name", "displayName", "provider", "providerGroup",
                 "inputLingPerKChar", "outputLingPerKChar", "inputRmbPerKChar", "outputRmbPerKChar", "minTier")}
        item["unlocked"] = (not tier) or (m.get("minTier") in (None, "FREE")) or tier in ("basic", "platinum", "max")
        out.append(item)
    return out


class H(BaseHTTPRequestHandler):
    server_version = "NovelAppLing/0.1"

    def _send(self, code: int, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("[ling] " + (fmt % args) + "\n")

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/api/ling/health", "/health"):
                return self._send(200, {"ok": True, "models": len(LEDGER.by_name), "tiers": TIER_DAILY})
            if u.path in ("/", "/demo"):
                p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ling_demo.html")
                if os.path.isfile(p):
                    with open(p, "rb") as f:
                        body = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return self._send(404, {"error": "demo missing"})
            if u.path == "/api/ling/models":
                tier = (q.get("tier") or [None])[0]
                return self._send(200, {"models": _models(tier)})
            if u.path == "/api/ling/balance":
                uid = (q.get("uid") or [""])[0]
                if not uid:
                    return self._send(400, {"error": "uid required"})
                return self._send(200, LEDGER.balance(uid))
            if u.path == "/api/ling/statement":
                uid = (q.get("uid") or [""])[0]
                return self._send(200, {"items": LEDGER.statement(uid)})
            return self._send(404, {"error": "not found"})
        except LingError as e:
            return self._send(400, {"error": e.code, "message": str(e)})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except Exception:
            return self._send(400, {"error": "bad json"})
        try:
            if u.path == "/api/ling/quote":
                return self._send(200, LEDGER.quote(data.get("model", ""), int(data.get("in_chars") or 0), int(data.get("out_chars") or 0)))
            if u.path == "/api/ling/reserve":
                return self._send(200, LEDGER.reserve(data["uid"], data["model"], int(data.get("in_chars") or 0), int(data.get("out_chars_est") or 0)))
            if u.path == "/api/ling/commit":
                return self._send(200, LEDGER.commit(data["usage_id"], int(data.get("out_chars") or 0)))
            if u.path == "/api/ling/refund":
                return self._send(200, LEDGER.refund(data["usage_id"]))
            if u.path == "/api/ling/grant":
                return self._send(200, LEDGER.grant(data["uid"], int(data["amount"]), data.get("bucket") or "permanent", data.get("kind") or "grant"))
            if u.path == "/api/ling/invite":
                return self._send(200, LEDGER.invite(data["inviter"], data["invitee"]))
            if u.path == "/api/ling/tier":
                return self._send(200, LEDGER.set_tier(data["uid"], data["tier"]))
            return self._send(404, {"error": "not found"})
        except KeyError as e:
            return self._send(400, {"error": "missing field", "field": str(e)})
        except LingError as e:
            return self._send(400, {"error": e.code, "message": str(e)})


class Srv(ThreadingHTTPServer):
    # Windows 下 SO_REUSEADDR 允许重复绑定同一端口，会静默起两个服务；
    # 关掉它，端口被占时直接报错，而不是"看起来启动了但连不上"。
    allow_reuse_address = False


def main():
    srv = Srv(("127.0.0.1", PORT), H)
    print("ling api on http://127.0.0.1:%d" % PORT, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
