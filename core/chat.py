# -*- coding: utf-8 -*-
"""对话分支（fork）· 复刻星月 /v1/ask/fork 的结构

数据模型：messages 是树，不是数组。
  {id, parent, role, content, ts, meta}
  conversation.current 指向"当前分支的叶子"，渲染 = 从叶子回溯到根。

支持：
  append（续写一条） / fork（从某条消息开新分支） / edit（改一条并保留旧分支）
  path（取到某条的分支路径） / tree（整棵树，前端画分支）
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone, timedelta

BJ = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "chat", "conversations.json")


class ChatError(Exception):
    pass


def _now():
    return datetime.now(BJ).isoformat(timespec="seconds")


def load() -> dict:
    if not os.path.isfile(DB):
        return {"conversations": {}}
    with open(DB, encoding="utf-8") as f:
        return json.load(f) or {"conversations": {}}


def save(d: dict):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    tmp = DB + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DB)


def create(title: str = "新对话") -> dict:
    d = load()
    cid = uuid.uuid4().hex[:12]
    root = {"id": uuid.uuid4().hex[:12], "parent": None, "role": "system",
            "content": "你是资深网文编辑，回答简短、可执行。", "ts": _now()}
    d["conversations"][cid] = {"id": cid, "title": title, "created": _now(),
                               "messages": [root], "current": root["id"]}
    save(d)
    return d["conversations"][cid]


def get(cid: str) -> dict:
    c = load()["conversations"].get(cid)
    if not c:
        raise ChatError("conversation not found")
    return c


def _put(c: dict):
    d = load()
    d["conversations"][c["id"]] = c
    save(d)


def append(cid: str, role: str, content: str, parent: str | None = None) -> dict:
    c = get(cid)
    pid = parent or c["current"]
    m = {"id": uuid.uuid4().hex[:12], "parent": pid, "role": role, "content": content, "ts": _now()}
    c["messages"].append(m)
    c["current"] = m["id"]
    _put(c)
    return m


def fork(cid: str, message_id: str, content: str, role: str = "user") -> dict:
    """从某条消息之后开新分支：新消息的 parent = 该消息"""
    c = get(cid)
    ids = {m["id"] for m in c["messages"]}
    if message_id not in ids:
        raise ChatError("message not found")
    m = {"id": uuid.uuid4().hex[:12], "parent": message_id, "role": role,
         "content": content, "ts": _now(), "meta": {"fork_of": message_id}}
    c["messages"].append(m)
    c["current"] = m["id"]
    _put(c)
    return m


def edit(cid: str, message_id: str, content: str) -> dict:
    """改一条消息：原消息保留（旧分支活着），新消息挂同一 parent"""
    c = get(cid)
    old = next((m for m in c["messages"] if m["id"] == message_id), None)
    if not old:
        raise ChatError("message not found")
    m = {"id": uuid.uuid4().hex[:12], "parent": old["parent"], "role": old["role"],
         "content": content, "ts": _now(), "meta": {"edited_from": message_id}}
    c["messages"].append(m)
    c["current"] = m["id"]
    _put(c)
    return m


def path(cid: str, message_id: str | None = None) -> list:
    c = get(cid)
    by_id = {m["id"]: m for m in c["messages"]}
    cur = message_id or c["current"]
    out = []
    while cur and cur in by_id:
        out.append(by_id[cur])
        cur = by_id[cur]["parent"]
    return list(reversed(out))


def tree(cid: str) -> dict:
    c = get(cid)
    children = {}
    for m in c["messages"]:
        children.setdefault(m["parent"], []).append(m["id"])
    return {"id": c["id"], "title": c["title"], "current": c["current"],
            "messages": c["messages"], "children": children}


def switch(cid: str, message_id: str) -> dict:
    c = get(cid)
    if not any(m["id"] == message_id for m in c["messages"]):
        raise ChatError("message not found")
    c["current"] = message_id
    _put(c)
    return {"current": message_id, "path": path(cid)}
