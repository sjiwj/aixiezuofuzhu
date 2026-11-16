# -*- coding: utf-8 -*-
"""读债：这一章必须动哪几条账。

研讨结论（AI-A）：
    「账本必须先被消费，后被填写。打开写章界面时系统说『这三条不处理就写不下去』，
      而不是写完说『你有 5 条陈旧』。读路径必须先于写路径。」

用法:
    python scripts/debt_view.py --book <书名> [--chapter 009]
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
    fm = {}
    m = re.match(r"^---\s*\n([\s\S]*?)\n---", text)
    if not m:
        return fm
    for line in m.group(1).split(chr(10)):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


STRENGTH = {"\u9ad8": 3, "\u4e2d": 2, "\u4f4e": 1}


def cur_volume(book_dir, ch):
    """当前章属于哪一卷。解析 大纲/全书大纲.md 的「### 卷一 · 名字（001–060）」。"""
    d = os.path.join(book_dir, "大纲")
    if not os.path.isdir(d):
        return ""
    pat = re.compile(r"###\s*卷([一二三四五六七八九十]+)[^（(]*[（(](\d{1,4})\s*[–\-~]\s*(\d{1,4})[）)]")
    for fn in sorted(x for x in os.listdir(d) if x.endswith(".md")):
        text = read(os.path.join(d, fn))
        for m in pat.finditer(text):
            lo, hi = int(m.group(2)), int(m.group(3))
            if lo <= ch <= hi:
                return "卷" + m.group(1)
    return ""


def vol_ok(promise_fm, vol):
    """承诺写了「可推进卷」且不含当前卷 -> 排除。"""
    if not vol:
        return True
    vols = str(promise_fm.get("可推进卷") or "").strip()
    if not vols:
        return True
    return vol in [v.strip() for v in re.split(r"[,,、]", vols) if v.strip()]


def load_state_gaps(book_dir):
    """角色状态里「未记录/未说明」的字段——这也是债。"""
    d = os.path.join(book_dir, "设定库", "角色状态.md")
    text = read(d)
    if not text:
        return []
    out, who = [], ""
    for ln in text.split(chr(10)):
        if ln.startswith("## "):
            who = ln[3:].strip()
        elif ("未记录" in ln or "未说明" in ln) and who:
            key = ln.strip().lstrip("-* ").split("**")[1] if "**" in ln else "字段"
            out.append({"who": who, "field": key})
    return out


def load_promises(book_dir, cur_ch, vol=""):
    """未兑付的承诺，按「强度 × 未推进章数」排序"""
    d = os.path.join(book_dir, "\u8bbe\u5b9a\u5e93", "\u627f\u8bfa")
    out = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md"):
            continue
        text = read(os.path.join(d, fn))
        fm = front_matter(text)
        if fm.get("\u72b6\u6001") in ("\u5df2\u5151\u4ed8", "\u5df2\u5b8c\u6210", "\u5e9f\u5f03", "closed", "done"):
            continue
        title = fm.get("\u6807\u9898") or fn.replace(".md", "")
        strength = fm.get("\u5f3a\u5ea6") or "\u4e2d"
        last = fm.get("\u6700\u540e\u63a8\u8fdb\u7ae0") or ""
        last_no = 0
        m = re.search(r"(\d{1,4})", str(last))
        if m:
            last_no = int(m.group(1))
        gap = max(0, cur_ch - last_no) if last_no else cur_ch
        out.append({"id": fm.get("\u7f16\u53f7") or fn, "title": title,
                    "strength": STRENGTH.get(strength, 2), "strength_label": strength,
                    "gap": gap, "last_ch": last_no,
                    "weight": STRENGTH.get(strength, 2) * (1 + gap / 10.0)})
    out.sort(key=lambda x: -x["weight"])
    return out


def load_foreshadow(book_dir, cur_ch, stale_after=5):
    d = os.path.join(book_dir, "\u8bbe\u5b9a\u5e93", "\u4f0f\u7b14.md")
    text = read(d)
    if not text:
        return []
    rows, head = [], None
    for ln in text.split(chr(10)):
        st = ln.strip()
        if not st.startswith("|"):
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells if c):
            continue
        if head is None:
            head = cells
            continue
        rows.append(dict(zip(head, cells)))
    out = []
    for r in rows:
        s = str(r.get("\u72b6\u6001") or "").strip()
        if s in ("\u4f5c\u5e9f", "\u5df2\u4f5c\u5e9f", "\u5df2\u6536", "\u5df2\u5151\u4ed8", "drop"):
            continue
        m = re.search(r"(\d{1,4})", str(r.get("\u57cb\u5728\u54ea\u7ae0") or ""))
        buried = int(m.group(1)) if m else 0
        if not buried:
            continue
        gap = cur_ch - buried
        if gap >= stale_after:
            out.append({"id": r.get("\u7f16\u53f7") or "?", "title": str(r.get("\u5185\u5bb9") or "")[:40],
                        "gap": gap, "weight": 2 * (1 + gap / 10.0)})
    out.sort(key=lambda x: -x["weight"])
    return out


def build_debt(book, chapter):
    book_dir = os.path.join(data_root(), "projects", book)
    if not os.path.isdir(book_dir):
        return {"ok": False, "error": "\u4e66\u4e0d\u5b58\u5728\uff1a%s" % book}
    try:
        cur_ch = int(re.sub(r"\D", "", str(chapter)) or 0)
    except ValueError:
        cur_ch = 0
    if not cur_ch:
        chs = os.path.join(book_dir, "\u7ae0\u8282")
        nums = [int(m.group(1)) for f in (os.listdir(chs) if os.path.isdir(chs) else [])
                for m in [re.match(r"(\d{1,4})", f)] if m]
        cur_ch = (max(nums) + 1) if nums else 1
    vol = cur_volume(book_dir, cur_ch)
    prom = load_promises(book_dir, cur_ch, vol)
    gaps = load_state_gaps(book_dir)
    fore = load_foreshadow(book_dir, cur_ch)
    items = []
    for p in prom[:4]:
        items.append({"kind": "\u627f\u8bfa", "id": p["id"], "title": p["title"],
                      "why": "\u5f3a\u5ea6%s\uff0c\u5df2\u7ecf %d \u7ae0\u6ca1\u63a8\u8fdb" % (p["strength_label"], p["gap"]),
                      "weight": p["weight"]})
    for f2 in fore[:4]:
        items.append({"kind": "\u4f0f\u7b14", "id": f2["id"], "title": f2["title"],
                      "why": "\u57cb\u4e86 %d \u7ae0\u6ca1\u52a8" % f2["gap"],
                      "weight": f2["weight"]})
    items.sort(key=lambda x: -x["weight"])
    top = items[:3]
    return {"ok": True, "book": book, "chapter": cur_ch, "volume": vol,
            "must_touch": top, "rest": len(items) - len(top),
            "state_gaps": gaps[:5],
            "summary": "\u8fd9\u4e00\u7ae0\u5fc5\u987b\u52a8 %d \u6761\uff0c\u5176\u4f59 %d \u6761\u662f\u80cc\u666f" % (len(top), max(0, len(items) - len(top)))}


def main():
    ap = argparse.ArgumentParser(description="\u8bfb\u503a\uff1a\u8fd9\u4e00\u7ae0\u5fc5\u987b\u52a8\u54ea\u51e0\u6761\u8d26")
    ap.add_argument("--book", required=True)
    ap.add_argument("--chapter")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rep = build_debt(a.book, a.chapter)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0 if rep.get("ok") else 1
    if not rep.get("ok"):
        print(rep.get("error"))
        return 1
    print("=" * 60)
    print("\u8bfb\u503a  \u300a%s\u300b\u7b2c %d \u7ae0" % (rep["book"], rep["chapter"]))
    print("=" * 60)
    print(rep["summary"])
    print("-" * 60)
    for i, it in enumerate(rep["must_touch"], 1):
        print("%d. [%s] %s" % (i, it["kind"], it["title"]))
        print("   %s" % it["why"])
    if not rep["must_touch"]:
        print("\u8fd9\u4e00\u7ae0\u6ca1\u6709\u5fc5\u987b\u52a8\u7684\u8d26\u3002")
    if rep.get("state_gaps"):
        print("-" * 60)
        print("另外，资料上有 %d 处空着（写之前建议补）：" % len(rep["state_gaps"]))
        for g in rep["state_gaps"][:5]:
            print("   %s 的「%s」没记" % (g["who"], g["field"]))
    # 缝针入口：诊断完必须紧跟一个 5 分钟能做完的动作，
    # 否则就是「分析工具」——看完报告就走（商业调研三方一致的一条）。
    if rep["must_touch"]:
        fs_ids = [it["id"] for it in rep["must_touch"] if it.get("kind") == "伏笔" and it.get("id")]
        pm_ids = [it["id"] for it in rep["must_touch"] if it.get("kind") == "承诺" and it.get("id")]
        args = " ".join(["--foreshadow " + i for i in fs_ids] + ["--promise " + i for i in pm_ids])
        if args:
            print("-" * 60)
            print("如果其中有你打算放弃的，标作废就不再催你（1 分钟）：")
            print("  python scripts/ledger_abandon.py --book %s %s" % (rep["book"], args))
            print("  （先加 --dry-run 看会改什么，不动文件）")
    print("-" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())