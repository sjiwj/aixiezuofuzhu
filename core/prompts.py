# -*- coding: utf-8 -*-
"""提示词市场 · 复刻白梦 prompt-template 的结构（权限组/版本/评分/收藏/搜索）

条目：{id,title,category,author,version,visibility(public|private|group),groups[],tags[],
      rating:{avg,count},uses,favorites,prompt,updated}
本地种子 12 条，够跑通"搜索/评分/收藏/权限"四条链路。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone, timedelta

BJ = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "prompts", "market.json")
CATEGORIES = ["续写", "润色", "开篇", "大纲", "拆书", "审稿", "设定", "剧本"]


def _now():
    return datetime.now(BJ).isoformat(timespec="seconds")


SEED = [
    ("官方-章节续写 6.5", "续写", "炼字官方", "6.5", "承接上一章情绪，不复述前文，1500 字左右。", ["续写", "长篇"]),
    ("官方-强力去 AI 味", "润色", "炼字官方", "2.1", "取消总结句与硬连接词，长短句交错，短句占比 >30%。", ["润色", "去AI味"]),
    ("官方-黄金开篇", "开篇", "炼字官方", "3.0", "前 300 字出冲突，主角处境具体，章末留钩。", ["开篇", "钩子"]),
    ("官方-总纲生成", "大纲", "炼字官方", "1.8", "主线一句话 + 三阶段推进 + 核心矛盾。", ["大纲", "主线"]),
    ("官方-九维拆书", "拆书", "炼字官方", "1.2", "题材/人设/冲突/节奏/爽点/伏笔/对白/世界观/结尾九维打分。", ["拆书", "结构"]),
    ("官方-审稿四问", "审稿", "炼字官方", "2.0", "冲突够不够具体、爽点够不够频、人设崩没崩、章末有没有钩。", ["审稿", "质检"]),
    ("社区-番茄脑洞标题", "开篇", "疯子女", "1.4", "标题带冲突或反差意象，控制在 12–18 字。", ["标题", "番茄"]),
    ("社区-短剧分场", "剧本", "顾川", "0.9", "按 1 分钟一场切分，每场一个动作一个反转。", ["剧本", "短剧"]),
    ("社区-设定补全", "设定", "青砚", "1.1", "从一句话灵感补出世界观/势力/力量体系三层。", ["设定", "世界观"]),
    ("社区-对白口语化", "润色", "小满", "1.0", "删书面语，允许省略与停顿，每句不超过 20 字。", ["对白", "口语"]),
    ("社区-伏笔回收表", "大纲", "南枝", "1.3", "列出已埋伏笔与回收章节，标出未回收项。", ["伏笔"]),
    ("社区-女频情绪钩", "开篇", "林舟", "1.1", "前 3 段给情绪落差，读者要知道她受了什么委屈。", ["女频", "情绪"]),
]


def load() -> dict:
    if os.path.isfile(DB):
        with open(DB, encoding="utf-8") as f:
            return json.load(f) or {"items": []}
    items = []
    for i, (t, cat, author, ver, prompt, tags) in enumerate(SEED, 1):
        items.append({
            "id": "p%02d" % i, "title": t, "category": cat, "author": author, "version": ver,
            "visibility": "public", "groups": [], "tags": tags,
            "rating": {"avg": round(4.1 + (i % 9) / 10, 1), "count": 12 + i * 7},
            "uses": 100 + i * 37, "favorites": 20 + i * 5,
            "prompt": prompt, "updated": _now(),
        })
    d = {"items": items}
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return d


def save(d: dict):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def list_items(q: str = "", category: str = "", group: str = "", sort: str = "uses") -> list:
    d = load()
    items = d["items"]
    if q:
        ql = q.lower()
        items = [x for x in items if ql in (x["title"] + x["prompt"] + " ".join(x["tags"])).lower()]
    if category:
        items = [x for x in items if x["category"] == category]
    if group:
        items = [x for x in items if x["visibility"] == "public" or group in (x.get("groups") or [])]
    if sort == "rating":
        items = sorted(items, key=lambda x: -x["rating"]["avg"])
    elif sort == "new":
        items = sorted(items, key=lambda x: x["updated"], reverse=True)
    else:
        items = sorted(items, key=lambda x: -x["uses"])
    return items


def get(pid: str) -> dict:
    for x in load()["items"]:
        if x["id"] == pid:
            return x
    raise KeyError(pid)


def create(payload: dict) -> dict:
    d = load()
    it = {
        "id": "p" + uuid.uuid4().hex[:6], "title": payload.get("title") or "未命名提示词",
        "category": payload.get("category") or "续写", "author": payload.get("author") or "我",
        "version": str(payload.get("version") or "1.0"),
        "visibility": payload.get("visibility") or "private",
        "groups": payload.get("groups") or [], "tags": payload.get("tags") or [],
        "rating": {"avg": 0, "count": 0}, "uses": 0, "favorites": 0,
        "prompt": payload.get("prompt") or "", "updated": _now(),
    }
    d["items"].append(it)
    save(d)
    return it


def rate(pid: str, score: float) -> dict:
    d = load()
    for x in d["items"]:
        if x["id"] == pid:
            n, avg = x["rating"]["count"], x["rating"]["avg"]
            x["rating"]["avg"] = round((avg * n + max(0, min(5, score))) / (n + 1), 2)
            x["rating"]["count"] = n + 1
            save(d)
            return x["rating"]
    raise KeyError(pid)


def favorite(pid: str, delta: int = 1) -> dict:
    d = load()
    for x in d["items"]:
        if x["id"] == pid:
            x["favorites"] = max(0, x["favorites"] + delta)
            save(d)
            return {"favorites": x["favorites"]}
    raise KeyError(pid)
