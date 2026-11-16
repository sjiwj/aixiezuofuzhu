# -*- coding: utf-8 -*-
"""统计 11 个模板的设计模式：背景色 / 圆角 / 阴影 / 间距 / 字号"""
import io, os, re, collections

W = r"D:\NovelApp\_tmp\design-templates"
files = []
for root, dirs, fs in os.walk(W):
    for f in fs:
        if f.endswith(".tsx"):
            files.append(os.path.join(root, f))
print("tsx files:", len(files))

bg = collections.Counter()
radius = collections.Counter()
shadow = collections.Counter()
gap = collections.Counter()
textbg = collections.Counter()

for p in files:
    s = io.open(p, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"bg-\[#[0-9a-fA-F]{6}\]", s):
        bg[m.group(0)] += 1
    for m in re.finditer(r"rounded-[a-z0-9\[\]]+", s):
        radius[m.group(0)] += 1
    for m in re.finditer(r"shadow-[a-z0-9\[\]/\.]+", s):
        shadow[m.group(0)] += 1
    for m in re.finditer(r"(?:gap|p|px|py|m|mb|mt)-\d{1,2}", s):
        gap[m.group(0)] += 1

print("\n=== 背景色 top 15 ===")
for k, n in bg.most_common(15):
    print("  %-20s %d" % (k, n))

print("\n=== 圆角 top 10 ===")
for k, n in radius.most_common(10):
    print("  %-24s %d" % (k, n))

print("\n=== 阴影 top 10 ===")
for k, n in shadow.most_common(10):
    print("  %-30s %d" % (k, n))

print("\n=== 间距 top 12 ===")
for k, n in gap.most_common(12):
    print("  %-10s %d" % (k, n))
