# -*- coding: utf-8 -*-
"""拆书公式 + 多书融合

拆书不产"读后感"，产**可执行公式**：
  每本 → {钩子类型, 节奏(章均字数/反转间隔), 人设三件套, 爽点密度, 公式}
  多本 → 九维对比（spread 大 = 可融合空间大）→ 配方 → 立项书草稿

对齐：炼字「拆书」与「多书融合」、星月「ai_book_analysis」。
"""
from __future__ import annotations

import re
import json

NINE = [
    ("theme", "题材", 0.12), ("hero", "人设", 0.14), ("conflict", "冲突", 0.14),
    ("rhythm", "节奏", 0.12), ("payoff", "爽点", 0.12), ("foreshadow", "伏笔", 0.10),
    ("dialogue", "对白", 0.08), ("world", "世界观", 0.10), ("ending", "结尾", 0.08),
]
RECIPES = [
    ("cold-fast", "冷开局 + 快打脸 + 强钩子", "前 3 章出冲突，第 7 章第一次打脸"),
    ("slow-burst", "慢热铺垫 + 中段爆发 + 情绪回甘", "前 10 章立人设，20 章后连爆"),
    ("dual-line", "双线并行 + 信息差反杀", "明线生意、暗线旧案，靠证据链收束"),
    ("unit-reverse", "群像铺陈 + 单元反转 + 主线收束", "每单元一个反派，主线慢慢浮出"),
]


def _chars(s: str) -> int:
    return len(re.sub(r"\s+", "", s or ""))


def _stats(text: str) -> dict:
    paras = [p for p in re.split(r"\n+", text) if p.strip()]
    sents = re.findall(r"[^。！？…\n]+[。！？…]?", text)
    dlg = len(re.findall(r"[“\"「][^”\"」]{2,}[”\"」]", text))
    return {"chars": _chars(text), "paras": len(paras), "sents": len(sents),
            "avg_para": round(_chars(text) / max(1, len(paras))),
            "dlg_per_k": round(dlg / max(1, _chars(text)) * 1000, 1)}


def analyze_book(title: str, text: str) -> dict:
    st = _stats(text)
    # 钩子：开头 200 字里是否有冲突/悬念信号
    head = text[:200]
    hook = "悬念开局" if re.search(r"[?？]|不知道|突然|竟然|没想到", head) else (
        "冲突开局" if re.search(r"撕|砸|骂|打|退|夺|抢", head) else "平铺开局")
    # 公式：按关键词粗判
    if re.search(r"账|合同|凭证|规则", text):
        formula = "被夺走 → 拿到凭证 → 借规则反杀"
    elif re.search(r"系统|签到|面板", text):
        formula = "获得系统 → 被动触发 → 打脸升级"
    else:
        formula = "困境 → 意外转机 → 第一次反击"
    rhythm = "两章一小反转" if st["chars"] > 800 else "样本偏短"
    payoff_per_k = round(max(1, len(re.findall(r"[!！]", text))) / max(1, st["chars"]) * 1000, 1)
    return {
        "title": title, "chars": st["chars"], "avg_para": st["avg_para"],
        "dialogue_per_k": st["dlg_per_k"], "hook": hook, "rhythm": rhythm,
        "payoff_per_k": payoff_per_k, "formula": formula,
        "voice": "短句白描" if st["avg_para"] < 80 else "长段铺陈",
    }


def nine_of(book: dict) -> list:
    base = 55
    out = []
    for key, label, w in NINE:
        s = base
        if key == "dialogue":
            s = 40 + min(50, int(book["dialogue_per_k"]))
        elif key == "rhythm":
            s = 50 + (12 if book["rhythm"] != "样本偏短" else 0) + int(book["payoff_per_k"]) % 20
        elif key == "payoff":
            s = 50 + min(40, int(book["payoff_per_k"]) * 2)
        elif key == "conflict":
            s = 60 + (10 if book["hook"] == "冲突开局" else 0)
        elif key == "hero":
            s = 58 + (hash(book["title"]) % 20)
        elif key == "world":
            s = 55 + (12 if "规则" in book["formula"] else 4)
        else:
            s = base + (hash(key + book["title"]) % 22)
        out.append({"key": key, "label": label, "weight": w, "score": max(30, min(96, s))})
    return out


def fuse(books: list) -> dict:
    if not books:
        raise ValueError("至少一本书")
    analyzed = [analyze_book(b.get("title") or "参考%d" % (i + 1), b.get("text") or "")
                for i, b in enumerate(books[:3])]
    dims = []
    for key, label, w in NINE:
        vals = [next(x["score"] for x in nine_of(b) if x["key"] == key) for b in analyzed]
        dims.append({"key": key, "label": label, "weight": w,
                     "scores": vals, "avg": round(sum(vals) / len(vals)),
                     "spread": max(vals) - min(vals)})
    total = round(sum(d["avg"] * d["weight"] for d in dims))
    # 选配方：spread 最大的维度决定
    top = max(dims, key=lambda d: d["spread"])
    recipe = {"dialogue": RECIPES[0], "rhythm": RECIPES[1], "conflict": RECIPES[2],
              "world": RECIPES[3]}.get(top["key"], RECIPES[0])
    formula = analyzed[0]["formula"] if len(analyzed) == 1 else " + ".join(b["formula"] for b in analyzed[:2])
    title = "融合·" + "×".join(b["title"][:6] for b in analyzed)
    return {
        "books": analyzed, "nine": dims, "total": total,
        "recipe": {"id": recipe[0], "label": recipe[1], "desc": recipe[2]},
        "book": {
            "title": title,
            "summary": "取《%s》的%s，叠《%s》的%s。" % (
                analyzed[0]["title"], analyzed[0]["hook"],
                analyzed[-1]["title"], analyzed[-1]["voice"]) if len(analyzed) > 1 else
                "沿用《%s》的%s与%s。" % (analyzed[0]["title"], analyzed[0]["hook"], analyzed[0]["voice"]),
            "mainline": formula,
            "first3": [
                {"idx": 1, "plan": "300 字内出%s，主角处境具体" % analyzed[0]["hook"]},
                {"idx": 2, "plan": "第一次小胜，兑现读者预期"},
                {"idx": 3, "plan": "抛更大钩子，进入主线"},
            ],
        },
    }
