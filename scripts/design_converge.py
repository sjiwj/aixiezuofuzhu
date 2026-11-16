# -*- coding: utf-8 -*-
"""把散落的字号/圆角/阴影收敛到 token。默认 dry-run，加 --apply 才写。

复刻 Claude Design 第三段的「让后续都 on-system」：
不是靠人记得，是靠脚本把所有离群值拉回规范。
"""
import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
P = os.path.join(ROOT, "plugin", "lib", "src", "parts", "040-theme.js")

# 字号收敛表（目标 token 名 -> 现有 token 定义）
FONT_MAP = [
    ("10.5px", "var(--nvl-text-2xs)"),
    ("11px",   "var(--nvl-text-xs)"),
    ("11.5px", "var(--nvl-text-xs)"),
    ("12px",   "var(--nvl-text-xs)"),
    ("12.5px", "var(--nvl-text-xs)"),
    ("13px",   "var(--nvl-text-sm)"),
    ("15px",   "var(--nvl-text-md)"),
    ("16.5px", "var(--nvl-text-body)"),
    ("18px",   "var(--nvl-text-xl)"),
    ("20px",   "var(--nvl-text-xl)"),
]
# 只替换 font-size: 后面的值（避免误伤 padding/margin 里的数字）
FONT_RE = re.compile(r"(font-size\s*:\s*)([0-9.]+px)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    s = io.open(P, encoding="utf-8").read()
    table = dict(FONT_MAP)
    changes = []

    def repl(m):
        head, val = m.group(1), m.group(2)
        if val in table:
            new = table[val]
            if new != val:
                changes.append((val, new))
            return head + new
        return m.group(0)

    out = FONT_RE.sub(repl, s)

    # 硬编码圆角收敛（只处理常见离群值，不动 0 和 100%/50%）
    RADIUS_MAP = {"5px": "var(--nvl-radius-2)", "6px": "var(--nvl-radius-2)",
                  "10px": "var(--nvl-radius-3)", "12px": "var(--nvl-radius-3)",
                  "16px": "var(--nvl-radius-3)"}
    R_RE = re.compile(r"(border-radius\s*:\s*)([0-9.]+px)(\s*;)")

    def rrepl(m):
        head, val, tail = m.group(1), m.group(2), m.group(3)
        if val in RADIUS_MAP:
            changes.append(("radius " + val, RADIUS_MAP[val]))
            return head + RADIUS_MAP[val] + tail
        return m.group(0)

    out = R_RE.sub(rrepl, out)

    print("=" * 60)
    print("收敛预览" + ("（apply）" if a.apply else "（dry-run，不写盘）"))
    print("=" * 60)
    from collections import Counter
    c = Counter(changes)
    for (old, new), n in c.most_common():
        print("  %-16s -> %-26s x%d" % (old, new, n))
    print("-" * 60)
    print("合计替换 %d 处" % len(changes))

    if a.apply and changes:
        tmp = P + ".tmp"
        io.open(tmp, "w", encoding="utf-8", newline="").write(out)
        os.replace(tmp, P)
        print("已写入 " + P)
    elif changes:
        print("加 --apply 才写盘")
    return 0


if __name__ == "__main__":
    sys.exit(main())
