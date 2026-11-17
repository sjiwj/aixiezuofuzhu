#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_budget.py — F3 · 8 拍预算表生成 + 闸一（fail-closed）

用法：
    python tools/chapter_budget.py --book "projects/<书名>" --chapter 2
    python D:\\NovelApp\\tools\\chapter_budget.py --book ... --chapter 2 --no-write
    python D:\\NovelApp\\tools\\chapter_budget.py --book ... --chapter 2 --words 3400

输入：大纲/00-第一卷大纲与章纲.md（章纲表 + 章内 8 拍表，有则用，无则按默认模板生成）
输出：8 行拍表 + 合计校验 + 重点章判定；默认写 策划/预算-第N章.md
闸一：五条否决项全部通过才 exit 0；任一失败 exit 1（不许派写手）

规则来源：references/流水线-融合版.md §三 Step 3「8 拍预算表」
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_WORDS = 3200

# 默认 8 拍模板：内容模板 / 强度权重 / 字数权重 / 必须发生 / 不许发生
DEFAULT_BEATS = [
    ("接上一章",       0.45, 0.08, "第一段接上一章最后一个动作或最后一句", "不许重新开场，不许先写景"),
    ("本章目标显形",   0.60, 0.11, "主角说出或做出本章要办的那件事", "不许用心理独白交代目标"),
    ("第一次受阻",     0.75, 0.07, "有人挡住他，且理由是规矩或旧例", "不许反派无理由作恶，不许威胁式台词"),
    ("代价或损失",     0.90, 0.14, "场面里有一个人当场受损（钱、脸、身体、关系）", "不许把代价推后成以后会招祸"),
    ("换路或加码",     0.80, 0.08, "他改一次做法（换地方、换人、换由头）", "不许靠运气解决"),
    ("正面冲突",       1.00, 0.16, "双方各出一句不可退让的话", "不许他说\"我这是为了……\""),
    ("结果落地",       0.95, 0.18, "本章目标有明确结果（成或不成，都要落到物件上）", "不许模糊收束，不许\"事情没那么简单\""),
    ("钩子",           1.00, 0.18, "停在未答问句或一个动作上", "不许总结、升华、预告旁白"),
]

FUNC_TO_BEAT = {
    "立处境": 0, "规矩的墙": 1, "死结": 2, "溢出（核心）": 3, "转折": 4,
    "代价当场兑现": 5, "死结 B": 6, "钩子": 7,
}


def read(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def clean(s):
    return s.replace("*", "").strip()


def parse_outline(path):
    t = read(path)
    if not t:
        raise SystemExit(f"大纲不存在: {path}")
    lines = t.splitlines()

    meta = {}          # 章号 -> dict(intensity, climax, hook, change, scenes, summary)
    for ln in lines:
        if not ln.startswith("|"):
            continue
        c = cells(ln)
        if len(c) < 6:
            continue
        n = clean(c[0])
        if not n.isdigit():
            continue
        inten_raw = clean(c[1])
        m = re.match(r"^(\d+)", inten_raw)
        if not m:
            continue
        chap = int(n)
        if chap in meta:
            continue
        meta[chap] = dict(
            intensity=int(m.group(1)),
            climax=("★" in inten_raw) or ("climax" in inten_raw.lower()),
            hook=clean(c[2]) if len(c) > 2 else "",
            change=clean(c[3]) if len(c) > 3 else "",
            scenes=clean(c[4]) if len(c) > 4 else "",
            summary=clean(c[5]) if len(c) > 5 else "",
        )

    # 章内 8 拍表
    beats_by_ch = {}
    cur = None
    for ln in lines:
        mb = re.match(r"^###\s*第\s*(\d+)\s*章\s*[·・]\s*8\s*拍", ln.strip())
        if mb:
            cur = int(mb.group(1))
            beats_by_ch[cur] = []
            continue
        if ln.startswith("###") and cur is not None:
            cur = None
            continue
        if cur is None or not ln.startswith("|"):
            continue
        c = cells(ln)
        if not c or c[0] in ("拍", "---") or set(c[0]) <= set("-: "):
            continue
        if not re.fullmatch(r"\d+", c[0]):
            continue
        if len(c) < 4:
            continue
        words = re.sub(r"[^0-9]", "", c[1])
        if not words:
            continue
        beats_by_ch[cur].append(dict(no=int(c[0]), words=int(words), content=c[2], func=c[3]))
    return meta, beats_by_ch


def actual_words(book, chapter):
    """从 大纲 进度表取已写字数（有则用），否则 None。"""
    t = read(Path(book) / "大纲" / "00-第一卷大纲与章纲.md") or ""
    for ln in t.splitlines():
        if not ln.startswith("|"):
            continue
        c = cells(ln)
        if len(c) >= 5 and re.fullmatch(r"\d+", c[0]) and int(c[0]) == chapter:
            if c[2].isdigit():
                return int(c[2])
    return None


def build(meta_c, beats, words):
    out = []
    if beats:
        # 章纲自带拍表：字数照抄，强度按曲线，必须/不许取默认模板同位
        total_beat = sum(b["words"] for b in beats)
        for i, b in enumerate(beats):
            tpl = DEFAULT_BEATS[i] if i < len(DEFAULT_BEATS) else DEFAULT_BEATS[-1]
            out.append(dict(
                no=b["no"], content=b["content"], words=b["words"],
                intensity=round(tpl[1] * meta_c["intensity"]) or 1,
                must=tpl[3], mustnot=tpl[4],
                src=f"章纲功能「{b['func']}」",
            ))
        return out, total_beat, "章纲自带"
    # 无拍表：按默认模板 + 权重生成，合计精确等于 words
    ws = [t[2] for t in DEFAULT_BEATS]
    s = sum(ws)
    alloc = [int(round(words * w / s)) for w in ws]
    diff = words - sum(alloc)
    alloc[6] += diff     # 差额压到「结果落地」拍，保证合计精确
    for i, t in enumerate(DEFAULT_BEATS):
        out.append(dict(
            no=i + 1, content=t[0] + ("·" + meta_c["summary"] if i == 1 and meta_c["summary"] else ""),
            words=alloc[i], intensity=round(t[1] * meta_c["intensity"]) or 1,
            must=t[3], mustnot=t[4], src="默认模板",
        ))
    return out, sum(alloc), "默认模板"


def gate(beats, total, words, is_key, model):
    fails = []
    if not beats:
        fails.append("1. 预算文件不存在（未生成任何一拍）")
    if len(beats) < 8:
        fails.append(f"2. 拍数 {len(beats)} < 8")
    dev = (total - words) / words * 100 if words else 0
    if abs(dev) > 10:
        fails.append(f"3. 字数合计偏差 {dev:+.1f}% > 10%")
    for b in beats:
        if not b["must"].strip() or not b["mustnot"].strip():
            fails.append(f"4. 第 {b['no']} 拍缺「必须发生」或「不许发生」")
    if is_key and "kimi" not in model:
        fails.append("5. 重点章未指定 kimi-k3")
    return fails, dev


def render_md(book, chapter, meta_c, beats, total, words, dev, fails, model, src):
    lines = []
    lines.append(f"# 第 {chapter} 章 · 8 拍预算")
    lines.append("")
    lines.append(f"> 生成：`tools/chapter_budget.py`（{src}）· 章纲 targetIntensity={meta_c['intensity']}"
                 f" · climax={meta_c['climax']} · 钩子={meta_c['hook']} · 变化={meta_c['change']}")
    lines.append("")
    lines.append("| 拍 | 内容 | 预算字数 | 强度目标 | 必须发生 | 不许发生 |")
    lines.append("|---|---|---|---|---|---|")
    for b in beats:
        lines.append(f"| {b['no']} | {b['content']} | {b['words']} | {b['intensity']} "
                     f"| {b['must']} | {b['mustnot']} |")
    lines.append(f"| 合计 | — | **{total}** | — | — | — |")
    lines.append("")
    lines.append(f"- 全章字数口径：{words}")
    lines.append(f"- 合计偏差：{dev:+.1f}%（限 ±10%）")
    lines.append(f"- 重点章：{'是' if meta_c['intensity'] >= 8 or meta_c['climax'] else '否'} → `{model}`")
    lines.append("")
    lines.append("## 闸一")
    if fails:
        lines.append("**未通过，不许派写手：**")
        for f in fails:
            lines.append(f"- {f}")
    else:
        lines.append("**PASS**（五条全过，可以出写手任务单）")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--words", type=int, default=None)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()

    book = Path(args.book)
    outline = book / "大纲" / "00-第一卷大纲与章纲.md"
    meta, beats_by_ch = parse_outline(outline)
    if args.chapter not in meta:
        raise SystemExit(f"章纲里没有第 {args.chapter} 章的强度记录")
    meta_c = meta[args.chapter]

    words = args.words or actual_words(book, args.chapter) or DEFAULT_WORDS
    beats, total, src = build(meta_c, beats_by_ch.get(args.chapter), words)

    is_key = meta_c["intensity"] >= 8 or meta_c["climax"]
    model = "moonshot/kimi-k3" if is_key else "deepseek/deepseek-flash"
    fails, dev = gate(beats, total, words, is_key, model)

    print(f"第 {args.chapter} 章 · 8 拍预算（{src}）")
    print("拍 | 内容 | 预算字数 | 强度目标 | 必须发生 | 不许发生")
    for b in beats:
        print(f"{b['no']} | {b['content']} | {b['words']} | {b['intensity']} | {b['must']} | {b['mustnot']}")
    print(f"合计 {total} {words} ±10% {'PASS' if abs(dev) <= 10 else 'FAIL'}（偏差 {dev:+.1f}%）")
    print(f"重点章: {'是' if is_key else '否'} → {model}")
    if fails:
        print("闸一 FAIL：")
        for f in fails:
            print("  " + f)
    else:
        print("闸一 PASS：五条全过")

    if not args.no_write:
        out = book / "策划" / f"预算-第{args.chapter}章.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_md(book, args.chapter, meta_c, beats, total, words, dev, fails, model, src),
                       encoding="utf-8")
        print(f"已写: {out}")

    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
