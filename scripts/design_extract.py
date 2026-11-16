# -*- coding: utf-8 -*-
"""从现有 CSS 提取设计系统（复刻 Claude Design 的 /design-sync 思路）。

它做的事和 Claude Design 一样：从代码里抽 tokens，不是让模型编。
输出 design-system.json + 一份体检报告（现实 vs 规范的差距）。
"""
import argparse
import collections
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PARTS = os.path.join(ROOT, "plugin", "lib", "src", "parts")
OUT = os.path.join(ROOT, "design-system.json")


def read_parts():
    if not os.path.isdir(PARTS):
        return {}
    out = {}
    for fn in sorted(os.listdir(PARTS)):
        if fn.endswith(".js"):
            with io.open(os.path.join(PARTS, fn), encoding="utf-8") as f:
                out[fn] = f.read()
    return out


def extract_tokens(sources):
    tokens = {}
    for fn, text in sources.items():
        for m in re.finditer(r'(--nvl-[a-z0-9-]+)\s*:\s*([^;",]{1,80})', text):
            name, val = m.group(1), m.group(2).strip()
            if name not in tokens:
                tokens[name] = {"value": val, "file": fn, "uses": 0}
    for name in tokens:
        n = 0
        for text in sources.values():
            n += len(re.findall(r'var\(' + re.escape(name) + r'\)', text))
        tokens[name]["uses"] = n
    return tokens


def find_hardcoded(sources):
    hits = collections.Counter()
    where = {}
    for fn, text in sources.items():
        for m in re.finditer(r'(#[0-9a-fA-F]{6}|rgba?\([^)]{5,60}\))', text):
            val = m.group(1)
            ls = text.rfind(chr(10), 0, m.start()) + 1
            le = text.find(chr(10), m.start())
            line = text[ls:le if le > 0 else m.start() + 60]
            if '--nvl-' in line:
                continue
            hits[val] += 1
            where.setdefault(val, set()).add(fn)
    return hits, where


def collect(sources, prop):
    seen = collections.Counter()
    for text in sources.values():
        for m in re.finditer(prop + r'\s*:\s*([^;"}]{1,50})', text):
            v = m.group(1).strip()
            if v:
                seen[v] += 1
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    sources = read_parts()
    if not sources:
        print("no source at " + PARTS)
        return 2

    tokens = extract_tokens(sources)
    hard, where = find_hardcoded(sources)
    radii = collect(sources, "border-radius")
    fonts = collect(sources, "font-size")
    shadows = collect(sources, "box-shadow")

    ds = {
        "version": 1,
        "source": "plugin/lib/src/parts/*.js",
        "tokens": tokens,
        "hardcoded_colors": dict(hard.most_common(40)),
        "radii": dict(radii.most_common(30)),
        "font_sizes": dict(fonts.most_common(30)),
        "shadows": dict(shadows.most_common(15)),
    }

    if a.json:
        print(json.dumps(ds, ensure_ascii=False, indent=2))
        return 0

    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(ds, ensure_ascii=False, indent=2))

    print("=" * 66)
    print("设计系统体检  （从代码里抽的，不是手写的）")
    print("=" * 66)
    print("文件：%d 个    token：%d 个" % (len(sources), len(tokens)))
    zero = [k for k, v in tokens.items() if v["uses"] == 0]
    if zero:
        print("  定义了但没人用：%s" % "、".join(zero[:8]))

    print("")
    print("硬编码颜色：%d 种（规范应该 0）" % len(hard))
    for v, n in hard.most_common(8):
        print("  %-32s x%-3d %s" % (v, n, ",".join(sorted(where.get(v, []))[:2])))

    print("")
    print("圆角：%d 种（规范 <= 4）" % len(radii))
    for v, n in radii.most_common(10):
        print("  %-26s x%d" % (v, n))

    print("")
    print("字号：%d 种（规范 <= 7）" % len(fonts))
    for v, n in fonts.most_common(10):
        print("  %-26s x%d" % (v, n))

    print("")
    print("阴影：%d 种（规范 <= 3）" % len(shadows))
    for v, n in shadows.most_common(6):
        print("  %-54s x%d" % (v[:52], n))

    print("-" * 66)
    print("写入：" + OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
