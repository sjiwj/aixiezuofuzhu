# -*- coding: utf-8 -*-
"""阴影收敛：把各种一次性 box-shadow 拉到 sh-1 / sh-2。"""
import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
P = os.path.join(ROOT, "plugin", "lib", "src", "parts", "040-theme.js")

# 按「浮起高度」归类，不是按字符串相似
SHADOW_MAP = [
    (r"0 1px 2px rgba\(0,0,0,\.0[0-9]\)",              "var(--nvl-shadow-1)"),
    (r"0 1px 2px rgba\(0, 0, 0, 0\.0[0-9]\)",          "var(--nvl-shadow-1)"),
    (r"0 [0-9]+px [0-9]+px rgba\(0, ?0, ?0, ?\.1[0-9]?\)", "var(--nvl-shadow-2)"),
    (r"0 [0-9]+px [0-9]+px rgba\(0, ?0, ?0, ?0\.[2-9][0-9]?\)", "var(--nvl-shadow-2)"),
    (r"0 -[0-9]+px [0-9]+px rgba\(0, ?0, ?0, ?,? ?0?\.[0-9]+\)", "var(--nvl-shadow-2)"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    s = io.open(P, encoding="utf-8").read()
    S_RE = re.compile(r"(box-shadow\s*:\s*)([^;\"]+)(;)")
    n = [0]

    def repl(m):
        head, val, tail = m.group(1), m.group(2).strip(), m.group(3)
        if val.startswith("var(--nvl-shadow") or val == "none" or val.startswith("inset"):
            return m.group(0)
        # 判断「贴着」还是「浮起来」：模糊半径 >= 8px 算浮起
        mm = re.search(r"0(?:px)?\s+(-?[0-9]+)px\s+([0-9]+)px", val)
        if mm:
            blur = int(mm.group(2))
            new = "var(--nvl-shadow-2)" if blur >= 8 else "var(--nvl-shadow-1)"
        else:
            new = "var(--nvl-shadow-1)"
        n[0] += 1
        return head + new + tail

    out = S_RE.sub(repl, s)
    print("阴影收敛：" + str(n[0]) + " 处" + ("（已写）" if a.apply else "（dry-run）"))

    if a.apply and n[0]:
        tmp = P + ".tmp"
        io.open(tmp, "w", encoding="utf-8", newline="").write(out)
        os.replace(tmp, P)
    return 0


if __name__ == "__main__":
    sys.exit(main())
