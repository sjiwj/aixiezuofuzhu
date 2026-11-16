# -*- coding: utf-8 -*-
"""中断扣费探针：读 new-api 的 logs 表（只读），对号单次请求。

用法:
    python scripts/quota_probe.py --baseline                  # 测前：只看累计额度
    python scripts/quota_probe.py --since 3                   # 最近 3 分钟的请求行
    python scripts/quota_probe.py --request-id <REQUEST_ID>   # 精确对号（recommended）
    python scripts/quota_probe.py --last 1                    # 最新那一条

判读:
    · 中断测试先记 request_id（或 --last），中断后等 20-30 秒再查
    · use_time 应 ≈ (中断时刻 - 起点)；若 ≈ 整章耗时 → 服务端跑完了（bug）
    · quota 反映该次实际扣费，不受同时段其它会话干扰
"""
import argparse, os, sqlite3, sys, time

DB = os.environ.get("NEWAPI_DB", r"D:\relay\data\new-api.db")
COLS = "id, created_at, request_id, model_name, quota, prompt_tokens, completion_tokens, use_time, is_stream"


def connect(path):
    if not os.path.exists(path):
        sys.exit("找不到数据库: " + path)
    return sqlite3.connect("file:" + path.replace("\\", "/") + "?mode=ro", uri=True, timeout=5)


def show(rows):
    print("ROWS=%d" % len(rows))
    for r in rows:
        rid = (r[2] or "")[:16]
        vals = (r[0], r[1], rid) + tuple(r[3:])
        print("  id=%s t=%s rid=%s model=%s quota=%s pt=%s ct=%s use=%ss stream=%s" % vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--since", type=float, default=0, help="最近 N 分钟")
    ap.add_argument("--request-id", default="")
    ap.add_argument("--last", type=int, default=0, help="最新 N 条")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    con = connect(args.db)
    cur = con.cursor()
    cur.execute("SELECT COALESCE(SUM(quota),0) FROM logs WHERE type=2")
    print("TOTAL_QUOTA=%d  at=%s" % (cur.fetchone()[0], time.strftime("%H:%M:%S")))

    if args.request_id:
        cur.execute("SELECT " + COLS + " FROM logs WHERE type=2 AND request_id LIKE ? ORDER BY id DESC LIMIT ?",
                    ("%" + args.request_id + "%", args.limit))
        show(cur.fetchall())
        return 0

    if args.last:
        cur.execute("SELECT " + COLS + " FROM logs WHERE type=2 ORDER BY id DESC LIMIT ?", (args.last,))
        show(cur.fetchall())
        return 0

    if args.baseline:
        return 0

    sql = "SELECT " + COLS + " FROM logs WHERE type=2"
    params = ()
    if args.since > 0:
        sql += " AND created_at >= ?"
        params = (int(time.time() - args.since * 60),)
    sql += " ORDER BY id DESC LIMIT ?"
    params = params + (args.limit,)
    cur.execute(sql, params)
    show(cur.fetchall())
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
