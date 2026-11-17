#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_panel.py — F4 · 审稿团工具化（读者 / 编辑 / 结构 + 汇总规则）

用法：
    # 1. 出三份审稿输入（贴给三个不同 agent）
    python tools/review_panel.py emit --book "projects/<书名>" --chapter 1

    # 2. 三家回完之后合并
    python tools/review_panel.py merge --book ... --chapter 1 \
        --reader 策划\\审稿-第1章\\reader.md --editor ...\\editor.md --structure ...\\structure.md

    # 3. 只跑结构层的机器指标
    python tools/review_panel.py metrics --file 章节\\001-000.md

汇总规则（写死）：
    三家指到同一处 → 必改（P0）
    两家指到同一处 → 必改（P0）
    一家独有       → 记录，不改（P2）
"""
import argparse
import json
import re
import sys
from pathlib import Path

BANNED = ["仿佛", "宛如", "不禁", "若有所思", "深邃", "眼眸", "勾勒",
          "交织", "弥漫", "氤氲", "彷徨", "震撼", "淋漓", "悄然"]

ROLES = {
    "reader": dict(
        name="读者",
        ask=["哪一句开始想放下？", "哪一句觉得作者在演？", "想不想看下一章（一句话理由）？", "觉得主角是什么人？"],
        forbid="不改稿、不给建议、不夸。只指出位置和感受。",
    ),
    "editor": dict(
        name="编辑",
        ask=["哪几句是替人物想的聪明话？", "哪几处信息读者补不上？", "负动作（否定式陈述、手部小动作）重复几次？"],
        forbid="不改稿、不推荐替代句。只点名。",
    ),
    "structure": dict(
        name="结构",
        ask=["哪一拍超预算？", "哪一拍强度不达标？", "钩子类型对不对？", "铺垫与高潮的力量比是多少？"],
        forbid="不谈文笔、不谈人物。只看预算与节奏。",
    ),
}

ITEM_RULE = """每条一行，格式固定：

- 「原文引用（6 字以上，必须与正文一字不差）」一句话挑错

不许合并多条，不许写"整体节奏偏慢"这类无引用条目。"""


def read(p):
    p = Path(p)
    return p.read_text(encoding="utf-8") if p.exists() else None


def char_count(text):
    return len(re.sub(r"\s", "", text))


def metrics(text):
    body = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    joined = "".join(body)
    chars = char_count(joined)
    sentences = [s for s in re.split(r"[。！？…]+", joined) if s.strip()]
    paras = [p for p in body if p]
    # 2026-11-16 修：半角引号与『』也要算。旧版只认 “”/「」，用半角引号的正文对话占比恒为 0 → 闸二误判
    dlg = "".join(re.findall(r"[“「]([^”」]*)[”」]", joined))
    dlg += "".join(re.findall(r'"([^"]*)"', joined))
    dlg += "".join(re.findall(r"『([^』]*)』", joined))
    out = {
        "字数": chars,
        "段数": len(paras),
        "平均段长": round(chars / len(paras), 1) if paras else 0,
        "平均句长": round(char_count(joined) / len(sentences), 1) if sentences else 0,
        "对话占比": round(len(dlg) / chars, 3) if chars else 0,
        "最长段": max((char_count(p) for p in paras), default=0),
        "破折号": joined.count("——"),
        "阿拉伯数字": len(re.findall(r"[0-9]", joined)),
        "禁词命中": {w: joined.count(w) for w in BANNED if w in joined},
    }
    return out


ITEM_PUNCT = "，。、！？；：“”‘’（）《》…— \t\r\n"


def strip_punct(s):
    return "".join(ch for ch in s if ch not in ITEM_PUNCT)


def parse_items(text):
    """从一份意见里抽出引用条目：- 「原文」评语"""
    items = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s.startswith("-"):
            continue
        m = re.search(r"[「“]([^」”]{6,})[」”]\s*(.*)$", s)
        if not m:
            continue
        quote, note = m.group(1).strip(), m.group(2).strip()
        key = strip_punct(quote)[:12]
        if not key:
            continue
        items.append(dict(quote=quote, note=note, key=key))
    return items


def dedup_keys(items):
    seen = {}
    for it in items:
        seen.setdefault(it["key"], it)
    return list(seen.values())


def load_chapter_body(book, chapter):
    """本章正文（去空白与标点）。找不到返回空串——空串表示不做引用校验。"""
    d = Path(book) / "章节"
    if not d.exists():
        return ""
    files = sorted(d.glob(f"*第{chapter}章*.md")) or sortedchap(d, chapter)
    if not files:
        return ""
    return strip_punct(read(files[0]) or "")


def cmd_metrics(args):
    t = read(args.file)
    if t is None:
        print(f"文件不存在: {args.file}")
        return 1
    m = metrics(t)
    print(json.dumps(m, ensure_ascii=False, indent=2))
    return 0


def cmd_emit(args):
    book = Path(args.book)
    chap_dir = book / "章节"
    files = sorted(chap_dir.glob(f"*第{args.chapter}章*.md")) or sortedchap(chap_dir, args.chapter)
    if not files:
        print(f"找不到第 {args.chapter} 章正文（章节/*第N章*.md）")
        return 1
    body = read(files[0])
    prev = ""
    if args.chapter > 1:
        pf = sorted(chap_dir.glob(f"*第{args.chapter-1}章*.md"))
        if pf:
            prev = "\n".join(read(pf[0]).splitlines()[-12:])
    budget = read(book / "策划" / f"预算-第{args.chapter}章.md") or "（预算表缺失 → 结构层只能看正文）"
    anchor = read(book / "meta" / "style-anchor.md") or ""
    m = metrics(body)

    out_dir = book / "策划" / f"审稿-第{args.chapter}章"
    out_dir.mkdir(parents=True, exist_ok=True)

    for role, spec in ROLES.items():
        parts = [f"# 审稿 · {spec['name']}层 · 第 {args.chapter} 章", ""]
        parts.append(f"> 你只做一件事：{spec['name']}的那个视角挑错。{spec['forbid']}")
        parts.append("")
        parts.append("## 要回答的问题")
        for q in spec["ask"]:
            parts.append(f"- {q}")
        parts.append("")
        parts += ["## 输出格式", "", ITEM_RULE, ""]
        if role == "structure":
            parts += ["## 机器指标（已算好，直接引用）", "", "```json",
                      json.dumps(m, ensure_ascii=False, indent=2), "```", "",
                      "## 本章 8 拍预算", "", budget, ""]
        if role == "editor" and anchor:
            parts += ["## 本书风格锚点（判断\"替人物想的聪明话\"用）", "", anchor, ""]
        if prev:
            parts += ["## 上一章末尾（承接检查用）", "", prev, ""]
        parts += ["## 本章正文", "", body, ""]
        (out_dir / f"{role}.md").write_text("\n".join(parts), encoding="utf-8")

    print(f"三份审稿输入已写: {out_dir}")
    for role in ROLES:
        print(f"  {role}.md  ({[p for p in out_dir.glob(role + '.md')][0].stat().st_size} bytes)")
    print("下一步：把三份分别贴给三个不同模型，回填同名文件，再跑 merge。")
    return 0


def sortedchap(d, n):
    return sorted([p for p in d.glob("*.md") if f"第{n}章" in p.name])


def cmd_merge(args):
    book = Path(args.book)
    src = dict(reader=args.reader, editor=args.editor, structure=args.structure)
    parsed = {}
    for role, p in src.items():
        t = read(p)
        if t is None:
            print(f"缺一份：{role} -> {p}")
            return 1
        parsed[role] = dedup_keys(parse_items(t))

    # 引用必须能在正文里定位：否则那是模板占位行或编造的引用，两家撞上也不许算"交集"
    body = load_chapter_body(book, args.chapter)
    if body:
        dropped = 0
        for role, items in parsed.items():
            keep = []
            for it in items:
                if strip_punct(it["quote"]) in body:
                    keep.append(it)
                else:
                    dropped += 1
            parsed[role] = keep
        if dropped:
            print(f"丢弃 {dropped} 条无法在正文定位的引用（模板占位/编造引用，不计入交集）")

    hits = {}
    for role, items in parsed.items():
        for it in items:
            hits.setdefault(it["key"], dict(quote=it["quote"], roles=[], notes={}))
            e = hits[it["key"]]
            if role not in e["roles"]:
                e["roles"].append(role)
            e["notes"][role] = it["note"]

    p0 = [e for e in hits.values() if len(e["roles"]) >= 2]
    p2 = [e for e in hits.values() if len(e["roles"]) == 1]
    p0.sort(key=lambda e: -len(e["roles"]))

    out = book / "策划" / f"审稿-第{args.chapter}章" / f"第{args.chapter}章-审稿.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    L = [f"# 第 {args.chapter} 章 · 审稿汇总", "",
         f"> 汇总规则：三家或两家指到同一处 = 必改（P0）；一家独有 = 记录不改（P2）。",
         f"> 交集 {len(p0)} 条 / 独有 {len(p2)} 条", "", "## P0 必改（交集）", ""]
    if not p0:
        L.append("（无交集——两家以上没有指到同一处，说明三家都跑偏了，重跑一次）")
    for e in p0:
        L.append(f"- 「{e['quote']}」  ← {'+'.join(e['roles'])}（{len(e['roles'])}/3）")
        for r, n in e["notes"].items():
            L.append(f"    - {r}：{n}")
    L += ["", "## P2 记录（一家独有，本轮不改）", ""]
    for e in p2:
        L.append(f"- 「{e['quote']}」  ← {e['roles'][0]}：{e['notes'][e['roles'][0]]}")
    out.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"交集 {len(p0)} 条 / 独有 {len(p2)} 条")
    for e in p0:
        print(f"  P0 [{len(e['roles'])}/3] 「{e['quote'][:24]}」")
    print(f"已写: {out}")
    if len(p0) < 3:
        print("警告：交集 <3 条，按 08 号验收标准不达标（06 号实测两家交叉有 4 条）")
        return 2
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("emit")
    a.add_argument("--book", required=True)
    a.add_argument("--chapter", type=int, required=True)

    b = sub.add_parser("merge")
    b.add_argument("--book", required=True)
    b.add_argument("--chapter", type=int, required=True)
    b.add_argument("--reader", required=True)
    b.add_argument("--editor", required=True)
    b.add_argument("--structure", required=True)

    c = sub.add_parser("metrics")
    c.add_argument("--file", required=True)

    args = ap.parse_args()
    return dict(emit=cmd_emit, merge=cmd_merge, metrics=cmd_metrics)[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
