# -*- coding: utf-8 -*-
"""开书前 / 中途的设定自洽检查（闸 1）

用法:
    python core/check_setup.py --book <书名>
    python core/check_setup.py --book <书名> --json

检查六个账本：
  角色卡    第 7/8 节（行为逻辑/语言风格）有没有填
  角色状态  关键字段有没有「未记录 / 未说明」
  世界地图  相对位置表有没有空格、行程是否大量「未定」
  力量体系  典型耗时缺失、战力表不全、金手指边界没写
  时间线    有没有起头、有没有「待确认/待读」
  伏笔      埋了多久没收敛（>30 章）

判定：通过（无待补）/ 有 N 处待补 / 有 M 处矛盾（矛盾优先，exit=2）
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

PLACEHOLDERS = ('待填', '待定', '待确认', '待读', '未明', '未记录', '未说明', '（暂无）', '(暂无)', 'TODO')


def _projects_root():
    """客户数据目录（与 coordinator.projects_root 同一套优先级）。
    2026-11-07 修：原来用 CO.ROOT（程序安装目录），客户数据在 %APPDATA% 时读不到。"""
    try:
        return CO.projects_root()
    except Exception:
        return os.path.join(CO.ROOT, "projects")


def read(p):
    try:
        with open(p, encoding='utf-8-sig') as f:
            return f.read()
    except OSError:
        return ''


def md_rows(text, header_keys):
    """从 md 表格里取行（按表头关键字定位），返回 list[dict]。"""
    lines = text.split('\n')
    out = []
    header = None
    for ln in lines:
        s = ln.strip()
        if not s.startswith('|'):
            header = None if header and out else header
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if header is None:
            if all(any(k in c for c in cells) for k in header_keys):
                header = cells
            continue
        if re.match(r'^\|[\s:\-|]+\|$', s):
            continue
        out.append(dict(zip(header, cells)))
    return out


def check_chars(path):
    issues = []
    text = read(path)
    if not text:
        return [{'level': 'gap', 'file': '角色卡.md', 'item': '文件缺失'}]
    blocks = re.split(r'\n(?=## )', text)
    for b in blocks:
        m = re.match(r'## (.+)', b)
        if not m:
            continue
        name = m.group(1).strip()
        if any(k in name for k in ('用法', '审稿团')) or '## ' in name:
            continue
        for sec, label in (('行为逻辑', '第 7 节 行为逻辑'), ('语言风格', '第 8 节 语言风格')):
            has_sec = sec in b
            filled = has_sec and len(re.sub(r'[\s\-*#\d\.:：()（）]', '', b.split(sec, 1)[1])) > 20
            if not filled:
                issues.append({'level': 'gap', 'file': '角色卡.md',
                               'item': '%s 的「%s」没填' % (name, label)})
    return issues


def check_state(path):
    issues = []
    text = read(path)
    if not text:
        return [{'level': 'gap', 'file': '角色状态.md', 'item': '文件缺失'}]
    for b in re.split(r'\n(?=## )', text):
        m = re.match(r'## (.+)', b)
        if not m:
            continue
        name = m.group(1).strip()
        if '更新规则' in name or '审稿团' in name:
            continue
        for field in ('当前位置', '怎么到的', '身上物品'):
            mm = re.search(field + r'[*\s]*[:：]\s*(.+)', b)
            if not mm:
                issues.append({'level': 'gap', 'file': '角色状态.md',
                               'item': '%s 缺「%s」' % (name, field)})
            elif any(p in mm.group(1) for p in ('未记录', '未说明', '待填')):
                issues.append({'level': 'gap', 'file': '角色状态.md',
                               'item': '%s 的「%s」= %s' % (name, field, mm.group(1)[:20])})
    return issues


def check_map(path):
    issues = []
    text = read(path)
    if not text:
        return [{'level': 'gap', 'file': '世界地图.md', 'item': '文件缺失'}]
    places = md_rows(text, ['地点', '距离'])
    if not places:
        issues.append({'level': 'gap', 'file': '世界地图.md', 'item': '没找到「相对位置表」'})
    unknown = [p.get('地点') for p in places if any(x in (p.get('距离') or '') for x in ('未明', '待定', '—'))
               and any(x in (p.get('距离') or '') for x in ('未明', '待定'))]
    if unknown:
        issues.append({'level': 'gap', 'file': '世界地图.md',
                       'item': '距离未定：%s（后文给具体数字前必须定死）' % '、'.join(unknown)})
    modes = md_rows(text, ['方式', '速度'])
    if not modes:
        issues.append({'level': 'gap', 'file': '世界地图.md', 'item': '没找到「交通方式与速度」表'})
    else:
        pending = [m.get('方式') for m in modes if any(x in (m.get('速度') or '') for x in ('待定', '待确认'))]
        if pending:
            issues.append({'level': 'gap', 'file': '世界地图.md',
                           'item': '交通方式速度待定：%s' % '、'.join(pending)})
    routes = md_rows(text, ['路线', '步行'])
    if routes:
        undecided = [r.get('路线') for r in routes if sum(1 for v in r.values() if '未定' in v) >= 2]
        if undecided:
            issues.append({'level': 'info', 'file': '世界地图.md',
                           'item': '行程未定：%s（写具体耗时前需补）' % '、'.join(undecided)})
    return issues


def check_power(path):
    issues = []
    text = read(path)
    if not text:
        return [{'level': 'gap', 'file': '力量体系.md', 'item': '文件缺失'}]
    realms = md_rows(text, ['境界', '门槛'])
    if not realms:
        issues.append({'level': 'contradiction', 'file': '力量体系.md',
                       'item': '没有「境界与升级条件」表 —— 升级速度无法校验'})
    else:
        no_time = []
        for r in realms:
            name = (r.get('境界') or '').strip()
            cost = (r.get('典型耗时') or '').strip()
            if '凡人' in name or name.startswith('（') or name.startswith('('):
                continue          # 凡人/占位行本来就没有耗时
            if not cost or cost in ('—', '-', '待定'):
                no_time.append(name)
        if no_time:
            issues.append({'level': 'gap', 'file': '力量体系.md',
                           'item': '「典型耗时」缺失：%s（升级快慢无法判定）' % '、'.join(no_time)})
    if '金手指' in text:
        tail = text.split('金手指', 1)[1]
        empty = all(not re.search(k + r'\s*[:：]\s*[^\s\-—*]', tail)
                    for k in ('能做什么', '不能做什么', '代价'))
        if empty:
            issues.append({'level': 'contradiction', 'file': '力量体系.md',
                           'item': '金手指边界没写（没写=无限强，长篇必崩）'})
    fights = md_rows(text, ['角色', '境界'])
    if not fights:
        issues.append({'level': 'gap', 'file': '力量体系.md', 'item': '没有「战力对照」表'})
    return issues


def check_timeline(path):
    issues = []
    text = read(path)
    if not text:
        return [{'level': 'gap', 'file': '时间线.md', 'item': '文件缺失'}]
    rows = md_rows(text, ['章', '故事内时间'])
    if not rows:
        return [{'level': 'gap', 'file': '时间线.md', 'item': '时间线还没起头（没有任何章节记录）'}]
    for r in rows:
        chapter = (r.get('章') or '').strip()
        note = (r.get('关键事件') or '')
        if any(p in note for p in ('待读正文确认', '待确认', '待填')):
            issues.append({'level': 'gap', 'file': '时间线.md',
                           'item': '%s 的时间记录是猜的（%s），需读正文确认' % (chapter, note[:24])})
    return issues


def check_foreshadow(path, current_ch=999):
    issues = []
    text = read(path)
    if not text:
        return [{'level': 'gap', 'file': '伏笔.md', 'item': '文件缺失'}]
    rows = md_rows(text, ['编号', '埋在哪章'])
    for r in rows:
        num = (r.get('编号') or '').strip()
        where = re.sub(r'\D', '', r.get('埋在哪章') or '')
        status = r.get('状态') or ''
        if num and where and '已收' not in status:
            age = current_ch - int(where)
            if age > 30:
                issues.append({'level': 'gap', 'file': '伏笔.md',
                               'item': '%s 埋在第 %s 章，已 %d 章未收（读者会忘）' % (num, where, age)})
    if not rows:
        issues.append({'level': 'gap', 'file': '伏笔.md', 'item': '还没登记任何伏笔'})
    return issues


def run(book, current_ch=None):
    base = os.path.join(_projects_root(), book, '设定库')
    if not os.path.isdir(base):
        return {'ok': False, 'error': '找不到 %s' % base}
    if current_ch is None:
        chapters = os.path.join(_projects_root(), book, '章节')
        nums = []
        if os.path.isdir(chapters):
            for f in os.listdir(chapters):
                m = re.match(r'(\d+)', f)
                if m and f.endswith('.md'):
                    nums.append(int(m.group(1)))
        current_ch = max(nums) if nums else 999

    checks = [
        ('角色卡', check_chars(os.path.join(base, '角色卡.md'))),
        ('角色状态', check_state(os.path.join(base, '角色状态.md'))),
        ('世界地图', check_map(os.path.join(base, '世界地图.md'))),
        ('力量体系', check_power(os.path.join(base, '力量体系.md'))),
        ('时间线', check_timeline(os.path.join(base, '时间线.md'))),
        ('伏笔', check_foreshadow(os.path.join(base, '伏笔.md'), current_ch)),
    ]
    all_issues = []
    for name, issues in checks:
        for i in issues:
            i['ledger'] = name
        all_issues.extend(issues)
    gaps = [i for i in all_issues if i['level'] == 'gap']
    contra = [i for i in all_issues if i['level'] == 'contradiction']
    if contra:
        verdict = 'contradiction'
    elif gaps:
        verdict = 'gaps'
    else:
        verdict = 'pass'
    return {'ok': True, 'book': book, 'current_chapter': current_ch, 'verdict': verdict,
            'gaps': len(gaps), 'contradictions': len(contra), 'issues': all_issues,
            'ledgers': {n: len(v) for n, v in checks}}


def main():
    ap = argparse.ArgumentParser(description='开书前设定自洽检查（闸 1）')
    ap.add_argument('--book', required=True)
    ap.add_argument('--ch', type=int, default=None, help='当前最新章号（伏笔年龄用）')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    res = run(args.book, args.ch)
    if not res.get('ok'):
        print('[错误] %s' % res['error'], file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        label = {'pass': '通过', 'gaps': '有 %d 处待补' % res['gaps'],
                 'contradiction': '有 %d 处矛盾（另有 %d 处待补）' % (res['contradictions'], res['gaps'])}[res['verdict']]
        print('《%s》设定自洽检查（当前第 %s 章）：%s' % (res['book'], res['current_chapter'], label))
        print('-' * 66)
        for i in res['issues']:
            tag = '矛盾' if i['level'] == 'contradiction' else ('待补' if i['level'] == 'gap' else '提示')
            print('[%s] %-6s %s' % (tag, i['ledger'], i['item']))
    return 0 if res['verdict'] == 'pass' else (2 if res['verdict'] == 'contradiction' else 1)


if __name__ == '__main__':
    sys.exit(main())
