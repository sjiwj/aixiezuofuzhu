#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deai_patch.py — F5 · 报告驱动定向改写（只改命中句，不整篇重写）

用法：
    python tools/deai_patch.py --file 章节\\001-000.md \
        --report 策划\\02-第1章质检记录.md --dry

    # 生成待填 patch
    python D:\\NovelApp\\tools\\deai_patch.py --file ... --report ... --emit 策划\\patch-第1章.md
    # 填完新句后应用（三重校验，任一不过就拒绝）
    python D:\\NovelApp\\tools\\deai_patch.py --file ... --apply 策划\\patch-第1章.md

三条纪律（对应 08 号 F5）：
    1. 只改命中句；未命中的行 0 改动（脚本逐行比对，改动行数必须等于命中数）
    2. 原文在改稿期间发生变化 → 拒绝应用（patch 头里存了源文件 sha256）
    3. 字数变化 ≤5%，超出必须等量删冗余（不是加字）
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

QUOTE_RE = re.compile(r"[「“]([^」”]{6,})[」”]")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read(p):
    return Path(p).read_text(encoding="utf-8")


def char_count(text):
    return len(re.sub(r"\s", "", text))


def extract_hits(report_text):
    """质检记录里的命中句：取引号内 ≥6 字的原文引用，保持出现顺序并去重。"""
    hits, seen = [], set()
    for m in QUOTE_RE.finditer(report_text):
        q = m.group(1).strip()
        if q in seen:
            continue
        seen.add(q)
        hits.append(q)
    return hits


def locate(body_lines, quote):
    """返回该句在正文中出现的行号列表（0 基）。"""
    return [i for i, ln in enumerate(body_lines) if quote in ln]


FRAG_SPLIT = re.compile(r"[…\u2026—，、；：\"\"''（）「」“”\s]+")


def locate_fragment(body_lines, quote):
    """引文跨了"说"标签或含省略号时，退一步用最长片段定位。
    返回 (行号, 片段) 或 (None, None)。"""
    frags = [f for f in FRAG_SPLIT.split(quote) if len(f) >= 6]
    for f in sorted(frags, key=len, reverse=True):
        idx = locate(body_lines, f)
        if len(idx) == 1:
            return idx[0], f
    return None, None


def classify(body_lines, hits):
    exact, fuzzy, missing = [], [], []
    for q in hits:
        idx = locate(body_lines, q)
        if len(idx) == 1:
            exact.append((q, idx[0]))
            continue
        if len(idx) > 1:
            missing.append((q, f"在正文出现 {len(idx)} 次，无法唯一定位"))
            continue
        no, frag = locate_fragment(body_lines, q)
        if no is not None:
            fuzzy.append((q, no, frag))
        else:
            missing.append((q, "正文里找不到（引用不完整或已被改过）"))
    return exact, fuzzy, missing


def cmd_dry(args):
    body = read(args.file)
    lines = body.splitlines()
    hits = extract_hits(read(args.report))
    exact, fuzzy, missing = classify(lines, hits)
    print(f"命中数 {len(hits)}")
    print(f"精确定位 {len(exact)}（可直接进 patch）")
    print(f"片段定位 {len(fuzzy)}（引文跨说标签/含省略号，需补全原句才能进 patch）")
    print(f"未定位 {len(missing)}")
    print(f"patch 行数 {len(exact)}")
    print(f"字数变化 0.00%（dry 模式，未写文件）")
    for q, no, frag in fuzzy:
        print(f"  [片段] 行{no+1} 「{q[:20]}」 -> 片段「{frag}」")
    for q, why in missing:
        print(f"  [跳过] 「{q[:24]}」 {why}")
    return 0 if not missing else 2


def cmd_emit(args):
    body = read(args.file)
    lines = body.splitlines()
    hits = extract_hits(read(args.report))
    exact, fuzzy, _ = classify(lines, hits)
    rows = [(q, "", no) for q, no in exact]
    for q, no, frag in fuzzy:
        rows.append((frag, "", no))
    out = [f"<!-- deai-patch source={Path(args.file).as_posix()} "
           f"sha256={sha(body)} chars={char_count(body)} hits={len(rows)} -->", ""]
    for q, new, no in rows:
        out.append(f"- 行{no+1} 原句：{q}")
        out.append(f"- 行{no+1} 新句：")
    Path(args.emit).parent.mkdir(parents=True, exist_ok=True)
    Path(args.emit).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"patch 已写: {args.emit}（{len(rows)} 条待填，其中 {len(fuzzy)} 条是片段）")
    print(f"源文件 sha256={sha(body)[:12]} chars={char_count(body)}")
    return 0


def parse_patch(text):
    head = re.search(r"sha256=([0-9a-f]{64})\s+chars=(\d+)", text)
    if not head:
        raise SystemExit("patch 头缺失（需要 <!-- deai-patch ... sha256=... chars=... -->）")
    rows, cur = [], None
    for ln in text.splitlines():
        m = re.match(r"^- 行(\d+)\s*原句：(.*)$", ln.strip())
        if m:
            cur = dict(line=int(m.group(1)), old=m.group(2), new="")
            rows.append(cur)
            continue
        m = re.match(r"^- 行(\d+)\s*新句：(.*)$", ln.strip())
        if m and cur is not None:
            cur["new"] = m.group(2)
    return head.group(1), int(head.group(2)), [r for r in rows if r["new"].strip()]


def cmd_apply(args):
    path = Path(args.file)
    body = read(path)
    want_sha, want_chars, rows = parse_patch(read(args.apply))

    # 纪律 2：原文变了就拒绝
    if sha(body) != want_sha:
        print(f"拒绝应用：原文已变更（patch 期望 {want_sha[:12]}，当前 {sha(body)[:12]}）")
        return 1
    if not rows:
        print("拒绝应用：patch 里没有填好的新句（全部为空）")
        return 1

    lines = body.splitlines()
    touched, problems = set(), []
    for r in rows:
        idx = locate(lines, r["old"])
        if len(idx) != 1:
            problems.append(f"行{r['line']} 「{r['old'][:20]}」定位到 {len(idx)} 处")
            continue
        i = idx[0]
        if i in touched:
            problems.append(f"行{r['line']} 与另一条 patch 落在同一行")
            continue
        lines[i] = lines[i].replace(r["old"], r["new"])
        touched.add(i)
    if problems:
        print("拒绝应用：")
        for p in problems:
            print("  " + p)
        return 1

    new_body = "\n".join(lines) + ("\n" if body.endswith("\n") else "")
    old_lines = body.splitlines()

    # 纪律 1：未命中行 0 改动
    changed = sum(1 for a, b in zip(old_lines, lines) if a != b)
    if changed != len(touched):
        print(f"拒绝应用：改动行数 {changed} != 命中行数 {len(touched)}（有串行/串段）")
        return 1
    if len(old_lines) != len(lines):
        print("拒绝应用：行数发生变化（定向改写不允许增删行）")
        return 1

    # 纪律 3：字数变化 ≤5%
    c0, c1 = char_count(body), char_count(new_body)
    dev = (c1 - c0) / c0 * 100
    print(f"改动行 {changed} 行 / 命中 {len(rows)} 条")
    print(f"字数 {c0} -> {c1}（{dev:+.2f}%）")
    if abs(dev) > 5:
        print("拒绝应用：字数变化超过 5%，先等量删冗余再改")
        return 1
    if args.dry:
        print("dry 模式，未写文件")
        return 0
    backup = path.with_suffix(path.suffix + ".bak-deai")
    backup.write_text(body, encoding="utf-8")
    path.write_text(new_body, encoding="utf-8")
    print(f"已应用。备份: {backup}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--report")
    ap.add_argument("--emit")
    ap.add_argument("--apply")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    if args.apply:
        return cmd_apply(args)
    if not args.report:
        raise SystemExit("需要 --report（或 --apply）")
    if args.emit:
        return cmd_emit(args)
    return cmd_dry(args)


if __name__ == "__main__":
    sys.exit(main())
