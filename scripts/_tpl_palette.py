# -*- coding: utf-8 -*-
"""抄 11 个模板的配色（青绿/暖黄/陶土/灰绿），UI 元素恢复圆角，正文纸保持直角。"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\040-theme.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()

OLD = """  "--nvl-desk: #F8FAF9;",
  "--nvl-paper: #F0F2F1;",
  "--nvl-paper-2: #F4F6F5;",
  "--nvl-paper-3: #EFF1F0;",
  "--nvl-rule: #DFE4E2;",
  "--nvl-ink: #171A19;",
  "--nvl-ink-2: #313433;",
  "--nvl-ink-3: #5A5D5C;",
  "--nvl-accent: #8CA49A;",
  "--nvl-annot: #A8836A;","""

NEW = """/* 抄自 11 个模板的配色（2026-11-09 统计得出）：
   暖白背景 #FAF8F5 · 青绿主色 #4A9D9A · 暖黄 #E8B86D · 陶土 #C17767 · 灰绿 #6B8E8E */
const TOKENS_LIGHT = [
  "--nvl-desk: #FAF8F5;",
  "--nvl-paper: #FFFFFF;",
  "--nvl-paper-2: #F6F3EE;",
  "--nvl-paper-3: #EFEAE3;",
  "--nvl-rule: #E4DFD7;",
  "--nvl-ink: #1F2421;",
  "--nvl-ink-2: #4A5049;",
  "--nvl-ink-3: #8A8F88;",
  "--nvl-accent: #4A9D9A;",
  "--nvl-warm: #E8B86D;",
  "--nvl-clay: #C17767;",
  "--nvl-sage: #6B8E8E;",
  "--nvl-annot: #C17767;","""

if OLD not in s:
    print("anchor missing")
    sys.exit(1)
s = s.replace(OLD, NEW, 1)

# 连带：accent-ink 用深色（青绿底上放白字通透，放深墨更稳）
s = s.replace('  "--nvl-accent-ink: #1A2421;",', '  "--nvl-accent-ink: #FFFFFF;",', 1)
s = s.replace('  "--nvl-accent-soft: rgba(140, 164, 154, 0.18);",', '  "--nvl-accent-soft: rgba(74, 157, 154, 0.12);",', 1)
s = s.replace('  "--nvl-focus: #6E8C7F;",', '  "--nvl-focus: #4A9D9A;",', 1)
s = s.replace('  "--nvl-bg: #F8FAF9;",', '  "--nvl-bg: #FAF8F5;",', 1)
s = s.replace('  "--nvl-scrim: rgba(12, 13, 16, 0.42);",', '  "--nvl-scrim: rgba(31, 36, 33, 0.42);",', 1)

# UI 元素圆角恢复（8/12px）；正文纸保持直角
s = s.replace('  "--nvl-radius-1: 0;"', '  "--nvl-radius-1: 8px;"')
s = s.replace('  "--nvl-radius-2: 0;"', '  "--nvl-radius-2: 12px;"')
s = s.replace('  "--nvl-radius-3: 0;"', '  "--nvl-radius-3: 16px;"')

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("template palette applied")