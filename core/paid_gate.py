# -*- coding: utf-8 -*-
"""付费闸 + 本地账本（append-only）—— 获利开关，不是功能。

设计原则（对账优先）：
  1. 账本只追加，不改不删。退款 = 一条负数反向分录。
  2. balance() 每次从账本行重算，不读任何缓存/派生余额。
     行里的 balance_after / quota_after 只是「落笔那一刻的审计快照」，
     用 status()['audit'] 校验它与重算值是否一致；不一致立即报警。
  3. 幂等：同一 ref 的 topup / refund 第二次调用返回 duplicate=True 且不落行。
  4. 不存 token、不接支付渠道 —— 本模块只登记「谁付了多少、买了多少章」。
  5. 章节额度 = Σtopup.chapters − Σconsume.chapters + Σrefund.chapters（退款默认只减钱，
     整档退款时传 chapters=-N 才回冲额度）。

对外 API：
  load_cfg() / ledger_path() / read_ledger()
  check(chapter_index, chapters_done=0) -> {allow, reason, tier, remaining, ...}
  consume(n=1, tier=None, ref=None, chapter=None, usage=None, model=None)
  topup(tier, amount=None, ref=None, chapters=None)
  refund(amount, ref=None, tier=None, chapters=None)      amount 传正数，落行写 -amount
  balance() / quota() / consumed_chapters() / status() / summary() / local_usage(limit)
"""
import json
import os
import sys
import threading
import time

_LOCK = threading.Lock()

DEFAULT_CFG = {
    "mode": "free",   # 2026-11-17 开源转向：free=不计费，只记成本遥测；paid=旧付费闸
    "enabled": True,
    "free_chapters": 3,
    "tiers": {
        "day": {"price": 14.8, "chapters": 60},
        "month": {"price": 49.0, "chapters": 60},
        "year": {"price": 388.0, "chapters": 60},
    },
    "ledger": "data/billing/ledger.jsonl",
    # 无真实 usage 时用这个样本估单章成本（= genlog-真实-01.json：prompt1820/completion456
    # → 网关 deepseek-flash 口径 ¥0.00365/章）。模型名必须是网关 pricing 里的键，
    # 否则 compute_billing 的 model_ratio=0，成本会被算成 0（会虚报毛利）。
    "cost_sample": {"model": "deepseek-flash", "prompt_tokens": 1820,
                    "completion_tokens": 456},
}


def _root():
    """与 server._resolve_root 同口径：frozen 时 exe 目录，源码时 core 的上一级。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


ROOT = _root()


def _cfg_file():
    return os.path.join(ROOT, "data", "config", "billing.json")


def load_cfg():
    """读 data/config/billing.json；不存在 / 坏掉就用内置默认（绝不因配置缺失停服）。"""
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    p = _cfg_file()
    try:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k == "tiers" and isinstance(v, dict):
                    for tk, tv in v.items():
                        base = cfg["tiers"].get(tk) or {}
                        if isinstance(tv, dict):
                            merged = dict(base)
                            merged.update(tv)
                            cfg["tiers"][tk] = merged
                        else:
                            cfg["tiers"][tk] = tv
                elif k == "cost_sample" and isinstance(v, dict):
                    sample = dict(cfg["cost_sample"])
                    sample.update(v)
                    cfg["cost_sample"] = sample
                else:
                    cfg[k] = v
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return cfg


def ledger_path():
    """账本文件：NOVELAPP_BILLING_LEDGER > config.ledger（相对 ROOT）> 默认。"""
    env = (os.environ.get("NOVELAPP_BILLING_LEDGER") or "").strip()
    if env:
        return os.path.abspath(env)
    cfg = load_cfg()
    rel = str(cfg.get("ledger") or DEFAULT_CFG["ledger"])
    if os.path.isabs(rel):
        return rel
    # 2026-11-17 Lead：生产账本落数据目录（打包后安装目录可能只读、更新即覆盖）
    if not os.path.exists(_cfg_file()):
        d = _data_dir()
        if d:
            return os.path.join(d, "billing", "ledger.jsonl")
    return os.path.join(ROOT, rel)


def _data_dir():
    """数据目录：优先 coordinator.data_dir()（AppData 下的 novelapp-desktop data），失败回 None。"""
    try:
        import coordinator as CO
        return CO.data_dir()
    except Exception:
        return None


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------- 账本读写 ----------------

def read_ledger():
    """返回 (rows, bad)。坏行不参与计算、不改写文件，只计数上报。"""
    p = ledger_path()
    rows, bad = [], 0
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    bad += 1
                    continue
                if isinstance(obj, dict) and obj.get("kind"):
                    rows.append(obj)
                else:
                    bad += 1
    except FileNotFoundError:
        pass
    except OSError:
        bad += 1
    return rows, bad


def _recalc(rows):
    """唯一权威算法：金额与章节额度都从行重算。"""
    balance = 0.0
    chapters_bought = 0.0
    chapters_used = 0.0
    for r in rows:
        kind = r.get("kind")
        try:
            amount = float(r.get("amount") or 0)
            chapters = float(r.get("chapters") or 0)
        except (TypeError, ValueError):
            continue
        if kind == "topup":
            balance += amount
            chapters_bought += chapters
        elif kind == "refund":
            balance += amount          # 行里存的是负数
            chapters_bought += chapters  # 整档退款时 chapters 也是负数
        elif kind == "consume":
            chapters_used += chapters   # 正数
    return {
        "balance": round(balance, 4),
        "chapters_bought": round(chapters_bought, 4),
        "chapters_used": round(chapters_used, 4),
        "quota": round(chapters_bought - chapters_used, 4),
    }


def balance():
    rows, _ = read_ledger()
    return _recalc(rows)["balance"]


def quota():
    rows, _ = read_ledger()
    return _recalc(rows)["quota"]


def consumed_chapters():
    rows, _ = read_ledger()
    return _recalc(rows)["chapters_used"]


def _append(row):
    """追加一行。O_APPEND 单次 write，不重写历史。"""
    p = ledger_path()
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n"
    with _LOCK:
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(line)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
    return row


def _find_ref(rows, ref, kinds=("topup", "refund", "consume")):
    if not ref:
        return None
    ref = str(ref)
    for r in reversed(rows):
        if r.get("kind") in kinds and str(r.get("ref") or "") == ref:
            return r
    return None


# ---------------- 闸门 ----------------

def is_free():
    """free 模式（开源默认）：不计费、不拦截，只记 usage 用于成本透明。"""
    try:
        return str(load_cfg().get("mode") or "free") == "free"
    except Exception:
        return True


def check(chapter_index, chapters_done=0):
    if is_free():
        return {"allow": True, "reason": "free", "free_chapters": None,
                "remaining": None, "tier": "free", "balance": 0.0, "mode": "free"}
    """第 chapter_index 章能否写。

    chapters_done = 账本里已付过费的章节数（consume 累计）；用来判断「这一章已经付过、
    重跑不再扣费」。只认账本，不认任何外部计数。
    """
    cfg = load_cfg()
    free = int(cfg.get("free_chapters") or 0)
    try:
        idx = int(chapter_index or 0)
    except (TypeError, ValueError):
        idx = 0
    try:
        done = int(chapters_done or 0)
    except (TypeError, ValueError):
        done = 0
    stats = _recalc(read_ledger()[0])
    cur_quota = stats["quota"]
    tier = current_tier()
    out = {
        "allow": False,
        "reason": "need_pay",
        "tier": tier,
        "remaining": cur_quota,
        "free_chapters": free,
        "chapter": idx,
        "enabled": bool(cfg.get("enabled", True)),
        "balance": stats["balance"],
        "price": (cfg.get("tiers") or {}).get(tier or "", {}).get("price"),
    }
    if not out["enabled"]:
        out.update({"allow": True, "reason": "free", "note": "billing disabled"})
        return out
    if idx and idx <= free:
        out.update({"allow": True, "reason": "free"})
        return out
    if idx and idx <= done:            # 这一章已经付过费（重跑）
        out.update({"allow": True, "reason": "paid", "note": "already_paid"})
        return out
    if cur_quota >= 1:
        out.update({"allow": True, "reason": "paid"})
        return out
    return out


def current_tier():
    """最近一次有效 topup 的档位（退款不改变「曾经买过什么」）。"""
    rows, _ = read_ledger()
    for r in reversed(rows):
        if r.get("kind") == "topup" and r.get("tier"):
            return r.get("tier")
    return None


# ---------------- 记账 ----------------

def topup(tier, amount=None, ref=None, chapters=None):
    if is_free():
        return {"ok": False, "error": "free_mode", "hint": "开源版不计费，没有充值与退款接口"}
    """登记一笔充值。同 ref 第二次调用返回 duplicate=True 且不加账。"""
    cfg = load_cfg()
    tiers = cfg.get("tiers") or {}
    if tier is None or str(tier) not in tiers:
        return {"ok": False, "error": "unknown_tier",
                "hint": "可用档位：%s" % ", ".join(sorted(tiers)),
                "tiers": tiers}
    tier = str(tier)
    ref = (str(ref).strip() if ref is not None else "")
    if not ref:
        return {"ok": False, "error": "ref_required",
                "hint": "ref 是对账主键（同一笔只能入一次），必填"}
    meta = tiers[tier]
    try:
        amt = float(meta.get("price") if amount is None else amount)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_amount"}
    if amt <= 0:
        return {"ok": False, "error": "bad_amount", "hint": "金额必须 > 0"}
    try:
        chs = float(meta.get("chapters") or 0) if chapters is None else float(chapters)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_chapters"}
    if chs < 0:
        return {"ok": False, "error": "bad_chapters"}

    rows, _ = read_ledger()
    dup = _find_ref(rows, ref)
    if dup is not None:
        stats = _recalc(rows)
        return {"ok": True, "duplicate": True, "ref": ref, "tier": dup.get("tier"),
                "amount": dup.get("amount"), "chapters": dup.get("chapters"),
                "balance": stats["balance"], "remaining": stats["quota"],
                "row": dup, "ledger": ledger_path(),
                "note": "同一 ref 已入账，本次未加账"}

    stats = _recalc(rows)
    row = {
        "ts": _now(),
        "kind": "topup",
        "tier": tier,
        "amount": round(amt, 4),
        "chapters": round(chs, 4),
        "ref": ref,
        "balance_after": round(stats["balance"] + amt, 4),
        "quota_after": round(stats["quota"] + chs, 4),
    }
    _append(row)
    stats = _recalc(read_ledger()[0])
    return {"ok": True, "duplicate": False, "ref": ref, "tier": tier,
            "amount": row["amount"], "chapters": row["chapters"],
            "balance": stats["balance"], "remaining": stats["quota"],
            "row": row, "ledger": ledger_path()}


def refund(amount, ref=None, tier=None, chapters=None):
    if is_free():
        return {"ok": False, "error": "free_mode", "hint": "开源版不计费，没有充值与退款接口"}
    """退款：只追加负数分录。amount 传正数（落行 -amount）。

    chapters 传正数表示同时回冲的章节额度（落行取负）。超退（余额变负）拒绝。
    """
    ref = (str(ref).strip() if ref is not None else "")
    if not ref:
        return {"ok": False, "error": "ref_required"}
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_amount"}
    if amt <= 0:
        return {"ok": False, "error": "bad_amount", "hint": "退款金额传正数，落行自动为负"}
    pro_rata = False
    if chapters is None:
        # 2026-11-17 Lead：退款默认按档位折额回冲额度（退钱同时退额度，才对得上"未用额度可退"）
        _t = tier or current_tier()
        _spec = (load_cfg().get("tiers") or {}).get(_t) or {}
        try:
            _price = float(_spec.get("price") or 0)
            _per = float(_spec.get("chapters") or 0)
        except (TypeError, ValueError):
            _price = _per = 0
        if _price > 0 and _per > 0:
            chapters = round(amt / (_price / _per), 4)
            pro_rata = True
    try:
        chs = float(chapters) if chapters is not None else 0.0
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_chapters"}
    if chs < 0:
        return {"ok": False, "error": "bad_chapters", "hint": "chapters 传正数，回冲时取负"}

    rows, _ = read_ledger()
    dup = _find_ref(rows, ref, kinds=("refund",))
    if dup is not None:
        stats = _recalc(rows)
        return {"ok": True, "duplicate": True, "ref": ref, "amount": dup.get("amount"),
                "balance": stats["balance"], "remaining": stats["quota"],
                "row": dup, "ledger": ledger_path(),
                "note": "同一 ref 已退款，本次未加账"}
    stats = _recalc(rows)
    if amt > stats["balance"] + 1e-9:
        return {"ok": False, "error": "insufficient_balance",
                "balance": stats["balance"], "asked": amt,
                "hint": "退款不能超过账本余额（防超退）"}
    row = {
        "ts": _now(),
        "kind": "refund",
        "tier": tier or current_tier(),
        "amount": round(-amt, 4),
        "chapters": round(-chs, 4) if chs else 0.0,
        "pro_rata": pro_rata,
        "ref": ref,
        "balance_after": round(stats["balance"] - amt, 4),
        "quota_after": round(stats["quota"] - chs, 4),
    }
    _append(row)
    stats = _recalc(read_ledger()[0])
    out = {"ok": True, "duplicate": False, "ref": ref, "amount": row["amount"],
           "balance": stats["balance"], "remaining": stats["quota"],
           "chapters_reversed": row["chapters"], "row": row, "ledger": ledger_path()}
    if not chs:
        # 只退钱不退额度 = 钱退了章还能写。整档退款必须显式传 chapters=n 回冲。
        out["warn"] = ("本次只冲金额、未回冲章节额度（remaining 仍 %s）；"
                       "整档退款请传 chapters=n" % stats["quota"])
        out["quota_unchanged"] = True
    return out


def consume(n=1, tier=None, ref=None, chapter=None, usage=None, model=None):
    if is_free():
        row = {"ts": _now(), "kind": "usage", "chapters": 0.0, "amount": 0.0,
               "tier": "free", "ref": ref, "chapter": chapter,
               "model": model, "usage": usage or {}, "free": True}
        _append(row)
        return {"ok": True, "free": True, "row": row, "ledger": ledger_path()}
    """扣一章（写章成功后调用）。同 ref 第二次返回 duplicate=True 且不扣。"""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_n"}
    if n <= 0:
        return {"ok": False, "error": "bad_n"}
    ref = (str(ref).strip() if ref is not None else "")
    rows, _ = read_ledger()
    if ref:
        dup = _find_ref(rows, ref, kinds=("consume",))
        if dup is not None:
            stats = _recalc(rows)
            return {"ok": True, "duplicate": True, "ref": ref,
                    "chapters": dup.get("chapters"), "balance": stats["balance"],
                    "remaining": stats["quota"], "row": dup,
                    "ledger": ledger_path()}
    stats = _recalc(rows)
    row = {
        "ts": _now(),
        "kind": "consume",
        "chapters": round(n, 4),
        "tier": tier or current_tier(),
        "ref": ref or None,
        "chapter": chapter,
        "model": model,
        "usage": usage if isinstance(usage, dict) else None,
        "balance_after": round(stats["balance"], 4),
        "quota_after": round(stats["quota"] - n, 4),
    }
    _append(row)
    stats = _recalc(read_ledger()[0])
    return {"ok": True, "duplicate": False, "ref": ref or None,
            "chapters": row["chapters"], "balance": stats["balance"],
            "remaining": stats["quota"], "row": row, "ledger": ledger_path()}


# ---------------- 汇总 / 状态 ----------------

_PRICING_CACHE = {"at": 0.0, "val": None}


def _pricing():
    """网关定价（compute_billing 口径）。取不到就返回 None，由调用方退化估算。"""
    now = time.time()
    if _PRICING_CACHE["val"] is not None and now - _PRICING_CACHE["at"] < 60:
        return _PRICING_CACHE["val"]
    try:
        sys.path.insert(0, os.path.join(ROOT, "core"))
        import coordinator as CO
        p = CO.gateway_pricing()
        if isinstance(p, dict) and p.get("models"):
            _PRICING_CACHE.update({"at": now, "val": p})
            return p
    except Exception:
        pass
    return None


def _cost_of(row, cfg):
    """一行 consume 的真实成本：有 usage 走 compute_billing，没有就用样本估。"""
    sample = cfg.get("cost_sample") or {}
    usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
    model = row.get("model") or sample.get("model") or ""
    u = {
        "prompt_tokens": int(usage.get("prompt_tokens") or sample.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or sample.get("completion_tokens") or 0),
    }
    if usage.get("total_tokens"):
        u["total_tokens"] = int(usage["total_tokens"])
    try:
        sys.path.insert(0, os.path.join(ROOT, "core"))
        import coordinator as CO
        b = CO.compute_billing(model, u, g=CO.gateway_cfg(), pricing=_pricing())
        return float(b.get("total_cny") or 0.0), "compute_billing", b
    except Exception:
        return 0.0, "unavailable", None


def summary(month=None):
    """本月（或指定 YYYY-MM）账单：收入 / 消耗章节 / 成本 / 预估毛利。"""
    cfg = load_cfg()
    month = month or time.strftime("%Y-%m")
    rows, bad = read_ledger()
    picked = [r for r in rows if str(r.get("ts") or "").startswith(month)]
    stats = _recalc(rows)
    topup_cny = sum(float(r.get("amount") or 0) for r in picked if r.get("kind") == "topup")
    refund_cny = sum(float(r.get("amount") or 0) for r in picked if r.get("kind") == "refund")
    consumes = [r for r in picked if r.get("kind") == "consume"]
    chapters_used = sum(float(r.get("chapters") or 0) for r in consumes)
    cost, basis, one = 0.0, "compute_billing", None
    for r in consumes:
        c, b, raw = _cost_of(r, cfg)
        cost += c
        basis = b
        if raw is not None and one is None:
            one = raw
    revenue = round(topup_cny + refund_cny, 4)
    sample_cost, _, sample_one = _cost_of({"usage": None, "model": None}, cfg)
    return {
        "month": month,
        "topup_cny": round(topup_cny, 4),
        "refund_cny": round(refund_cny, 4),
        "revenue_cny": revenue,
        "chapters_consumed": chapters_used,
        "cost_cny": round(cost, 6),
        "gross_cny": round(revenue - cost, 6),
        "unit_cost_cny": round((cost / chapters_used) if chapters_used else sample_cost, 6),
        "sample_unit_cost_cny": round(sample_cost, 6),
        "cost_basis": basis,
        "fee_rate": (one or {}).get("fee_rate"),
        "total_balance": stats["balance"],
        "remaining_chapters": stats["quota"],
        "rows": len(picked),
        "bad_lines": bad,
        "note": "毛利 = 本月(充值+退款) − 本月消耗章节成本；成本按 coordinator.compute_billing 口径",
    }


def status():
    cfg = load_cfg()
    rows, bad = read_ledger()
    stats = _recalc(rows)
    last = rows[-1] if rows else None
    audit = {
        "last_row_balance_after": (last or {}).get("balance_after"),
        "recomputed_balance": stats["balance"],
        "ok": (last is None) or (
            abs(float((last or {}).get("balance_after") or 0) - stats["balance"]) < 1e-6),
        "last_row_quota_after": (last or {}).get("quota_after"),
        "recomputed_quota": stats["quota"],
    }
    free = int(cfg.get("free_chapters") or 0)
    return {
        "ok": True,
        "enabled": bool(cfg.get("enabled", True)),
        "free_chapters": free,
        "tier": current_tier(),
        "balance": stats["balance"],
        "remaining": stats["quota"],
        "chapters_bought": stats["chapters_bought"],
        "chapters_used": stats["chapters_used"],
        "next_paid_chapter": free + 1,
        "tiers": cfg.get("tiers") or {},
        "summary": summary(),
        "ledger": ledger_path(),
        "ledger_lines": len(rows),
        "bad_lines": bad,
        "audit": audit,
    }


def local_usage(limit=20):
    """本地账本口径的用量行（网关 401 时给 /api/account/usage 兜底）。"""
    try:
        limit = max(1, min(int(limit or 20), 100))
    except (TypeError, ValueError):
        limit = 20
    rows, bad = read_ledger()
    cfg = load_cfg()
    out = []
    for r in rows[-limit:]:
        kind = r.get("kind")
        cost, basis, _ = _cost_of(r, cfg) if kind == "consume" else (0.0, None, None)
        out.append({
            "time": r.get("ts"),
            "kind": kind,
            "tier": r.get("tier"),
            "ref": r.get("ref"),
            "chapter": r.get("chapter"),
            "chapters": r.get("chapters"),
            "amount_cny": r.get("amount"),
            "cost_cny": round(cost, 6) if kind == "consume" else None,
            "cost_basis": basis,
            "balance_after": r.get("balance_after"),
            "quota_after": r.get("quota_after"),
        })
    stats = _recalc(rows)
    return {"ok": True, "source": "local_ledger", "count": len(out),
            "total": len(rows), "bad_lines": bad, "usage": out,
            "balance": stats["balance"], "remaining": stats["quota"],
            "ledger": ledger_path(),
            "note": "网关不可用（R22）时的本地账本回退；金额与剩余章节均由账本行重算"}


if __name__ == "__main__":
    print(json.dumps(status(), ensure_ascii=False, indent=2))
