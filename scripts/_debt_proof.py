# -*- coding: utf-8 -*-
"""读债条去卡片化：改成校样纸的批注形态（左侧竖线 + 缩进，无背景无圆角无阴影）"""
import io, os, sys
P = r"D:\NovelApp\plugin\lib\src\parts\040-theme.js"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "/* 校样批注" in s:
    print("ALREADY"); sys.exit(0)

OLD = '''		".nvl-debt { display: flex; flex-direction: column; gap: 2px; margin: 0 12px 6px; padding: 6px 10px; border-radius: 8px; background: var(--nvl-paper-2); border-left: 2px solid var(--nvl-accent); }",
		".nvl-debt__head { font-size: 11px; color: var(--nvl-ink-3); margin-bottom: 2px; }",'''

NEW = '''		/* 校样批注：没有卡片、没有圆角、没有阴影。
		   左侧一根细线当批注栏，正文缩进对齐——校样纸上的批注就这个形态。
		   参考 docs/design/视觉设计计划-20261108.md */
		".nvl-debt { display: flex; flex-direction: column; gap: 1px; margin: 2px 0 10px; padding: 2px 0 2px 14px; border-left: 2px solid var(--nvl-rule); background: none; border-radius: 0; }",
		".nvl-debt__head { font-size: 11.5px; color: var(--nvl-ink-2); margin-bottom: 3px; letter-spacing: .01em; }",'''

if OLD not in s:
    print("anchor missing"); sys.exit(1)
s = s.replace(OLD, NEW, 1)

# kind 不再用 accent（强调色不该满屏）
s = s.replace('".nvl-debt__kind { font-size: 10.5px; color: var(--nvl-accent);',
              '".nvl-debt__kind { font-size: 10.5px; color: var(--nvl-ink-3);')
# 行距收紧，字号提一点
s = s.replace('column-gap: 10px; font-size: 12px; line-height: 1.8; }',
              'column-gap: 12px; font-size: 12.5px; line-height: 1.75; font-variant-numeric: tabular-nums; }')

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("debt -> proof-sheet annotation")