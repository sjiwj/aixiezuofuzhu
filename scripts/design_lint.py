# -*- coding: utf-8 -*-
"""设计系统 lint：检查代码是否符合 design-system.json。

复刻 Claude Design 第三段（引用 + 校验）：规范不是写在文档里给人看的，
是每次改完能被机器检查的。

用法：
    python scripts/design_lint.py            # 全部检查
    python scripts/design_lint.py --strict   # 有违规就 exit 1
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PARTS = os.path.join(ROOT, "plugin", "lib", "src", "parts")
DS = os.path.join(ROOT, "design-system.json")


def load_ds():
    with io.open(DS, encoding="utf-8") as f:
        return json.load(f)


def read_parts():
    out = {}
    if not os.path.isdir(PARTS):
        return out
    for fn in sorted(os.listdir(PARTS)):
        if fn.endswith(".js"):
            with io.open(os.path.join(PARTS, fn), encoding="utf-8") as f:
                out[fn] = f.read()
    return out


def lines_of(text):
    return text.split(chr(10))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    ds = load_ds()
    ok_radius = set(v["value"] for v in ds["radius"].values())
    ok_text = set(v["value"] for v in ds["text"].values())
    ok_shadow = set(v["value"] for v in ds["shadow"].values()) | {"none"}
    ok_color_tokens = set(ds["color"].keys())

    sources = read_parts()
    issues = []

    for fn, text in sources.items():
        for i, line in enumerate(lines_of(text), 1):
            is_token_def = "--nvl-" in line and re.search(r'"--nvl-', line)
            stripped = line.strip()
            # 注释行不算违规（文件头的示例值、说明文字）
            if stripped.startswith("/*") or stripped.startswith("*") or stripped.startswith("//"):
                continue

            # 1 圆角
            for m in re.finditer(r'border-radius\s*:\s*([^;"}]+)', line):
                v = m.group(1).strip()
                if v.startswith("var(--nvl-radius"):
                    continue
                if is_token_def:
                    continue
                if v not in ok_radius:
                    issues.append((fn, i, "radius", v, "只能用 2px/4px/8px/999px（或 var(--nvl-radius-N)）"))

            # 2 字号
            for m in re.finditer(r'font-size\s*:\s*([^;"}]+)', line):
                v = m.group(1).strip()
                if v.startswith("var(--nvl-text"):
                    continue
                if is_token_def:
                    continue
                if v not in ok_text:
                    issues.append((fn, i, "font-size", v, "只能用 10/11/12.5/14/15/16.5/20px（或 var(--nvl-text-*)）"))

            # 3 阴影
            for m in re.finditer(r'box-shadow\s*:\s*([^;"}]+)', line):
                v = m.group(1).strip()
                if v.startswith("var(--nvl-shadow"):
                    continue
                if is_token_def:
                    continue
                if v not in ok_shadow:
                    issues.append((fn, i, "shadow", v[:48], "只能用 sh-1 / sh-2 / none"))

            # 4 硬编码颜色
            if not is_token_def:
                for m in re.finditer(r'(#[0-9a-fA-F]{6}\b|rgba?\([^)]{5,60}\))', line):
                    v = m.group(1)
                    if v in ("rgba(0,0,0,0)", "rgba(0, 0, 0, 0)"):
                        continue
                    issues.append((fn, i, "color", v, "颜色必须用 var(--nvl-*)"))

    print("=" * 70)
    print("设计系统 lint   （对照 design-system.json）")
    print("=" * 70)
    if not issues:
        print("没有违规。")
        return 0

    by_kind = {}
    for it in issues:
        by_kind.setdefault(it[2], []).append(it)

    for kind in ("radius", "font-size", "shadow", "color"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        print("")
        print("%s：%d 处" % (kind, len(items)))
        seen = set()
        for fn, i, k, v, hint in items:
            key = (fn, v)
            if key in seen:
                continue
            seen.add(key)
            print("  %-14s:%-5d %-22s %s" % (fn, i, v[:20], hint))

    print("")
    print("-" * 70)
    total = len(issues)
    print("合计 %d 处违规" % total)
    if a.strict and total:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
