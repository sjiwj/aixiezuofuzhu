# -*- coding: utf-8 -*-
"""灵石账本（Ling ledger）——复刻自 lianzigongfang.com 的计费结构

还原依据：docs/竞品-炼字-复刻清单.md 与 知识/领域/AI写作竞品/02-炼字工坊-逆向.md
三件事必须和对方一致：
  1. 余额分三段：daily（每日补满，过期作废）/ bonus（活动）/ permanent（充值）
  2. 扣费顺序：daily -> bonus -> permanent
  3. 计价按「每千字、输入输出分别计价、各自向上取整」，不是按 token

与炼字不同的地方（有意为之）：
  - 结算用「先全额退还预扣，再按实际重扣」，避免部分输出时算错分段；对方是就地差额补偿。
  - 模型表来自 config/lianzi_models.json（2026-11-11 从公开 /api/ai/models 抓取）。

用法：
  python core/ling.py --selftest            # 自检 12 条断言
  python core/ling.py --balance u1          # 看余额
  python core/ling.py --grant u1 10000      # 充值（permanent）
  python core/ling.py --quote gemini-4-carbon-high 3000 5000
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CFG_PATH = os.path.join(ROOT, "config", "lianzi_models.json")
DB_PATH = os.path.join(ROOT, "data", "ling", "ling.db")

BJ = timezone(timedelta(hours=8))

# 每日额度（炼字：free 2000 / basic 8000 / platinum 16000 / max 30000）
TIER_DAILY = {"free": 2000, "basic": 8000, "platinum": 16000, "max": 30000}
# 渠道前缀 -> 上游（炼字的 yD() 映射，原样照抄）
CHANNELS = {
    "channela": "grsai",
    "official": "yunwu",
    "channelb": "openlux",
    "ark": "ark",
    "grsai": "grsai",
    "yunwu": "yunwu",
    "openlux": "openlux",
}
INVITE_REWARD = 2000
MIN_CHARGE = 1


class LingError(Exception):
    def __init__(self, code: str, msg: str = ""):
        super().__init__(msg or code)
        self.code = code


def load_catalog(path: str = CFG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_model(spec: str, channels: dict | None = None):
    """'official:gemini-4-carbon-high' -> ('yunwu', 'gemini-4-carbon-high')"""
    ch = channels or CHANNELS
    raw = str(spec or "").strip()
    if ":" not in raw:
        return None, raw
    head, tail = raw.split(":", 1)
    head, tail = head.strip().lower(), tail.strip()
    if head in ch and tail:
        return ch[head], tail
    return None, raw


def ceil_charge(chars: int, price_per_k: float) -> int:
    n = max(0, int(chars or 0))
    if not n or not price_per_k:
        return 0
    return int(math.ceil(n / 1000.0 * float(price_per_k)))


class Ling:
    def __init__(self, db_path: str = DB_PATH, catalog: dict | None = None):
        self.db_path = db_path
        self.catalog = catalog or load_catalog()
        self.by_name = {m["name"]: m for m in self.catalog.get("models", [])}
        self.channels = self.catalog.get("channels") or CHANNELS
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init()

    # ---------- storage ----------
    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init(self):
        with self._db() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts(
                  uid TEXT PRIMARY KEY, tier TEXT NOT NULL DEFAULT 'free',
                  daily INTEGER NOT NULL DEFAULT 0, bonus INTEGER NOT NULL DEFAULT 0,
                  permanent INTEGER NOT NULL DEFAULT 0, reset_on TEXT NOT NULL DEFAULT '',
                  inviter TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS usage(
                  id TEXT PRIMARY KEY, uid TEXT NOT NULL, model TEXT NOT NULL,
                  in_chars INTEGER NOT NULL, out_chars INTEGER NOT NULL DEFAULT 0,
                  reserved INTEGER NOT NULL, charged INTEGER NOT NULL DEFAULT 0,
                  deduct TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'pending',
                  ts TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ledger(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL, kind TEXT NOT NULL,
                  amount INTEGER NOT NULL, bucket TEXT NOT NULL, ref TEXT, model TEXT, ts TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_ledger_uid ON ledger(uid, ts);
                """
            )

    # ---------- helpers ----------
    @staticmethod
    def _today(now: datetime | None = None) -> str:
        return (now or datetime.now(BJ)).strftime("%Y-%m-%d")

    def _ensure(self, c, uid: str, tier: str = "free", now: datetime | None = None):
        row = c.execute("SELECT * FROM accounts WHERE uid=?", (uid,)).fetchone()
        if row:
            return row
        c.execute(
            "INSERT INTO accounts(uid,tier,daily,bonus,permanent,reset_on,created_at) VALUES(?,?,?,?,?,?,?)",
            (uid, tier, TIER_DAILY.get(tier, 2000), 0, 0, self._today(now), datetime.now(BJ).isoformat(timespec="seconds")),
        )
        return c.execute("SELECT * FROM accounts WHERE uid=?", (uid,)).fetchone()

    def _reset_if_needed(self, c, uid: str, now: datetime | None = None):
        r = self._ensure(c, uid, now=now)
        today = self._today(now)
        if r["reset_on"] != today:
            grant = TIER_DAILY.get(r["tier"], 2000)
            c.execute("UPDATE accounts SET daily=?, reset_on=? WHERE uid=?", (grant, today, uid))
            return True
        return False

    def _charge(self, c, uid: str, amount: int, model: str, ref: str) -> dict:
        """按 daily -> bonus -> permanent 扣，返回每段扣了多少"""
        r = self._ensure(c, uid)
        remain = int(amount)
        out = {"daily": 0, "bonus": 0, "permanent": 0}
        for bucket in ("daily", "bonus", "permanent"):
            if remain <= 0:
                break
            have = int(r[bucket])
            take = min(have, remain)
            if take:
                c.execute("UPDATE accounts SET %s=%s-? WHERE uid=?" % (bucket, bucket), (take, uid))
                out[bucket] = take
                remain -= take
        if remain > 0:
            for b, v in out.items():
                if v:
                    c.execute("UPDATE accounts SET %s=%s+? WHERE uid=?" % (b, b), (v, uid))
            raise LingError("INSUFFICIENT", "余额不足：还需 %d 灵石" % remain)
        c.execute(
            "INSERT INTO ledger(uid,kind,amount,bucket,ref,model,ts) VALUES(?,?,?,?,?,?,?)",
            (uid, "charge", -int(amount), json.dumps(out), ref, model, datetime.now(BJ).isoformat(timespec="seconds")),
        )
        return out

    def _restore(self, c, uid: str, deduct: dict, ref: str | None = None):
        for bucket in ("daily", "bonus", "permanent"):
            v = int((deduct or {}).get(bucket) or 0)
            if v:
                c.execute("UPDATE accounts SET %s=%s+? WHERE uid=?" % (bucket, bucket), (v, uid))
        c.execute(
            "INSERT INTO ledger(uid,kind,amount,bucket,ref,ts) VALUES(?,?,?,?,?,?)",
            (uid, "refund", sum(int((deduct or {}).get(b) or 0) for b in ("daily", "bonus", "permanent")), json.dumps(deduct or {}), ref, datetime.now(BJ).isoformat(timespec="seconds")),
        )

    # ---------- public ----------
    def quote(self, model: str, in_chars: int, out_chars: int):
        _, name = parse_model(model, self.channels)
        m = self.by_name.get(name)
        known = bool(m)
        ip = float(m["inputLingPerKChar"]) if known else 90.0
        op = float(m["outputLingPerKChar"]) if known else 270.0
        a, b = ceil_charge(in_chars, ip), ceil_charge(out_chars, op)
        total = a + b
        if total and total < MIN_CHARGE:
            total = MIN_CHARGE
        return {
            "model": name, "known": known, "in_price": ip, "out_price": op,
            "in_ling": a, "out_ling": b, "total": total,
        }

    def balance(self, uid: str, now: datetime | None = None) -> dict:
        with self._db() as c:
            self._reset_if_needed(c, uid, now)
            r = self._ensure(c, uid)
            d, b, p = int(r["daily"]), int(r["bonus"]), int(r["permanent"])
            return {"uid": uid, "tier": r["tier"], "daily": d, "bonus": b, "permanent": p, "total": d + b + p}

    def reserve(self, uid: str, model: str, in_chars: int, out_chars_est: int, now: datetime | None = None) -> dict:
        q = self.quote(model, in_chars, out_chars_est)
        with self._db() as c:
            self._reset_if_needed(c, uid, now)
            self._ensure(c, uid)
            uid_use = uuid.uuid4().hex
            deduct = self._charge(c, uid, q["total"], q["model"], uid_use)
            c.execute(
                "INSERT INTO usage(id,uid,model,in_chars,out_chars,reserved,charged,deduct,status,ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (uid_use, uid, q["model"], int(in_chars), 0, q["total"], 0, json.dumps(deduct), "pending",
                 datetime.now(BJ).isoformat(timespec="seconds")),
            )
            return {"usage_id": uid_use, **q}

    def commit(self, usage_id: str, out_chars: int, now: datetime | None = None) -> dict:
        with self._db() as c:
            u = c.execute("SELECT * FROM usage WHERE id=?", (usage_id,)).fetchone()
            if not u:
                raise LingError("NOT_FOUND", "无此调用记录")
            if u["status"] != "pending":
                raise LingError("BAD_STATE", "该调用已结算：%s" % u["status"])
            deduct = json.loads(u["deduct"] or "{}")
            self._restore(c, u["uid"], deduct, usage_id)
            q = self.quote(u["model"], u["in_chars"], out_chars)
            actual_deduct = self._charge(c, u["uid"], q["total"], u["model"], usage_id)
            c.execute(
                "UPDATE usage SET out_chars=?, charged=?, deduct=?, status='committed' WHERE id=?",
                (int(out_chars), q["total"], json.dumps(actual_deduct), usage_id),
            )
            return {"usage_id": usage_id, "reserved": u["reserved"], "charged": q["total"],
                    "refunded": int(u["reserved"]) - q["total"]}

    def refund(self, usage_id: str) -> dict:
        with self._db() as c:
            u = c.execute("SELECT * FROM usage WHERE id=?", (usage_id,)).fetchone()
            if not u:
                raise LingError("NOT_FOUND", "无此调用记录")
            if u["status"] != "pending":
                raise LingError("BAD_STATE", "该调用已结算：%s" % u["status"])
            self._restore(c, u["uid"], json.loads(u["deduct"] or "{}"), usage_id)
            c.execute("UPDATE usage SET status='refunded' WHERE id=?", (usage_id,))
            return {"usage_id": usage_id, "refunded": int(u["reserved"])}

    def grant(self, uid: str, amount: int, bucket: str = "permanent", kind: str = "grant") -> dict:
        if bucket not in ("daily", "bonus", "permanent"):
            raise LingError("BAD_BUCKET", bucket)
        with self._db() as c:
            self._ensure(c, uid)
            c.execute("UPDATE accounts SET %s=%s+? WHERE uid=?" % (bucket, bucket), (int(amount), uid))
            c.execute("INSERT INTO ledger(uid,kind,amount,bucket,ts) VALUES(?,?,?,?,?)",
                      (uid, kind, int(amount), bucket, datetime.now(BJ).isoformat(timespec="seconds")))
            return {"uid": uid, "bucket": bucket, "amount": int(amount)}

    def invite(self, inviter: str, invitee: str, reward: int = INVITE_REWARD) -> dict:
        """邀请注册：双方加权（炼字是注册方 +2000，邀请方走 affiliate 返佣，这里两边都给）"""
        with self._db() as c:
            self._ensure(c, invitee)
            row = c.execute("SELECT inviter FROM accounts WHERE uid=?", (invitee,)).fetchone()
            if row and row["inviter"]:
                raise LingError("ALREADY_BOUND", "该用户已绑定邀请人")
            c.execute("UPDATE accounts SET inviter=? WHERE uid=?", (inviter, invitee))
            for uid, kind in ((invitee, "invite_new"), (inviter, "invite_referrer")):
                self._ensure(c, uid)
                c.execute("UPDATE accounts SET bonus=bonus+? WHERE uid=?", (reward, uid))
                c.execute("INSERT INTO ledger(uid,kind,amount,bucket,ts) VALUES(?,?,?,?,?)",
                          (uid, kind, reward, "bonus", datetime.now(BJ).isoformat(timespec="seconds")))
            return {"inviter": inviter, "invitee": invitee, "reward": reward}

    def set_tier(self, uid: str, tier: str):
        if tier not in TIER_DAILY:
            raise LingError("BAD_TIER", tier)
        with self._db() as c:
            self._ensure(c, uid)
            c.execute("UPDATE accounts SET tier=?, daily=? WHERE uid=?", (tier, TIER_DAILY[tier], uid))
            return {"uid": uid, "tier": tier}

    def statement(self, uid: str, limit: int = 20):
        with self._db() as c:
            rows = c.execute("SELECT kind,amount,bucket,model,ts FROM ledger WHERE uid=? ORDER BY id DESC LIMIT ?",
                             (uid, limit)).fetchall()
            return [dict(r) for r in rows]


# ---------------- selftest ----------------
def selftest() -> int:
    import tempfile
    tmp = tempfile.mkdtemp(prefix="ling_test_")
    L = Ling(os.path.join(tmp, "t.db"))
    ok, fail = [], []

    def check(name, cond, extra=""):
        (ok if cond else fail).append(name)
        print(("  PASS " if cond else "  FAIL ") + name + ((" | " + str(extra)) if extra else ""))

    # 1 渠道解析
    ch, name = parse_model("channela:grok-4.7")
    check("parse channela->grsai", (ch, name) == ("grsai", "grok-4.7"), (ch, name))
    ch, name = parse_model("official:gemini-4-carbon-high")
    check("parse official->yunwu", (ch, name) == ("yunwu", "gemini-4-carbon-high"), (ch, name))
    ch, name = parse_model("gemini-3-flash")
    check("parse 无前缀", (ch, name) == (None, "gemini-3-flash"))

    # 2 计价：1000 入 + 1000 出 = 60+270
    q = L.quote("gemini-4-carbon-high", 1000, 1000)
    check("quote 1000/1000 = 330", q["total"] == 330, q)
    # 3 向上取整：999 入 -> 60；1 出 -> 1
    q = L.quote("gemini-4-carbon-high", 999, 1)
    check("ceil 999->60 + 1->1 = 61", q["total"] == 61, q)
    # 4 未知模型回落
    q = L.quote("no-such-model", 1000, 1000)
    check("未知模型回落 90/270", q["total"] == 360 and not q["known"], q)

    # 5 初始日额度
    b = L.balance("u1")
    check("free 初始 daily=2000", b["daily"] == 2000 and b["total"] == 2000, b)
    # 6 预扣走 daily
    r = L.reserve("u1", "gemini-4-carbon-high", 1000, 1000)
    b = L.balance("u1")
    check("预扣后 daily=1670", b["daily"] == 1670, b)
    # 7 结算：实际 800 出 -> 60 + 216 = 276，退 54
    c = L.commit(r["usage_id"], 800)
    b = L.balance("u1")
    check("结算退差额 54", c["charged"] == 276 and c["refunded"] == 54, c)
    check("结算后 daily=1724", b["daily"] == 1724, b)
    # 8 重复结算报错
    try:
        L.commit(r["usage_id"], 10); check("重复结算应报错", False)
    except LingError as e:
        check("重复结算报错", e.code == "BAD_STATE", e.code)

    # 9 三段顺序 daily->bonus->permanent
    L2 = Ling(os.path.join(tmp, "t2.db"))
    L2.grant("u2", 0, "permanent")
    with L2._db() as c:
        L2._ensure(c, "u2")
        c.execute("UPDATE accounts SET daily=100,bonus=200,permanent=1000 WHERE uid='u2'")
    L2.reserve("u2", "gemini-4-carbon-high", 1000, 1000)  # 330
    b2 = L2.balance("u2")
    check("扣费顺序 100+200+30", (b2["daily"], b2["bonus"], b2["permanent"]) == (0, 0, 970), b2)

    # 10 余额不足回滚
    L3 = Ling(os.path.join(tmp, "t3.db"))
    with L3._db() as c:
        L3._ensure(c, "u3")
        c.execute("UPDATE accounts SET daily=10,bonus=0,permanent=0 WHERE uid='u3'")
    try:
        L3.reserve("u3", "deepseek-v4-pro", 1000, 1000); check("余额不足应报错", False)
    except LingError as e:
        check("余额不足报错", e.code == "INSUFFICIENT", e.code)
    b3 = L3.balance("u3")
    check("失败后余额未损失", (b3["daily"], b3["bonus"], b3["permanent"]) == (10, 0, 0), b3)

    # 11 退款全额
    r4 = L.reserve("u1", "gemini-3-flash", 10, 10)  # 1+1=2
    before = L.balance("u1")["daily"]
    L.refund(r4["usage_id"])
    after = L.balance("u1")["daily"]
    check("退款回原段", after == before + 2, (before, after))

    # 12 邀请 + 日额度重置 + 会员提升
    L.invite("u1", "u9")
    b9 = L.balance("u9")
    check("邀请注册方 +2000 bonus", b9["bonus"] == 2000, b9)
    try:
        L.invite("u1", "u9"); check("重复绑定应报错", False)
    except LingError as e:
        check("重复绑定报错", e.code == "ALREADY_BOUND", e.code)

    L.set_tier("u9", "platinum")
    b9 = L.balance("u9")
    check("升级 platinum daily=16000", b9["daily"] == 16000, b9)
    tomorrow = datetime.now(BJ) + timedelta(days=1)
    with L._db() as c:
        c.execute("UPDATE accounts SET daily=0 WHERE uid='u9'")
    b9 = L.balance("u9", now=tomorrow)
    check("跨日自动补满", b9["daily"] == 16000, b9)

    print("\n%d passed, %d failed" % (len(ok), len(fail)))
    return 0 if not fail else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="灵石账本")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--balance")
    ap.add_argument("--grant", nargs=2, metavar=("UID", "AMOUNT"))
    ap.add_argument("--quote", nargs=3, metavar=("MODEL", "IN_CHARS", "OUT_CHARS"))
    ap.add_argument("--statement")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    L = Ling()
    if a.balance:
        print(json.dumps(L.balance(a.balance), ensure_ascii=False, indent=2))
    if a.grant:
        print(json.dumps(L.grant(a.grant[0], int(a.grant[1])), ensure_ascii=False))
    if a.quote:
        print(json.dumps(L.quote(a.quote[0], int(a.quote[1]), int(a.quote[2])), ensure_ascii=False, indent=2))
    if a.statement:
        print(json.dumps(L.statement(a.statement), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
