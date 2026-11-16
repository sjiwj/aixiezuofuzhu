# -*- coding: utf-8 -*-
"""分时段定价：高峰 / 空闲自动切换

DeepSeek 官方定义（2026-11）：
  高峰：北京时间周一至周五 9:00-12:00、14:00-18:00
  空闲：其余时段，含周末全天
  空闲价 = 高峰价的一半

定价 = 官方价 x (1 + 服务费率)；服务费率读 config/coordinator.json 的 gateway.fee_rate
（2026-11-10：默认 0，按官方价收，方便实测；要恢复 5% 就把 fee_rate 改回 0.05）

关键限制：new-api 有内存缓存，改 DB 不生效，必须重启（约 15 秒）。
所以用定时任务每 30 分钟检查一次，价格不对就切换。

用法：
  python core/pricing.py --check
  python core/pricing.py --apply
  python core/pricing.py --force peak
  python core/pricing.py --force off
"""
import os, sys, json, time, socket, sqlite3, argparse, subprocess
from datetime import datetime, timedelta, timezone

DB = r"D:\relay\data\new-api.db"
NEWAPI = r"D:\relay\new-api\new-api.exe"
NEWAPI_DIR = r"D:\relay\new-api"
PORT = 3000
RATIO_UNIT = 14.6
BJ = timezone(timedelta(hours=8))

# 中国法定节假日（放假日 = 空闲时段，官方按空闲价收）
# 来源：国办发明电〔2025〕7号（2026 年安排，2025-11-04 发布）
# 注意：调休上班的周六（2/14、2/28、5/9、9/20、10/10）不特殊处理——
#       DeepSeek 规则是「其余时段含周末全天均为空闲」，所以周六一律空闲
HOLIDAYS = {
    "2026-01-01",
    "2026-01-02",
    "2026-01-03",
    "2026-02-15",
    "2026-02-16",
    "2026-02-17",
    "2026-02-18",
    "2026-02-19",
    "2026-02-20",
    "2026-02-21",
    "2026-02-22",
    "2026-02-23",
    "2026-04-04",
    "2026-04-05",
    "2026-04-06",
    "2026-05-01",
    "2026-05-02",
    "2026-05-03",
    "2026-05-04",
    "2026-05-05",
    "2026-06-19",
    "2026-06-20",
    "2026-06-21",
    "2026-09-25",
    "2026-09-26",
    "2026-09-27",
    "2026-10-01",
    "2026-10-02",
    "2026-10-03",
    "2026-10-04",
    "2026-10-05",
    "2026-10-06",
    "2026-10-07",
}

CFG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "coordinator.json")


def service_fee():
    """服务费率：读 config/coordinator.json 的 gateway.fee_rate。

    0（默认）= 按官方价收；0.05 = 官方价 +5%。注意 0 是合法值，
    不能用 `or 0.05` 这种写法（0 会被吞掉）。
    """
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            g = (json.load(f) or {}).get("gateway") or {}
        v = g.get("fee_rate")
        return float(v) if v is not None else 0.0
    except Exception:
        return 0.0


FEE = 1.0 + service_fee()

PEAK = {
    "deepseek-flash":  {"in": 2.00 * FEE, "out": 8.00 * FEE},
    "deepseek-v4-pro": {"in": 9.00 * FEE, "out": 27.00 * FEE},
}
OFF = {
    "deepseek-flash":  {"in": 1.00 * FEE, "out": 4.00 * FEE},
    "deepseek-v4-pro": {"in": 4.50 * FEE, "out": 13.50 * FEE},
}


def is_peak(now=None):
    """判断当前是否高峰时段

    高峰：周一至周五（非法定节假日）9:00-12:00、14:00-18:00
    其余全为空闲（含周末、法定节假日全天）
    """
    now = now or datetime.now(BJ)
    # 法定节假日 → 空闲
    if now.strftime("%Y-%m-%d") in HOLIDAYS:
        return False
    # 周末 → 空闲（含调休上班的周六）
    if now.weekday() >= 5:
        return False
    # 工作日的高峰时段
    h = now.hour + now.minute / 60.0
    return (9.0 <= h < 12.0) or (14.0 <= h < 18.0)


def current_prices():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT value FROM options WHERE key = ?", ("ModelRatio",))
    mr = json.loads(cur.fetchone()[0])
    cur.execute("SELECT value FROM options WHERE key = ?", ("CompletionRatio",))
    cr = json.loads(cur.fetchone()[0])
    con.close()
    out = {}
    for m in PEAK:
        if m in mr:
            i = mr[m] * RATIO_UNIT
            o = i * cr.get(m, 1)
            out[m] = {"in": round(i, 4), "out": round(o, 4)}
    return out, mr, cr


def same(a, b, tol=0.02):
    return abs(a - b) < tol


def restart_gateway():
    ps = "(Get-NetTCPConnection -LocalPort %d -State Listen -EA SilentlyContinue).OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -EA SilentlyContinue }" % PORT
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=30)
    except Exception:
        pass
    time.sleep(5)
    subprocess.Popen([NEWAPI], cwd=NEWAPI_DIR, creationflags=0x08000000)
    for _ in range(30):
        try:
            s = socket.create_connection(("127.0.0.1", PORT), timeout=1)
            s.close()
            return True
        except Exception:
            time.sleep(1)
    return False


def apply_prices(prices, do_restart=True):
    cur, mr, cr = current_prices()
    changed = []
    for m, p in prices.items():
        if m not in mr:
            continue
        want_ratio = round(p["in"] / RATIO_UNIT, 6)
        want_comp = round(p["out"] / p["in"], 4)
        if not same(mr[m], want_ratio, 0.002):
            mr[m] = want_ratio
            changed.append(m)
        cr[m] = want_comp
    if not changed:
        return {"changed": [], "restarted": False}
    con = sqlite3.connect(DB)
    cur2 = con.cursor()
    cur2.execute("UPDATE options SET value = ? WHERE key = ?", (json.dumps(mr, ensure_ascii=False), "ModelRatio"))
    cur2.execute("UPDATE options SET value = ? WHERE key = ?", (json.dumps(cr, ensure_ascii=False), "CompletionRatio"))
    con.commit()
    con.close()
    ok = restart_gateway() if do_restart else False
    return {"changed": changed, "restarted": ok}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", choices=["peak", "off"], default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-restart", action="store_true")
    args = ap.parse_args()

    now = datetime.now(BJ)
    peak = is_peak(now)
    if args.force:
        prices = PEAK if args.force == "peak" else OFF
    else:
        prices = PEAK if peak else OFF

    cur, _, _ = current_prices()

    if args.json:
        print(json.dumps({
            "now": now.strftime("%Y-%m-%d %H:%M:%S"),
            "weekday": now.strftime("%A"),
            "peak": peak,
            "target": prices,
            "current": cur,
        }, ensure_ascii=False, indent=1))
        return 0

    print("=== 分时段定价 ===")
    print("  现在: %s %s（%s）" % (now.strftime("%Y-%m-%d %H:%M"), now.strftime("%A"), "高峰" if peak else "空闲"))
    print()
    print("  %-18s %-20s %-20s" % ("模型", "当前价(入/出)", "目标价(入/出)"))
    print("  " + "-" * 60)
    need = False
    for m, p in prices.items():
        c = cur.get(m, {})
        mark = ""
        if c and not same(c.get("in", 0), p["in"], 0.03):
            mark = "  <- 要改"
            need = True
        print("  %-18s %6.2f / %6.2f      %6.2f / %6.2f%s" % (
            m, c.get("in", 0), c.get("out", 0), p["in"], p["out"], mark))

    if args.apply or args.force:
        if not need and not args.force:
            print()
            print("  价格已是目标值，不用改")
            return 0
        print()
        r = apply_prices(prices, do_restart=not args.no_restart)
        print("  已改: %s" % (", ".join(r["changed"]) or "无"))
        print("  重启网关: %s" % ("成功" if r["restarted"] else "未重启或失败"))
        new, _, _ = current_prices()
        print()
        print("  改后:")
        for m, v in new.items():
            print("    %-18s %6.2f / %6.2f" % (m, v["in"], v["out"]))
    else:
        print()
        print("  需要切换。加 --apply 执行。" if need else "  价格正确。")
    return 0


if __name__ == "__main__":
    sys.exit(main())