#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prompt_render.py — F1 装配器 + F6 可复现记录

用法：
    python tools/prompt_render.py --book "projects/<书名>" \
        --chapter 2 --style plain-clean --requirement coherent-continue --beat 1

产出：
    策划\\任务单-第N章-第M拍.md      （装配好的写手任务单）
    策划\\生成记录-第N章.json        （style / requirement / 上下文清单 / 两个 sha256）

fail-closed（任一缺失就不渲染，exit 1）：
    style 文件 / requirement 文件 / meta/style-anchor.md 正样本 / 策划\\预算-第M章.md 对应拍
可复现：同一输入连跑两次，prompt_sha256 必须相同。
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

PROMPTS = Path(r"D:\NovelApp\prompts")


def read(p):
    p = Path(p)
    return p.read_text(encoding="utf-8") if p.exists() else None


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def anchor_positive(anchor_text):
    """只取「正样本示范文本」到「负示范」之间的原文，一字不改。"""
    if not anchor_text:
        return None
    m = re.search(r"^##\s*正样本示范文本(.*?)^##\s*负示范", anchor_text, re.S | re.M)
    return m.group(1).strip() if m else None


def budget_beat(budget_text, beat_no):
    if not budget_text:
        return None, None
    model = None
    m = re.search(r"重点章：.*?→\s*`([^`]+)`", budget_text)
    if m:
        model = m.group(1)
    for ln in budget_text.splitlines():
        if not ln.startswith("|"):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) < 6 or not c[0].isdigit() or int(c[0]) != beat_no:
            continue
        return dict(summary=c[1], words=c[2], intensity=c[3], must=c[4], mustnot=c[5]), model
    return None, model


def chapter_position(outline_text, chapter):
    if not outline_text:
        return "（大纲缺失）"
    for ln in outline_text.splitlines():
        if not ln.startswith("|"):
            continue
        c = [x.replace("*", "").strip() for x in ln.strip().strip("|").split("|")]
        if len(c) >= 6 and c[0].isdigit() and int(c[0]) == chapter:
            return f"第 {chapter} 章 · 强度 {c[1]} · 钩子 {c[2]} · 变化 {c[3]} · 场次 {c[4]} · {c[5]}"
    return f"第 {chapter} 章（大纲无记录）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--style", required=True)
    ap.add_argument("--requirement", required=True)
    ap.add_argument("--beat", type=int, default=1)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    book = Path(args.book)
    missing = []

    style_t = read(PROMPTS / "style" / f"{args.style}.md")
    if not style_t:
        missing.append(f"prompts/style/{args.style}.md")
    req_t = read(PROMPTS / "requirement" / f"{args.requirement}.md")
    if not req_t:
        missing.append(f"prompts/requirement/{args.requirement}.md")
    tpl = read(PROMPTS / "write" / "chapter-beat.md")
    if not tpl:
        missing.append("prompts/write/chapter-beat.md")
    anchor_t = read(book / "meta" / "style-anchor.md")
    positive = anchor_positive(anchor_t)
    if not positive:
        missing.append(f"{book}/meta/style-anchor.md 的「正样本示范文本」")
    budget_t = read(book / "策划" / f"预算-第{args.chapter}章.md")
    beat, model = budget_beat(budget_t, args.beat)
    if not beat:
        missing.append(f"{book}/策划/预算-第{args.chapter}章.md 第 {args.beat} 拍（先跑 chapter_budget.py）")

    if missing:
        print("fail-closed：以下输入缺失，不渲染任务单")
        for m in missing:
            print("  - " + m)
        return 1

    outline_t = read(book / "大纲" / "00-第一卷大纲与章纲.md")
    never = "仿佛、宛如、不禁、若有所思、深邃、眼眸、勾勒、交织、弥漫、氤氲、彷徨、震撼、淋漓、悄然；" \
            "禁「不是……而是……」；禁破折号；禁金句/升华收尾；禁止旁白否定式陈述"

    ctx_files = [
        f"prompts/style/{args.style}.md",
        f"prompts/requirement/{args.requirement}.md",
        "prompts/write/chapter-beat.md",
        "meta/style-anchor.md",
        f"策划/预算-第{args.chapter}章.md",
    ]
    ctx_text = "\n".join((read(book / f) or "") for f in ctx_files)

    prompt = (tpl
              .replace("{{style}}", style_t.strip())
              .replace("{{requirement}}", req_t.strip())
              .replace("{{beat_summary}}", beat["summary"])
              .replace("{{beat_words}}", beat["words"])
              .replace("{{beat_intensity}}", beat["intensity"])
              .replace("{{must_happen}}", beat["must"])
              .replace("{{must_not_happen}}", beat["mustnot"])
              .replace("{{style_anchor_samples}}", positive)
              .replace("{{never}}", never)
              .replace("{{chapter_position}}", chapter_position(outline_t, args.chapter)))

    out_md = book / "策划" / f"任务单-第{args.chapter}章-第{args.beat}拍.md"
    out_json = book / "策划" / f"生成记录-第{args.chapter}.json"
    out_md.parent.mkdir(parents=True, exist_ok=True)

    prompt_hash = sha(prompt)
    record = dict(
        chapter=args.chapter, beat=args.beat,
        model=model or "deepseek/deepseek-flash",
        style=args.style, requirement=args.requirement,
        context_files=ctx_files,
        context_sha256=sha(ctx_text),
        prompt_sha256=prompt_hash,
        prompt_chars=len(prompt),
        prompt_tokens=0, completion_tokens=0,
    )

    old = read(out_json)
    same = bool(old) and json.loads(old).get("prompt_sha256") == prompt_hash and out_md.exists()
    if not out_md.exists():
        out_md.write_text(prompt, encoding="utf-8")
    out_json.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"style={args.style} requirement={args.requirement} beat={args.beat}")
    print(f"model={record['model']}")
    print(f"prompt_sha256={prompt_hash}")
    print(f"context_sha256={record['context_sha256']}")
    print(f"chars={len(prompt)}")
    print(f"任务单: {out_md}")
    print(f"生成记录: {out_json}")
    print("可复现: " + ("unchanged（同输入，sha256 相同）" if same else "first-render"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
