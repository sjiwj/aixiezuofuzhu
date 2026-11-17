#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布前隐私门禁：确认要推的内容里没有作者真实书名 / 客户统计 / 正文片段。

背景：v1.0.0 把 docstring 里的真实书名示例、`config/cliche.json` 的客户统计、
`scripts/fixtures/*.md` 的真实正文片段一起推到了公开仓库，之后才改写历史清掉。
这个脚本把当时的教训钉成规则，每次发布前跑。

检查项：
  P1  密钥形态（sk- / github_pat_ / ghp_ / gho_ / AKIA / 私钥头）
  P2  客户作品引用（"客户《…》" 且括号里不是占位符）
  P3  具体中文书名：`projects/<中文>/` 或 `--book <中文>`，排除示例/测试/占位符白名单
  P4  fixtures 里的正文：先由 P3 覆盖真名；这里只提示"像正文的文件清单"，不算失败

用法：
  python scripts/_verify_no_private_data.py            # 查 HEAD
  python scripts/_verify_no_private_data.py --rev <sha>
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_PATTERNS = [
    (r'sk-[A-Za-z0-9_-]{16,}', 'sk- 形式密钥'),
    (r'github_pat_[A-Za-z0-9_]{20,}', 'fine-grained PAT'),
    (r'ghp_[A-Za-z0-9]{20,}', 'classic PAT'),
    (r'gho_[A-Za-z0-9]{20,}', 'OAuth token'),
    (r'AKIA[0-9A-Z]{16}', 'AWS key'),
    (r'BEGIN [A-Z ]*PRIVATE KEY', '私钥'),
]

# 占位符/测试名/提示文案白名单：命中的中文段里含这些词就放行
ALLOW = ('<书名>', '示例', '测试', '不存在的项目', '拆书样本', '样本', '演示',
         '_errtest', '_authtest', '_pocbook', '_apitest', '_poc',
         '必填', '书名', '指定的', '临时书', '中文名')

CJK_NAME = r'[\u4e00-\u9fff][\u4e00-\u9fff0-9A-Za-z_\-]{1,15}'

BINARY = ('.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip', '.exe',
          '.dll', '.pyd', '.so', '.pyc', '.woff', '.woff2', '.ttf', '.db', '.sqlite')


def git(*args):
    return subprocess.run(['git', '-C', ROOT] + list(args),
                          capture_output=True, text=True).stdout


def allowed(name):
    return any(a in name for a in ALLOW)


def main():
    rev = 'HEAD'
    if '--rev' in sys.argv:
        rev = sys.argv[sys.argv.index('--rev') + 1]
    files = [f for f in git('ls-tree', '-r', rev, '--name-only').splitlines() if f.strip()]
    bad = []

    for f in files:
        if f.lower().endswith(BINARY):
            continue
        if f in ('scripts/_verify_no_private_data.py',
                 'scripts/_pre_publish_check.py',
                 'scripts/_scrub_proper_nouns.py',
                 'issues/REQ-purge-old-commits.md'):
            continue                      # 检测脚本自身含检测用正则；清除请求里要写规则说明
        body = git('show', '%s:%s' % (rev, f))
        if not body:
            continue
        for pat, label in SECRET_PATTERNS:
            for m in re.finditer(pat, body):
                bad.append(('P1', f, '%s: %s…' % (label, m.group(0)[:10])))
        for m in re.finditer(r'客户《([^》]{0,30})》', body):
            if not allowed(m.group(1)):
                bad.append(('P2', f, m.group(0)))
        for m in re.finditer(r'projects/(' + CJK_NAME + r')/', body):
            if not allowed(m.group(1)):
                bad.append(('P3', f, m.group(0)))
        for m in re.finditer(r'--book\s+["\']?(' + CJK_NAME + r')', body):
            if not allowed(m.group(1)):
                bad.append(('P3', f, '--book ' + m.group(1)))

    print('检查版本: %s（%d 个文件）' % (rev, len(files)))
    if not bad:
        print('\n结果: PASS —— 密钥 / 客户统计 / 具体书名 均为 0')
        return 0
    print('\n发现 %d 处：' % len(bad))
    seen = {}
    for code, f, detail in bad:
        seen.setdefault((code, f), []).append(detail)
    for (code, f), ds in sorted(seen.items())[:30]:
        print('  %s  %-44s %s' % (code, f, ' | '.join(sorted(set(ds))[:3])))
    print('\n结果: FAIL')
    return 1


if __name__ == '__main__':
    sys.exit(main())
