# -*- coding: utf-8 -*-
"""上游渠道余额与真实成本监控（v2）

用法:
  python check-balance.py           查一次
  python check-balance.py --json    输出 JSON
  python check-balance.py --watch   每 6 小时

v2 改动（2026-11-06）：
  1. 主指标改成「渠道 used_quota 增量」，不再用「余额差」
     —— 余额有账单延迟（实测 4-8 小时），quota 是实时的
  2. 余额只做二次校验，偏离 >50% 记 WARN 而不是判倒挂
  3. 按 token 名区分测试/客户，测试消耗不计入毛利
"""
import sqlite3
import json
import sys
import os
import time
import urllib.request

DB = r"D:\relay\data\new-api.db"
STATE = r"D:\NovelApp\data\balance-state.json"
QUOTA_PER_UNIT = 500000
PRICE_RATIO = 7.3
ALERT_THRESHOLD = 0.10
# --topup N 手工登记区间内充值额（余额 API 无充值流水，只能人工登记）
# --topup-channel NAME 指定登记到哪个渠道，默认 deepseek
FORCED_TOPUP = 0.0
TOPUP_CHANNEL = "deepseek"
# 单令牌 1 小时消耗告警线（元）—— 一天写 20 章 kimi/glm 全开约 10 元/小时，5 元太低
HOURLY_SPIKE_CNY = 30.0
# 同一令牌出现几个不同 IP 就告警
MULTI_IP_THRESHOLD = 3
LOW_BALANCE_CNY = 50.0
DEVIATION_WARN = 0.50        # 余额差与 quota 差偏离超过 50% 记 WARN

# 测试用 token 名包含这些词的，不计入毛利（是我自己烧的）
TEST_TOKEN_MARKS = ("test", "debug", "dev")


def q(sql, args=()):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall()
    con.close()
    return rows


def cny(quota):
    return (quota or 0) / QUOTA_PER_UNIT * PRICE_RATIO


def is_test_token(name):
    n = (name or "").lower()
    return any(m in n for m in TEST_TOKEN_MARKS)


def deepseek_balance(key):
    """返回 (dict|None, note)。
    必须区分 total / topped_up / granted：
      total = granted + topped_up
    充值只增加 topped_up，消耗只减少 topped_up。
    只看 total 的差分，会把「充值」误当成「负消耗」。
    """
    try:
        req = urllib.request.Request("https://api.deepseek.com/user/balance",
                                     headers={"Authorization": "Bearer " + key})
        r = json.loads(urllib.request.urlopen(req, timeout=15).read())
        bi = r.get("balance_infos") or []
        if bi:
            b0 = bi[0]
            return {
                "total": float(b0.get("total_balance", 0)),
                "topped_up": float(b0.get("topped_up_balance", 0) or 0),
                "granted": float(b0.get("granted_balance", 0) or 0),
                "currency": b0.get("currency", "CNY"),
            }, "CNY"
        return None, "no balance_infos"
    except Exception as e:
        return None, str(e)[:80]


def moonshot_balance(key):
    try:
        req = urllib.request.Request("https://api.moonshot.cn/v1/users/me/balance",
                                     headers={"Authorization": "Bearer " + key})
        r = json.loads(urllib.request.urlopen(req, timeout=15).read())
        d = r.get("data") or {}
        if d.get("available_balance") is not None:
            return float(d["available_balance"]), "CNY"
        return None, json.dumps(r)[:80]
    except Exception as e:
        return None, str(e)[:80]


def zhipu_check(key):
    """智谱没有余额 API，用一次极小请求探活"""
    try:
        body = json.dumps({"model": "glm-4.5-air",
                           "messages": [{"role": "user", "content": "hi"}],
                           "max_tokens": 1}).encode()
        req = urllib.request.Request("https://open.bigmodel.cn/api/paas/v4/chat/completions",
                                     data=body,
                                     headers={"Authorization": "Bearer " + key,
                                              "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20)
        return "ok", None
    except Exception as e:
        s = str(e)
        if "1113" in s or "balance" in s.lower():
            return "empty", s[:80]
        return "unknown", s[:80]


def load_state():
    if os.path.exists(STATE):
        try:
            with open(STATE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def detect_multi_ip(hours=24):
    """检测同一令牌被多个 IP 使用（疑似分享/泄露）
    new-api 的 logs 表有 ip 字段
    """
    cut = int(time.time()) - hours * 3600
    try:
        rows = q("""SELECT token_name, COUNT(DISTINCT ip) as n_ip, GROUP_CONCAT(DISTINCT ip) as ips,
                           COUNT(*) as calls, SUM(quota) as quota
                    FROM logs WHERE created_at > ? AND ip IS NOT NULL AND ip != ''
                    GROUP BY token_name HAVING n_ip >= ?""",
                (cut, MULTI_IP_THRESHOLD))
    except Exception:
        # logs 表可能没有 ip 字段
        return []
    out = []
    for tn, n_ip, ips, calls, quota in rows:
        out.append({"token": tn, "ips": n_ip, "ip_list": (ips or "")[:200],
                    "calls": calls, "cny": cny(quota)})
    return out


def detect_hourly_spike():
    """检测最近 1 小时单令牌消耗突增"""
    cut = int(time.time()) - 3600
    try:
        rows = q("""SELECT token_name, COUNT(*), SUM(quota) FROM logs
                    WHERE created_at > ? GROUP BY token_name""", (cut,))
    except Exception:
        return []
    out = []
    for tn, calls, quota in rows:
        c = cny(quota)
        if c > HOURLY_SPIKE_CNY:
            out.append({"token": tn, "calls": calls, "cny": round(c, 3)})
    return out


def token_breakdown(seconds=6 * 3600):
    """最近 N 秒按 token 分的消耗（区分测试/客户）"""
    cut = int(time.time()) - seconds
    try:
        rows = q("SELECT token_name, COUNT(*), SUM(quota) FROM logs WHERE created_at > ? GROUP BY token_name", (cut,))
    except Exception:
        return [], []
    client, test = [], []
    for tn, n, qq in rows:
        item = {"token": tn or "(未知)", "calls": n, "quota": qq or 0, "cny": cny(qq)}
        (test if is_test_token(tn) else client).append(item)
    return client, test


def parse_args():
    """--topup N 登记区间内充值额。返回 (as_json, topup)"""
    as_json = "--json" in sys.argv
    topup = 0.0
    chan = "deepseek"
    for i, a in enumerate(sys.argv):
        if a == "--topup" and i + 1 < len(sys.argv):
            try:
                topup = float(sys.argv[i + 1])
            except ValueError:
                sys.stderr.write("--topup 需要一个数字\n")
        elif a.startswith("--topup="):
            try:
                topup = float(a.split("=", 1)[1])
            except ValueError:
                sys.stderr.write("--topup= 需要一个数字\n")
        elif a == "--topup-channel" and i + 1 < len(sys.argv):
            chan = sys.argv[i + 1]
        elif a.startswith("--topup-channel="):
            chan = a.split("=", 1)[1]
    return as_json, topup, chan


def main():
    global FORCED_TOPUP, TOPUP_CHANNEL
    as_json, topup, chan = parse_args()
    FORCED_TOPUP = topup
    TOPUP_CHANNEL = chan
    state = load_state()
    now = int(time.time())
    out = {"ts": now, "channels": [], "alerts": [], "warns": []}

    for cid, name, key, status, used, bal in q(
            "SELECT id, name, key, status, used_quota, balance FROM channels ORDER BY id"):
        rec = {"id": cid, "name": name, "status": status,
               "used_quota": used or 0, "quota_cny": round(cny(used), 4)}
        key = (key or "").strip().split(chr(10))[0].strip()

        # 余额（二次校验用）
        detail = None
        if name == "deepseek":
            detail, note = deepseek_balance(key)
            b = detail["total"] if detail else None
        elif name == "moonshot-kimi":
            b, note = moonshot_balance(key)
        elif name == "zhipu-glm":
            st_, note = zhipu_check(key)
            b = None
            rec["probe"] = st_
        else:
            b, note = None, "skip"
        rec["balance"] = b
        rec["note"] = note
        if detail:
            rec["topped_up"] = detail["topped_up"]
            rec["granted"] = detail["granted"]

        prev = state.get(name, {})
        prev_used = prev.get("used_quota")
        prev_bal = prev.get("balance")
        prev_topup = prev.get("topped_up")

        # ---- 主指标：quota 增量（实时）----
        if prev_used is not None and used is not None and used >= prev_used:
            d_quota = used - prev_used
            rec["delta_quota"] = d_quota
            rec["delta_cny"] = round(cny(d_quota), 4)

        # ---- 余额差：只做「区间内有没有充值」的判据，不当消耗 ----
        # 铁律：余额 API 没有「充值流水」接口，无法分离充值额与消耗额。
        # 唯一可靠的消耗口径是网关 used_quota（我们的 app 走网关）。
        topup_in_window = None
        if detail and prev_topup is not None:
            tp_delta = round(detail["topped_up"] - prev_topup, 4)
            if tp_delta > 0.01:
                topup_in_window = tp_delta
                rec["topup_in_window"] = tp_delta
        if FORCED_TOPUP and name == TOPUP_CHANNEL:
            topup_in_window = (topup_in_window or 0) + FORCED_TOPUP
            rec["topup_in_window"] = round(topup_in_window, 4)

        if b is not None and prev_bal is not None:
            net = round(b - prev_bal, 4)
            rec["balance_net"] = net
            # 余额没涨 => 区间内没有充值，消耗 = -net，可直接算
            if topup_in_window is None and net <= 0.01:
                topup_in_window = 0.0
                rec["topup_in_window"] = 0.0
            # 区间真实消耗 = 旧余额 + 充值 - 新余额
            if topup_in_window is not None:
                burn = round(prev_bal + topup_in_window - b, 4)
                rec["burn"] = burn
                gw = rec.get("delta_cny")
                if gw is not None:
                    rec["off_gateway"] = round(burn - gw, 4)
                    if burn > 0.01 and abs(burn - gw) > max(0.5, gw * 0.2):
                        out["warns"].append(
                            "[口径分离] %s 区间实耗 ¥%.2f（含充值 ¥%.2f），"
                            "网关记 ¥%.4f，差额 ¥%.2f 不经本网关（openclaw/直连）"
                            % (name, burn, topup_in_window, gw, burn - gw))
            elif net > 0.01:
                out["warns"].append(
                    "[区间含充值] %s 余额净增 ¥%.2f，未登记充值额，"
                    "本区间消耗不可计算——用 --topup N 登记" % (name, net))

        # ---- 余额告警（真·不足）----
        if b is not None and b < LOW_BALANCE_CNY:
            out["alerts"].append("[余额低] %s 剩 %.2f 元 < %.0f" % (name, b, LOW_BALANCE_CNY))
        if rec.get("probe") == "empty":
            out["alerts"].append("[余额空] %s 探测返回余额不足" % name)

        state[name] = {"balance": b, "used_quota": used, "ts": now}
        if detail:
            state[name]["topped_up"] = detail["topped_up"]
            state[name]["granted"] = detail["granted"]
        out["channels"].append(rec)

    # ---- 多 IP 检测（防 key 分享）----
    multi_ip = detect_multi_ip()
    out["multi_ip"] = multi_ip
    for m in multi_ip:
        out["alerts"].append(
            "[多IP] %s 被 %d 个 IP 使用（%d 次，¥%.2f）—— 疑似 key 分享/泄露"
            % (m["token"], m["ips"], m["calls"], m["cny"]))

    # ---- 小时消耗突增 ----
    spikes = detect_hourly_spike()
    out["hourly_spikes"] = spikes
    for s in spikes:
        out["alerts"].append(
            "[突增] %s 最近 1 小时 %d 次调用 ¥%.2f > %.0f —— 检查是否被盗刷"
            % (s["token"], s["calls"], s["cny"], HOURLY_SPIKE_CNY))

    # ---- 按 token 区分测试/客户 ----
    client, test = token_breakdown()
    out["client_usage"] = client
    out["test_usage"] = test

    save_state(state)

    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print("=== 渠道状态 ===")
    for c in out["channels"]:
        b = "%9.2f 元" % c["balance"] if c.get("balance") is not None else "  查不到  "
        d = ""
        if c.get("delta_cny") is not None:
            d = " | 网关记 ¥%.4f（本 app 消耗）" % c["delta_cny"]
        print("  [%d] %-16s 状态=%d 余额=%s%s" % (c["id"], c["name"], c["status"], b, d))
        if c.get("topped_up") is not None:
            print("       余额构成：充值 %.2f + 赠送 %.2f"
                  % (c["topped_up"], c.get("granted") or 0))
        if c.get("burn") is not None:
            print("       区间实耗 ¥%.4f（= 旧余额 %.2f + 充值 %.2f - 现余额 %.2f）"
                  % (c["burn"], c["balance"] + c["burn"] - c["topup_in_window"],
                     c["topup_in_window"], c["balance"]))
            if c.get("off_gateway") is not None:
                print("         其中不经网关 ¥%.4f（openclaw / 直连，非本 app）"
                      % c["off_gateway"])
        elif c.get("balance_net") is not None:
            print("       余额净变 %+.4f 元（%s）"
                  % (c["balance_net"],
                     "涨=有充值" if c["balance_net"] > 0 else "降=有消耗，但未登记充值"))

    print()
    print("=== 最近 6 小时消耗（按 token）===")
    if client:
        print("  客户：")
        for x in client:
            print("    %-30s %3d 次  ¥%.4f" % (x["token"][:30], x["calls"], x["cny"]))
    if test:
        print("  测试（不计入毛利）：")
        for x in test:
            print("    %-30s %3d 次  ¥%.4f" % (x["token"][:30], x["calls"], x["cny"]))
    if not client and not test:
        print("  无调用")

    print()
    if out["alerts"]:
        print("=== 告警 ===")
        for a in out["alerts"]:
            print("  " + a)
    else:
        print("=== 无告警 ===")
    if out["warns"]:
        print("=== 提示 ===")
        for w in out["warns"]:
            print("  " + w)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        while True:
            main()
            print(chr(10) + "[%s] 下次检查 6 小时后" % time.strftime("%H:%M:%S"))
            time.sleep(6 * 3600)
    else:
        main()