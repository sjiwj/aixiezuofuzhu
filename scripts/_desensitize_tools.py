#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/ 下脚本的 docstring 脱敏（幂等）。

这些脚本的用法示例里写着作者本机路径和真实书名（projects\\<书名>、
章节\\001-第1章-000.md）。入库前必须换成占位符，否则等于把作品名 publish 出去。

用法：python scripts/_desensitize_tools.py [--dry-run]
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (文件, 原文片段, 替换)
PAIRS = [
    ('tools/chapter_budget.py',
     'python D:\\\\NovelApp\\\\tools\\\\chapter_budget.py --book "D:\\\\NovelApp\\\\projects\\\\<书名>" --chapter 2',
     'python tools/chapter_budget.py --book "projects/<书名>" --chapter 2'),
    ('tools/deai_patch.py',
     'python D:\\\\NovelApp\\\\tools\\\\deai_patch.py --file 章节\\\\001-第1章-000.md',
     'python tools/deai_patch.py --file 章节\\\\001-000.md'),
    ('tools/prompt_render.py',
     'python D:\\\\NovelApp\\\\tools\\\\prompt_render.py --book "D:\\\\NovelApp\\\\projects\\\\<书名>"',
     'python tools/prompt_render.py --book "projects/<书名>"'),
]

BAD = ['<书名>', '000']


def main():
    dry = '--dry-run' in sys.argv
    ok = skip = fail = 0
    for rel, old, new in PAIRS:
        path = os.path.join(ROOT, rel)
        src = open(path, encoding='utf-8', newline='').read()
        if new in src and old not in src:
            print('SKIP  已脱敏  %s' % rel)
            skip += 1
            continue
        if src.count(old) != 1:
            print('FAIL  锚点命中 %d 次  %s' % (src.count(old), rel))
            fail += 1
            continue
        if not dry:
            tmp = path + '.tmp-desens'
            with open(tmp, 'w', encoding='utf-8', newline='') as f:
                f.write(src.replace(old, new, 1))
            os.replace(tmp, path)
        print('%s  %s' % ('WOULD' if dry else 'OK', rel))
        ok += 1

    # 收尾检查
    left = []
    for rel, _o, _n in PAIRS:
        txt = open(os.path.join(ROOT, rel), encoding='utf-8').read()
        for b in BAD:
            if b in txt:
                left.append('%s:%s' % (rel, b))
    if left:
        print('\n仍有真实书名：%s' % ', '.join(left))
        fail += 1
    else:
        print('\n真实书名残留：0')

    print('\n结果: applied=%d skipped=%d failed=%d%s' % (ok, skip, fail, '（dry-run）' if dry else ''))
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
