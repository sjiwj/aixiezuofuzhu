# -*- coding: utf-8 -*-
import io
p = r"D:\NovelApp\scripts\debt_view.py"
s = io.open(p, encoding="utf-8").read()
# 把状态缺口从 items 里撤出，单独返回
old = '    items = []\n    for g in gaps[:2]:'
i = s.find(old)
if i < 0:
    print("anchor missing"); raise SystemExit(1)
j = s.find("    for p in prom[:4]:", i)
if j < 0:
    print("anchor2 missing"); raise SystemExit(1)
s = s[:i] + "    items = []" + chr(10) + s[j:]

# 返回值加 state_gaps
s = s.replace('            "summary": "\u8fd9\u4e00\u7ae0\u5fc5\u987b\u52a8 %d \u6761\uff0c\u5176\u4f59 %d \u6761\u662f\u80cc\u666f" % (len(top), max(0, len(items) - len(top)))}',
              '            "state_gaps": gaps[:5],' + chr(10) +
              '            "summary": "\u8fd9\u4e00\u7ae0\u5fc5\u987b\u52a8 %d \u6761\uff0c\u5176\u4f59 %d \u6761\u662f\u80cc\u666f" % (len(top), max(0, len(items) - len(top)))}')

# 输出加一组
s = s.replace('    print("-" * 60)\n    return 0',
              '    if rep.get("state_gaps"):' + chr(10) +
              '        print("-" * 60)' + chr(10) +
              '        print("\u53e6\u5916\uff0c\u8d44\u6599\u4e0a\u6709 %d \u5904\u7a7a\u7740\uff08\u5199\u4e4b\u524d\u5efa\u8bae\u8865\uff09\uff1a" % len(rep["state_gaps"]))' + chr(10) +
              '        for g in rep["state_gaps"][:5]:' + chr(10) +
              '            print("   %s \u7684\u300c%s\u300d\u6ca1\u8bb0" % (g["who"], g["field"]))' + chr(10) +
              '    print("-" * 60)' + chr(10) +
              '    return 0')

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("state gaps separated")