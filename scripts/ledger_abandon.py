# -*- coding: utf-8 -*-
"""把一条账目标成作废（伏笔 / 承诺）。

为什么需要这个（商业调研三方都说的一条）：
  诊断完只给报告 = 分析工具，留存差。
  必须紧跟一个 5 分钟能做完的动作：
    「这 5 条里，勾掉你打算放弃的」→ 标作废 → 欠债从 5 降到 2。
  这才是「急诊室」该干的：先止血，再谈疗程。

用法：
    python scripts/ledger_abandon.py --book <书名> --foreshadow F05 --foreshadow F06
    python scripts/ledger_abandon.py --book <书名> --promise P-003 --dry-run
    python scripts/ledger_abandon.py --book <书名> --list     # 列出所有可作废的
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def data_root():
    d = os.environ.get("NOVELAPP_DATA")
    if d:
        return os.path.abspath(d)
    a = os.environ.get("APPDATA")
    return os.path.join(a, "novelapp-desktop", "data") if a else os.path.join(ROOT, "data")


def read(p):
    try:
        with io.open(p, encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def front_matter(text):
    """读 --- 包住的 front matter，返回 dict（供 server 的 /api/ledger/abandonable 用）。"""
    fm = {}
    m = re.match(r"^---\s*\n([\s\S]*?)\n---", text or "")
    if not m:
        return fm
    for line in m.group(1).split(chr(10)):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def write_atomic(p, text):
    """先写 .tmp 再原子替换——今天有一次直接 open(w) 把源文件写空了。"""
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, p)


ABANDON = "作废"


def list_foreshadow(book):
    """解析 设定库/伏笔.md 的表格，返回 [{id, chapter, content, status, line}]"""
    p = os.path.join(data_root(), "projects", book, "设定库", "伏笔.md")
    text = read(p)
    if not text:
        return [], p
    rows, head = [], None
    for idx, ln in enumerate(text.split(chr(10))):
        st = ln.strip()
        if not st.startswith("|"):
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells if c):
            continue
        if head is None:
            head = cells
            continue
        if len(cells) < 4:
            continue
        rows.append({
            "id": cells[0], "chapter": cells[1], "content": cells[2], "status": cells[3],
            "cells": cells, "line": idx, "head": head,
        })
    return rows, p


def abandon_foreshadow(book, ids, dry=False):
    rows, p = list_foreshadow(book)
    if not p or not os.path.isfile(p):
        return {"ok": False, "error": "找不到 设定库/伏笔.md"}
    lines = read(p).split(chr(10))
    done, skipped, missing = [], [], []
    want = set(ids)
    for r in rows:
        if r["id"] not in want:
            continue
        want.discard(r["id"])
        if r["status"] == ABANDON:
            skipped.append(r["id"])
            continue
        cells = list(r["cells"])
        cells[3] = ABANDON
        lines[r["line"]] = "| " + " | ".join(cells) + " |"
        done.append(r["id"])
    missing = sorted(want)
    if done and not dry:
        write_atomic(p, chr(10).join(lines))
    return {"ok": True, "changed": done, "already": skipped, "not_found": missing, "dry": dry}


def promise_path(book, pid):
    d = os.path.join(data_root(), "projects", book, "设定库", "承诺")
    if not os.path.isdir(d):
        return None
    for fn in os.listdir(d):
        if not fn.endswith(".md"):
            continue
        if fn.startswith(pid + "-") or fn == pid + ".md":
            return os.path.join(d, fn)
    return None


def abandon_promise(book, ids, dry=False):
    done, skipped, missing = [], [], []
    for pid in ids:
        p = promise_path(book, pid)
        if not p:
            missing.append(pid)
            continue
        text = read(p)
        m = re.search(r"^状态:\s*(.+)$", text, re.M)
        if m and m.group(1).strip() in (ABANDON, "已兑付", "已完成", "closed", "done"):
            skipped.append(pid)
            continue
        if m:
            new = re.sub(r"^状态:\s*.+$", "状态: " + ABANDON, text, count=1, flags=re.M)
        else:
            # 没有状态字段就加在 front matter 末尾，或者文件开头
            if text.startswith("---"):
                end = text.find(chr(10) + "---", 3)
                if end > 0:
                    new = text[:end] + chr(10) + "状态: " + ABANDON + text[end:]
                else:
                    new = text
            else:
                new = "---" + chr(10) + "状态: " + ABANDON + chr(10) + "---" + chr(10) + text
        if not dry and new != text:
            write_atomic(p, new)
        done.append(pid)
    return {"ok": True, "changed": done, "already": skipped, "not_found": missing, "dry": dry}


def main():
    ap = argparse.ArgumentParser(description="把账目标成作废（伏笔/承诺）")
    ap.add_argument("--book", required=True)
    ap.add_argument("--foreshadow", action="append", default=[])
    ap.add_argument("--promise", action="append", default=[])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.list:
        rows, p = list_foreshadow(a.book)
        out = [{"id": r["id"], "chapter": r["chapter"], "content": r["content"][:30], "status": r["status"]}
               for r in rows if r["status"] not in (ABANDON, "已收")]
        print(json.dumps({"ok": True, "file": p, "items": out}, ensure_ascii=False, indent=2))
        return 0

    res = {}
    if a.foreshadow:
        res["foreshadow"] = abandon_foreshadow(a.book, a.foreshadow, a.dry_run)
    if a.promise:
        res["promise"] = abandon_promise(a.book, a.promise, a.dry_run)
    if not res:
        print("没有指定 --foreshadow 或 --promise")
        return 2

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for kind, r in res.items():
            tag = "（试运行）" if a.dry_run else ""
            print("%s%s: 改了 %s" % (kind, tag, "、".join(r["changed"]) or "无"))
            if r["already"]:
                print("  已经是作废：%s" % "、".join(r["already"]))
            if r["not_found"]:
                print("  没找到：%s" % "、".join(r["not_found"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())