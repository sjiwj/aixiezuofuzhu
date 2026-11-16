# -*- coding: utf-8 -*-
"""按 Laper 截图的实测配色重写浅色 token。"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\040-theme.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()

OLD = """const TOKENS_LIGHT = [
  "--nvl-paper: #FFFFFF;",
  "--nvl-desk: #F7F7F8;",
  "--nvl-paper-2: #F7F7F8;",
  "--nvl-paper-3: #EFEFF1;",
  "--nvl-rule: #E4E4E7;",
  "--nvl-ink: #18181B;",
  "--nvl-ink-2: #52525B;",
  "--nvl-ink-3: #A1A1AA;",
  "--nvl-accent: #18181B;",
  "--nvl-annot: #B08256;","""

NEW = """/* Laper 实测配色（2026-11-08 从截图取色，不是猜的）：
   外层 #F8FAF9 · 纸 #F0F2F1（比背景略深）· 文字 #171A19 · accent #8CA49A 灰绿 */
const TOKENS_LIGHT = [
  "--nvl-desk: #F8FAF9;",
  "--nvl-paper: #F0F2F1;",
  "--nvl-paper-2: #F4F6F5;",
  "--nvl-paper-3: #EFF1F0;",
  "--nvl-rule: #DFE4E2;",
  "--nvl-ink: #171A19;",
  "--nvl-ink-2: #313433;",
  "--nvl-ink-3: #5A5D5C;",
  "--nvl-accent: #8CA49A;",
  "--nvl-annot: #A8836A;","""

if OLD not in s:
    print("anchor missing")
    sys.exit(1)
s = s.replace(OLD, NEW, 1)

# accent-ink 要跟着变（灰绿上放深字）
s = s.replace('  "--nvl-accent-ink: #ffffff;",', '  "--nvl-accent-ink: #1A2421;",', 1)
s = s.replace('  "--nvl-accent-soft: rgba(24, 24, 27, 0.06);",', '  "--nvl-accent-soft: rgba(140, 164, 154, 0.18);",', 1)
s = s.replace('  "--nvl-focus: #2563EB;",', '  "--nvl-focus: #6E8C7F;",', 1)
s = s.replace('  "--nvl-bg: #F7F7F8;",', '  "--nvl-bg: #F8FAF9;",', 1)

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("laper palette applied")