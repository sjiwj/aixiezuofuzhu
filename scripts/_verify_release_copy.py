#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布文案校验（v1.0.1 第 5 项）。

文案里的数字最容易编造，所以逐项对账：
  A  版本：VERSION == 1.0.1，且 Release 说明里写的是 1.0.1
  B  指标：文案引用的每个核心数字，必须能在 README 或 CHANGELOG 里找到原文
  C  功能名：Release 说明提到的字段/环境变量/函数，必须在代码里真实存在
  D  地址：文案里的仓库地址与 git remote 一致
  E  形态：三份首帖各自具备该平台必需的段落（钩子/标签/CTA 等）

用法：python scripts/_verify_release_copy.py
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE = os.path.join(ROOT, 'release')
POSTS = os.path.join(RELEASE, 'posts')

# 文案可以引用的核心指标（全部来自 README「它凭什么」与实测行）
CORE_NUMBERS = ['0.275', '0.043', '0.183', '0.273', '1.27', '0.00', '0.69', '0.72',
                '859', '860', '969', '2025', '10.9', '15.1', '10.5', '9.9',
                '17.2', '22.6', '16.4', '12.1', '2795', '3418', '154', '22.2', '13.6',
                '0.178', '109']

# Release 说明里必须真实存在的实现线索
CODE_ANCHORS = [
    ('core/server.py', 'shipped_stale'),
    ('core/server.py', 'NOVELAPP_ALLOW_HOSTS'),
    ('core/server.py', 'def safe_rel'),
    ('core/server.py', 'def check_chapter_outline'),
    ('core/errors.py', 'def human'),
    ('web/index.html', '__NVL_TOKEN__'),
]

POST_REQUIREMENTS = {
    'zhihu-01.md': ['结论', '0.043', '3418', 'github.com/sjiwj/jy', '标签'],
    'xiaohongshu-01.md': ['标题', '0.043', '0.00', '标签', 'sjiwj/jy'],
    'bilibili-01.md': ['口播', '分镜', '0.043', '0.178', 'github.com/sjiwj/jy'],
}


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def main():
    bad = 0

    def check(name, ok, detail=''):
        nonlocal bad
        if not ok:
            bad += 1
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name, ('  ' + detail) if detail else ''))

    # A 版本
    version = read(os.path.join(ROOT, 'VERSION')).strip()
    check('A VERSION == 1.0.1', version == '1.0.1', 'got=%s' % version)
    rel_path = os.path.join(RELEASE, '1.0.1.md')
    check('A Release 说明存在', os.path.isfile(rel_path), rel_path)
    rel = read(rel_path) if os.path.isfile(rel_path) else ''
    check('A 标题写 1.0.1', 'v1.0.1' in rel or '1.0.1' in rel)

    # B 指标溯源：README + CHANGELOG + 已有文稿（2795/3418 这两个数出自 posts/01 的真实记录）
    corpus = (read(os.path.join(ROOT, 'README.md')) + read(os.path.join(ROOT, 'CHANGELOG.md'))
              + read(os.path.join(ROOT, 'posts', '01-第4章为什么崩.md')))
    # 原文写的是 "2,795"（带千分位），对账时统一去掉逗号再比
    corpus_norm = corpus.replace(',', '')
    missing_in_repo = [n for n in CORE_NUMBERS if n not in corpus_norm]
    check('B 核心数字都能在 README/CHANGELOG/文稿 找到', not missing_in_repo,
          '缺=%s' % missing_in_repo)

    posts = {}
    for name in POST_REQUIREMENTS:
        p = os.path.join(POSTS, name)
        exists = os.path.isfile(p)
        check('E 文案存在 %s' % name, exists)
        posts[name] = read(p) if exists else ''

    all_copy = rel + ''.join(posts.values())
    # 文案里出现的核心数字，逐个反查仓库
    used = [n for n in CORE_NUMBERS if n in all_copy]
    check('B 文案至少引用 5 个核心数字', len(used) >= 5, 'used=%d %s' % (len(used), used[:8]))
    orphan = [n for n in used if n not in corpus_norm]
    check('B 引用的数字无编造', not orphan, 'orphan=%s' % orphan)

    # 每个平台各自的硬要素
    for name, needles in POST_REQUIREMENTS.items():
        lack = [x for x in needles if x not in posts[name]]
        check('E %s 要素齐' % name, not lack, '缺=%s' % lack)

    # C 代码锚点
    for path, needle in CODE_ANCHORS:
        full = os.path.join(ROOT, path)
        ok = os.path.isfile(full) and needle in read(full)
        check('C 代码里有 %s::%s' % (path, needle), ok)

    # C' Release 说明提到的关键行为词，必须在文案里出现（防止说明漏项）
    for word in ['Host', 'Origin', 'shipped_stale', 'NOVELAPP_ALLOW_HOSTS', 'force=true']:
        check('C Release 说明覆盖 %s' % word, word in rel)

    # D 地址一致
    remote = subprocess.run(['git', '-C', ROOT, 'remote', 'get-url', 'origin'],
                            capture_output=True, text=True).stdout.strip()
    remote_norm = re.sub(r'\.git$', '', remote)
    check('D 仓库地址一致', remote_norm and remote_norm in all_copy,
          'remote=%s' % remote_norm)
    # D 地址一致（小红书不给外链，用「GitHub 搜 sjiwj/jy」）
    check('D 小红书给出可检索的仓库名', 'sjiwj/jy' in posts.get('xiaohongshu-01.md', ''))

    # F 12 周判据可算、可落盘
    plan_path = os.path.join(RELEASE, 'plan-12w.md')
    check('F 12 周计划存在', os.path.isfile(plan_path))
    plan = read(plan_path) if os.path.isfile(plan_path) else ''
    for needle, label in (('150', 'stars 门槛'), ('100', '周活门槛'), ('12 周', '时间窗'),
                          ('砍到两个入口', '不达标处置')):
        check('F 判据含 %s' % label, needle in plan)
    weekly = os.path.join(ROOT, 'issues', 'weekly.md')
    check('F 每周检查表存在', os.path.isfile(weekly))
    if os.path.isfile(weekly):
        w = read(weekly)
        rows = len(re.findall(r'^\|\s*W\d+\s*\|', w, re.M))
        check('F 检查表有 12 行', rows == 12, 'rows=%d' % rows)

    print('\n结果: %s（失败 %d）' % ('PASS' if not bad else 'FAIL', bad))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
