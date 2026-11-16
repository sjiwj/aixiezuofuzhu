# -*- coding: utf-8 -*-
"""承诺系统 —— 伏笔的升级版

设计来自 webnovel-writer（GPL-3.0，只学设计不抄代码）：
  把「伏笔、悬念、感情线、爽点预期、立旗」统一为「对读者的承诺」
  每条一个文件，front matter 六字段，正文是描述/兑付计划/履历

核心能力：
  1. 解析 设定库/承诺/P-xxx.md
  2. 计算节奏债（强度高 + 超期未推进）
  3. 章末结转（touch 承诺 → 更新 front matter + 追加履历）
  4. 到期清单（兑付期限快到了）

用法：
  python core/promises.py --book <书名> --list
  python core/promises.py --book <书名> --debts          # 节奏债
  python core/promises.py --book <书名> --due            # 到期清单
  python core/promises.py --book <书名> --touch P-005 --ch 004 --action 推进 --note "甲看清了半个字"
"""
import os
import re
import sys
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _projects_root():
    """客户项目目录 —— 与 coordinator.projects_root() 同一套优先级。

    2026-11-07 修：原来直接用 <ROOT>/projects（程序安装目录），
    而客户数据在 %APPDATA%/novelapp-desktop/data/projects，
    两边读到的承诺表不是同一份。"""
    p = os.environ.get('NOVELAPP_PROJECTS')
    if p:
        return os.path.abspath(p)
    d = os.environ.get('NOVELAPP_DATA')
    if d:
        return os.path.join(os.path.abspath(d), 'projects')
    if os.environ.get('APPDATA'):
        return os.path.join(os.environ['APPDATA'], 'novelapp-desktop', 'data', 'projects')
    return os.path.join(ROOT, 'projects')

# 节奏债阈值：高承诺超过这么多章没推进就亮黄灯
DEBT_THRESHOLD = 10


def promise_dir(book):
    return os.path.join(_projects_root(), book, "设定库", "承诺")


def parse_front(text):
    """解析 front matter（平铺 YAML 子集）"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        return {}, text
    head, body = m.group(1), m.group(2)
    data = {}
    key = None
    for line in head.split("\n"):
        s = line.rstrip()
        if not s or s.startswith("#"):
            continue
        if s.lstrip().startswith("- ") and key:
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(s.lstrip()[2:].strip())
            continue
        mm = re.match(r"^([^:]+):\s*(.*)$", s)
        if mm:
            key = mm.group(1).strip()
            val = mm.group(2).strip()
            data[key] = val if val else []
    return data, body


def load_all(book):
    """读所有承诺"""
    d = promise_dir(book)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(d, fn)
        with open(p, "r", encoding="utf-8") as f:
            text = f.read()
        meta, body = parse_front(text)
        meta["_file"] = fn
        meta["_path"] = p
        meta["_body"] = body
        out.append(meta)
    return out


def to_int(v, default=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def current_chapter(book):
    """当前写到第几章（从 章节/ 目录算）"""
    d = os.path.join(_projects_root(), book, "章节")
    if not os.path.isdir(d):
        return 0
    nums = []
    for fn in os.listdir(d):
        m = re.match(r"^(\d{3})", fn)
        if m and fn.endswith(".md"):
            nums.append(int(m.group(1)))
    return max(nums) if nums else 0


def debts(book):
    """节奏债：强度高 + 超过阈值章没推进"""
    cur = current_chapter(book)
    out = []
    for p in load_all(book):
        if p.get("状态") != "进行":
            continue
        if p.get("强度") != "高":
            continue
        last = to_int(p.get("最后推进章"))
        gap = cur - last
        if gap > DEBT_THRESHOLD:
            out.append({
                "id": p.get("编号"),
                "title": p.get("标题"),
                "gap": gap,
                "last": last,
                "current": cur,
            })
    return out


def due(book):
    """兑付期限不是「待定」的承诺"""
    out = []
    for p in load_all(book):
        if p.get("状态") != "进行":
            continue
        d = str(p.get("兑付期限") or "").strip()
        if d and d != "待定":
            out.append({"id": p.get("编号"), "title": p.get("标题"), "due": d, "strength": p.get("强度")})
    return out


def touch(book, pid, chapter, action, note):
    """结转：更新 front matter + 追加履历"""
    ps = load_all(book)
    target = None
    for p in ps:
        if p.get("编号") == pid:
            target = p
            break
    if not target:
        return {"ok": False, "error": "找不到承诺 " + pid}

    path = target["_path"]
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # 更新 最后推进章
    text = re.sub(r"^(最后推进章:\s*).*$", r"\g<1>" + chapter, text, count=1, flags=re.M)
    # 兑付时改状态
    if action == "兑付":
        text = re.sub(r"^(状态:\s*).*$", r"\g<1>已兑付", text, count=1, flags=re.M)
    elif action == "弃置":
        text = re.sub(r"^(状态:\s*).*$", r"\g<1>已弃置", text, count=1, flags=re.M)
    # 追加履历
    line = "- " + chapter + "：" + action + ("——" + note if note else "")
    if "## 履历" in text:
        text = text.rstrip() + "\n" + line + "\n"
    else:
        text = text.rstrip() + "\n\n## 履历\n" + line + "\n"

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)

    return {"ok": True, "id": pid, "chapter": chapter, "action": action}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--debts", action="store_true")
    ap.add_argument("--due", action="store_true")
    ap.add_argument("--touch", default=None)
    ap.add_argument("--ch", default=None)
    ap.add_argument("--action", default="推进")
    ap.add_argument("--note", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.touch:
        if not args.ch:
            print("--touch 需要 --ch")
            return 1
        r = touch(args.book, args.touch, args.ch, args.action, args.note)
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r.get("ok") else 1

    ps = load_all(args.book)
    cur = current_chapter(args.book)

    if args.json:
        print(json.dumps({"current_chapter": cur, "promises": ps, "debts": debts(args.book)}, ensure_ascii=False, indent=1, default=str))
        return 0

    print("=== 承诺清单（共 %d 条，当前第 %d 章）===" % (len(ps), cur))
    for p in ps:
        st = p.get("状态", "?")
        mark = "○" if st == "进行" else ("✓" if st == "已兑付" else "✗")
        gap = cur - to_int(p.get("最后推进章"))
        gap_txt = ("%d 章前" % gap) if gap > 0 else ("本章" if gap == 0 else "已推进到 ch%03d" % to_int(p.get("最后推进章")))
        print("  %s %-10s %-20s %-4s %-4s 最后推进 ch%03d（%s）" % (
            mark, p.get("编号", "?"), p.get("标题", "?"), p.get("类型", "?"), p.get("强度", "?"),
            to_int(p.get("最后推进章")), gap_txt))

    ds = debts(args.book)
    if ds:
        print()
        print("=== 节奏债（阈值 %d 章）===" % DEBT_THRESHOLD)
        for d in ds:
            print("  ⚠ %s %s：%d 章没推进（第 %d 章埋，现在第 %d 章）" % (d["id"], d["title"], d["gap"], d["last"], d["current"]))

    dd = due(args.book)
    if dd:
        print()
        print("=== 到期清单 ===")
        for d in dd:
            print("  · %s %s → 兑付期限 %s（%s）" % (d["id"], d["title"], d["due"], d["strength"]))

    return 0


if __name__ == "__main__":
    sys.exit(main())