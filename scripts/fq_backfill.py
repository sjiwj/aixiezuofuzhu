# -*- coding: utf-8 -*-
"""番茄样本慢速回填（给 PUA 映射补字用）

规矩（写死在这里，别手滑）：
  - 单线程，顺序请求；
  - 每次间隔 2.0–4.0 秒随机，且每 20 本多停 30 秒；
  - 单次运行上限 40 本；
  - 命中本地缓存直接跳过，绝不重抓；
  - 只抓书页公开信息（bookName / abstract），不碰章节正文。

用法：
  python scripts/fq_backfill.py --rank female --limit 30
  python scripts/fq_backfill.py --ids 7617740782291651646 7665193065501445145
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "rank", "fq")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
MAX_PER_RUN = 40


def fetch_book(bid: str) -> dict | None:
    fp = os.path.join(CACHE, bid + ".json")
    if os.path.isfile(fp):
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    url = "https://fanqienovel.com/page/" + bid
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            t = r.read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        print("  ! fail", bid, type(e).__name__)
        return None
    name = (re.search(r'"bookName":"([^"]+)"', t) or [None, ""])[1]
    abs_ = (re.search(r'"abstract":"((?:[^"\\]|\\.)*)"', t) or [None, ""])[1]
    rec = {"id": bid, "plain": name, "abs": abs_.replace("\\n", "\n")}
    os.makedirs(CACHE, exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rank", default="male", choices=["male", "female"])
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--ids", nargs="*", default=[])
    a = ap.parse_args()

    ids = a.ids
    if not ids:
        gender, rank_type = ("1", "2") if a.rank == "male" else ("0", "2")
        q = "gender=%s&rank_type=%s&category_id=0" % (gender, rank_type)
        req = urllib.request.Request("https://lianzigongfang.com/api/fanqie/rank?" + q,
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        ids = [n["id"] for n in d.get("novels", [])]

    ids = ids[: min(a.limit, MAX_PER_RUN)]
    todo = [i for i in ids if not os.path.isfile(os.path.join(CACHE, i + ".json"))]
    print("target=%d todo=%d (cached %d)" % (len(ids), len(todo), len(ids) - len(todo)))
    for k, bid in enumerate(todo, 1):
        rec = fetch_book(bid)
        print("  [%d/%d] %s %s" % (k, len(todo), bid, (rec or {}).get("plain", "fail")[:20]))
        time.sleep(random.uniform(2.0, 4.0))
        if k % 20 == 0:
            print("  .. cooldown 30s")
            time.sleep(30)
    print("done")


if __name__ == "__main__":
    main()
