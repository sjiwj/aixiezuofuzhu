#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布前总检：转 public / 发版之前跑一遍，全 PASS 才允许公开。

检查项：
  SECRET     密钥形态（sk- / github_pat_ / ghp_ / gho_ / AKIA / 私钥 / 明文口令赋值）
  LOCALPATH  本机用户目录（C:\\Users\\<名字>）—— 安装路径 D:\\NovelApp 属正常示例，不拦
  CUSTOMER   "客户《…》" 且不是占位符
  PROJECT    projects/<中文>/ 或 --book <中文> 且不在白名单
  PROSE      scripts/fixtures/*.md 连续中文 ≥60 字且未标注「示例」
  FILE       凭据/数据库类文件名
  IGNORE     .gitignore 必须覆盖用户数据目录

用法：
  python scripts/_pre_publish_check.py            # 查 main + 所有 tag
  python scripts/_pre_publish_check.py --rev <sha>
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BINARY = ('.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip', '.exe', '.dll',
          '.pyd', '.so', '.pyc', '.woff', '.woff2', '.ttf', '.db', '.sqlite', '.bin')

SECRETS = [
    (r'sk-[A-Za-z0-9_-]{16,}', 'sk- 形式密钥'),
    (r'github_pat_[A-Za-z0-9_]{20,}', 'fine-grained PAT'),
    (r'ghp_[A-Za-z0-9]{20,}', 'classic PAT'),
    (r'gho_[A-Za-z0-9]{20,}', 'OAuth token'),
    (r'AKIA[0-9A-Z]{16}', 'AWS access key'),
    (r'BEGIN [A-Z ]*PRIVATE KEY', '私钥'),
    (r'(?i)(api[_-]?key|secret|password)\s*[:=]\s*["\'][A-Za-z0-9_\-]{16,}["\']', '明文口令/密钥赋值'),
]

# 只拦真实用户名目录；D:\NovelApp 这类安装路径示例不拦
LOCAL_PATHS = [
    (r'C:\\\\Users\\\\[A-Za-z0-9_.\-]{2,}', 'C 盘用户目录'),
    (r'C:/Users/[A-Za-z0-9_.\-]{2,}', 'C 盘用户目录'),
]

CJK = re.compile(r'[\u4e00-\u9fff]')
ALLOW = ('<书名>', '示例', '测试', '不存在的项目', '拆书样本', '样本', '演示',
         '_errtest', '_authtest', '_pocbook', '_apitest', '_poc',
         '必填', '书名', '指定的', '临时书', '中文名')
CJK_NAME = r'[\u4e00-\u9fff][\u4e00-\u9fff0-9A-Za-z_\-]{1,15}'

SKIP_SELF = ('scripts/_pre_publish_check.py', 'scripts/_verify_no_private_data.py')


def git(*args):
    return subprocess.run(['git', '-C', ROOT] + list(args),
                          capture_output=True, text=True).stdout


def allowed(name):
    return any(a in name for a in ALLOW)


def longest_cjk_run(text):
    best = cur = 0
    for ch in text:
        if CJK.match(ch):
            cur += 1
            best = max(best, cur)
        elif ch not in '，。、；：！？""''（）《》…—':
            cur = 0
    return best


def check_rev(rev, label):
    files = [f for f in git('ls-tree', '-r', rev, '--name-only').splitlines() if f.strip()]
    issues = []
    for f in files:
        if f.lower().endswith(BINARY) or f in SKIP_SELF:
            continue
        body = git('show', '%s:%s' % (rev, f))
        if not body:
            continue
        for pat, what in SECRETS:
            m = re.search(pat, body)
            if m:
                issues.append(('SECRET', f, '%s: %s…' % (what, m.group(0)[:10])))
        for pat, what in LOCAL_PATHS:
            m = re.search(pat, body)
            if m:
                issues.append(('LOCALPATH', f, '%s: %s' % (what, m.group(0)[:24])))
        m = re.search(r'客户《([^》]{0,30})》', body)
        if m and not allowed(m.group(1)):
            issues.append(('CUSTOMER', f, m.group(0)))
        m = re.search(r'projects/(' + CJK_NAME + r')/', body)
        if m and not allowed(m.group(1)):
            issues.append(('PROJECT', f, m.group(0)))
        m = re.search(r'--book\s+["\']?(' + CJK_NAME + r')', body)
        if m and not allowed(m.group(1)):
            issues.append(('PROJECT', f, '--book ' + m.group(1)))
        if f.startswith('scripts/fixtures/') and f.endswith('.md') and '示例' not in body:
            run = longest_cjk_run(body)
            if run >= 60:
                issues.append(('PROSE', f, '连续中文 %d 字，未标注「示例」' % run))
        if re.search(r'(user_token|\.netrc|id_rsa|\.pem$|\.p12$|credential|\.env$)', f):
            issues.append(('FILE', f, '不应入库的凭据类文件'))

    print('\n[%s] %s  （%d 文件）' % (label, rev[:10], len(files)))
    if not issues:
        print('  PASS')
        return 0
    seen = set()
    for code, f, detail in issues:
        if (code, f) in seen:
            continue
        seen.add((code, f))
        print('  FAIL  %-10s %-44s %s' % (code, f, detail))
    return len(seen)


def main():
    revs = [('main', 'HEAD')] + [('tag ' + t, t) for t in git('tag').split()]
    if '--rev' in sys.argv:
        revs = [('explicit', sys.argv[sys.argv.index('--rev') + 1])]

    total = 0
    for label, rev in revs:
        total += check_rev(rev, label)

    print('\n=== .gitignore 覆盖 ===')
    gi = open(os.path.join(ROOT, '.gitignore'), encoding='utf-8').read()
    for n in ('projects/', 'samples/', 'reports/', 'data/*', 'user_token.json'):
        ok = n in gi
        print('  %s  %s' % ('PASS' if ok else 'FAIL', n))
        if not ok:
            total += 1

    print('\n结果: %s（问题 %d）' % ('PASS' if total == 0 else 'FAIL', total))
    return 0 if total == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
