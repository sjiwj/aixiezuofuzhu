# -*- coding: utf-8 -*-
"""AI 小说榜 · 数据层（复刻炼字 /rank）

真实接口（公开 GET，无需登录）：
  GET /api/fanqie/rank?gender=1|0&rank_type=2|1&category_id=0|fanqieId
  GET /api/fanqie/writing-trends?gender&rank_type&category_id&history=true[&date=&expand=true]

本地做磁盘缓存（默认 6 小时），避免反复打对方；force=1 才刷新。
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "rank")
BASE = "https://lianzigongfang.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TTL = 6 * 3600

PUA_MAP_PATH = os.path.join(ROOT, "config", "pua_map.json")
try:
    with open(PUA_MAP_PATH, encoding="utf-8") as _f:
        _PUA = (json.load(_f) or {}).get("map") or {}
except (OSError, ValueError):
    _PUA = {}


def decode_text(s):
    """PUA 码位 → 汉字；未命中用 □ 占位并计数"""
    if not isinstance(s, str) or not s:
        return s, 0
    miss = 0
    out = []
    for ch in s:
        cp = ord(ch)
        if 0xE000 <= cp <= 0xF8FF:
            v = _PUA.get(format(cp, "x"))
            if v:
                out.append(v)
            else:
                out.append("□")
                miss += 1
        else:
            out.append(ch)
    return "".join(out), miss


def decode_novel(n: dict):
    miss = 0
    for k in ("title", "author", "description"):
        v, m = decode_text(n.get(k) or "")
        n[k] = v
        miss += m
    if isinstance(n.get("tags"), list):
        tags = []
        for t in n["tags"]:
            v, m = decode_text(str(t))
            tags.append(v)
            miss += m
        n["tags"] = tags
    return miss


def _path(kind: str, key: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, "%s-%s.json" % (kind, key))


def _fresh(p: str) -> bool:
    return os.path.isfile(p) and (time.time() - os.path.getmtime(p)) < TTL


def _get(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _cached(kind: str, key: str, url: str, force: bool):
    p = _path(kind, key)
    if not force and _fresh(p):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        d["_cache"] = {"hit": True, "file": p}
        if isinstance(d.get("novels"), list):
            miss = sum(decode_novel(n) for n in d["novels"])
            d["_decode"] = {"mapped": len(_PUA), "missing": miss}
        return d
    d = _get(url)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    d["_cache"] = {"hit": False, "file": p}
    if isinstance(d.get("novels"), list):
        miss = sum(decode_novel(n) for n in d["novels"])
        d["_decode"] = {"mapped": len(_PUA), "missing": miss}
    return d


def rank(gender: str = "1", rank_type: str = "2", category_id: str = "0", force: bool = False):
    key = "%s_%s_%s" % (gender, rank_type, category_id)
    q = urllib.parse.urlencode({"gender": gender, "rank_type": rank_type, "category_id": category_id})
    return _cached("rank", key, BASE + "/api/fanqie/rank?" + q, force)


def trends(gender: str = "1", rank_type: str = "2", category_id: str = "0",
           date: str = "", expand: bool = False, force: bool = False):
    key = "%s_%s_%s%s" % (gender, rank_type, category_id, ("_" + date) if date else "")
    q = {"gender": gender, "rank_type": rank_type, "category_id": category_id, "history": "true"}
    if date:
        q["date"] = date
    if expand:
        q["expand"] = "true"
    return _cached("trends", key, BASE + "/api/fanqie/writing-trends?" + urllib.parse.urlencode(q), force)
