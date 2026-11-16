# -*- coding: utf-8 -*-
"""导入已有稿子 —— 把乱文件整理成标准项目结构

用法:
    python core/import_book.py <源路径> [--name 书名] [--dry-run] [--force] [--root PROJECTS_DIR]

    --root 的语义：**projects 目录本身**（书会建在 <root>/<书名>/）。
    默认值（与插件 projectsRoot() 一致）：
      NOVELAPP_PROJECTS > <app>/projects > <data>/projects（NOVELAPP_DATA / NOVELAPP_ROOT/data / %APPDATA%/novelapp-desktop/data）

四种输入：
  1. 单个 txt/md        -> 按「第X章」切成多章
  2. 一个文件夹         -> 逐文件识别章节（文件名 / 首行 / 顺序）
  3. 已有标准结构       -> 校验 + 复制（不重排）
  4. docx               -> 读 word/document.xml 取正文（标准库实现，不依赖 python-docx）

三条硬规则：
  · 不覆盖：目标已存在就报错（--force 才允许，且只补缺、不覆盖同名文件）
  · 不移动：只复制，源目录一个字节都不动
  · --dry-run：只打印计划，不写盘
"""
import argparse
import os
import re
import shutil
import sys
import time
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

CN_NUM = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
          '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '百': 100}
CHAP_RE = re.compile(r'^\s*第\s*([零一二三四五六七八九十百两\d]{1,6})\s*章[^\n]*$', re.M)
SETTING_KEYS = ('人物', '角色', '设定', '世界观', '大纲', '细纲', '地理', '地图',
                '伏笔', '时间线', '力量', '体系', '卡片', '资料')
CHAPTER_DIR = '章节'
SETTING_DIR = '设定库'

SETTING_TEMPLATES = {
    '角色卡.md': '# 《{book}》· 角色卡\n\n## 一、主角名（主角·详细）\n\n### 7. 行为逻辑（硬约束）\n1. **遇到冲突**：\n2. **危机第一反应**：\n\n### 8. 语言风格\n- 口头禅：\n- 句式特点：\n',
    '角色状态.md': '# 《{book}》· 角色状态\n\n> 语义：记录「截至最后一章结束时」的状态。审 N 章时，表里是 N-1 章结束的状态。\n\n## 主角名（主角）\n\n- **当前位置**：未说明\n- **怎么到的**：未说明\n- **身上物品**：未说明\n- **身体状况**：无伤\n',
    '世界地图.md': '# 《{book}》· 世界地图\n\n## 一、相对位置表\n\n| 地点 | 相对方位 | 距离 | 地形 | 备注 |\n|---|---|---|---|---|\n| 起点 | — | — | — | — |\n\n## 二、交通方式与速度\n\n| 方式 | 速度 | 条件 | 备注 |\n|---|---|---|---|\n| 步行（空手） | 四十里/日 | 凡人 | — |\n\n## 三、本书已记录的行程\n\n| 路线 | 步行 | 挑担 | 快跑 | 备注 |\n|---|---|---|---|---|\n',
    '力量体系.md': '# 《{book}》· 力量体系\n\n## 一、境界与升级条件\n\n| 境界 | 门槛 | 典型耗时 | 战力倍数 |\n|---|---|---|---|\n| 凡人 | — | — | 1 |\n\n## 二、主角成长记录\n\n| 章 | 境界 | 怎么升的 | 距上次升级 |\n|---|---|---|---|\n\n## 三、硬约束\n\n1. 每升一层至少需要上表「典型耗时」\n2. 越级挑战需要前置条件\n\n## 四、战力对照\n\n| 角色 | 境界 | 能打赢 | 打不过 |\n|---|---|---|---|\n',
    '时间线.md': '# 《{book}》· 时间线\n\n| 章 | 故事内时间 | 地点 | 关键事件 | 距上一章 |\n|---|---|---|---|---|\n',
    '伏笔.md': '# 《{book}》· 伏笔\n\n> 列说明见 docs/format/伏笔表格式.md。权重 1-10（主线≥7）、层级 主线/支线/彩蛋、回收目标三级（arc_002 / sec_003 / ch_015）。\n\n## 已埋未收\n\n| 编号 | 埋在哪章 | 内容 | 状态 | 权重 | 层级 | 回收目标 | 建议 |\n|---|---|---|---|---|---|---|---|\n\n## 已收\n\n| 编号 | 埋在哪 | 收到哪 | 怎么收的 |\n|---|---|---|---|\n',
    '事件索引.md': '# 《{book}》· 事件索引\n\n| 章 | 故事内时间 | 一句话事件 | 关键角色 | 关键地点 |\n|---|---|---|---|---|\n',
    '章节摘要.md': '# 《{book}》· 章节摘要\n\n## 章摘要\n\n## 卷摘要\n\n## 全书摘要\n',
}


# ---------------- 工具 ----------------

def cn_to_int(s):
    s = str(s or '').strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if '十' in s:
        head, _, tail = s.partition('十')
        tens = CN_NUM.get(head, 1) if head else 1
        ones = CN_NUM.get(tail, 0) if tail else 0
        return tens * 10 + ones
    if len(s) == 1:
        return CN_NUM.get(s)
    total = 0
    for ch in s:
        if ch in CN_NUM:
            total = total * 10 + CN_NUM[ch] if CN_NUM[ch] < 10 else total + CN_NUM[ch]
    return total or None


def app_root():
    """frozen 下是 exe 所在目录；源码模式是 core/ 的上一级。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    cands = [os.environ.get('NOVELAPP_DATA')]
    root = os.environ.get('NOVELAPP_ROOT')
    if root:
        cands.append(os.path.join(root, 'data'))
    if os.environ.get('APPDATA'):
        cands.append(os.path.join(os.environ['APPDATA'], 'novelapp-desktop', 'data'))
    for c in cands:
        if not c:
            continue
        try:
            os.makedirs(c, exist_ok=True)
            return c
        except OSError:
            continue
    return os.getcwd()


def default_projects_root():
    """与插件 projectsRoot() 对齐：NOVELAPP_PROJECTS > <app>/projects > <data>/projects。"""
    cands = [os.environ.get('NOVELAPP_PROJECTS'),
             os.path.join(app_root(), 'projects'),
             os.path.join(data_dir(), 'projects')]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return os.path.join(data_dir(), 'projects')


def read_text(path):
    for enc in ('utf-8-sig', 'utf-8', 'gb18030', 'big5'):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def docx_to_text(path):
    """标准库读 docx：zip -> word/document.xml -> 段落拼接。"""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read('word/document.xml')
    except (zipfile.BadZipFile, KeyError) as e:
        raise SystemExit('docx 读取失败：%s' % e)
    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(ns + 'p'):
        txt = ''.join(t.text or '' for t in p.iter(ns + 't'))
        paras.append(txt)
    return '\n'.join(paras).strip()


def split_chapters(text):
    """单文件按「第X章」切成 [(no, title, body)]。"""
    matches = list(CHAP_RE.finditer(text))
    if not matches:
        return []
    out = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = m.group(0).strip()
        no = cn_to_int(m.group(1)) or (i + 1)
        body = text[start:end].strip()
        out.append((no, title, body))
    return out


def guess_name_from_text(text):
    m = re.search(r'《([^》]{1,30})》', text[:2000])
    return m.group(1).strip() if m else None


def is_setting_file(name, head):
    blob = name + ' ' + head
    return any(k in blob for k in SETTING_KEYS)


def safe_stem(name):
    s = re.sub(r'[\\/:*?"<>|]', '', name).strip()
    return s or 'untitled'


# ---------------- 扫描 ----------------

def scan_standard(src):
    """已有标准结构：章节/ + 设定库/。"""
    chapters = []
    cdir = os.path.join(src, CHAPTER_DIR)
    for f in sorted(os.listdir(cdir)):
        if f.endswith('.md'):
            chapters.append({'name': f, 'src': os.path.join(cdir, f),
                             'title': os.path.splitext(f)[0], 'out': f})
    settings = []
    sdir = os.path.join(src, SETTING_DIR)
    if os.path.isdir(sdir):
        for f in sorted(os.listdir(sdir)):
            if f.endswith('.md'):
                settings.append({'name': f, 'src': os.path.join(sdir, f)})
    return chapters, settings, '标准结构（章节/ + 设定库/）'


def scan_folder(src):
    files = [f for f in sorted(os.listdir(src))
             if f.lower().endswith(('.txt', '.md', '.docx')) and os.path.isfile(os.path.join(src, f))]
    chapters, settings = [], []
    pending = []
    for f in files:
        p = os.path.join(src, f)
        if f.lower().endswith('.docx'):
            text = docx_to_text(p)
        else:
            text = read_text(p)
        head = '\n'.join(text.split('\n')[:3])
        if is_setting_file(f, head) and not CHAP_RE.search(head):
            settings.append({'name': f if f.endswith('.md') else os.path.splitext(f)[0] + '.md',
                             'src': p, 'text': text})
            continue
        m = CHAP_RE.search(head) or CHAP_RE.search(text[:200])
        no = cn_to_int(m.group(1)) if m else None
        if no is None:                       # 文件名里任意位置的数字（book-3.txt）
            digits = re.search(r'(\d{1,4})', os.path.splitext(f)[0])
            if digits:
                no = int(digits.group(1))
        title = ''
        if text.strip():
            first = text.strip().split('\n')[0].strip()
            if len(first) <= 40 and (first.startswith('#') or '章' in first):
                title = first.lstrip('#').strip()
        pending.append({'name': f, 'src': p, 'text': text, 'no': no, 'title': title})

    # 没有编号的按文件顺序补号（排在已有编号之后，避免撞号）
    used = {r['no'] for r in pending if r['no']}
    next_no = (max(used) + 1) if used else 1
    for rec in pending:
        if rec['no'] is None:
            rec['no'] = next_no
            next_no += 1
            used.add(rec['no'])

    for i, rec in enumerate(pending):
        no = rec['no'] or (i + 1)
        title = rec['title'] or os.path.splitext(rec['name'])[0]
        rec['no'] = no
        rec['title'] = title
        rec['out'] = '%03d-%s.md' % (no, safe_stem(title))
        chapters.append(rec)
    chapters.sort(key=lambda r: (r['no'], r['name']))
    return chapters, settings, '散乱文件（%d 个）' % len(files)


def scan_single(path):
    raw = docx_to_text(path) if path.lower().endswith('.docx') else read_text(path)
    parts = split_chapters(raw)
    chapters, settings = [], []
    if parts:
        for no, title, body in parts:
            chapters.append({'name': title, 'title': title, 'text': body,
                             'out': '%03d-%s.md' % (no, safe_stem(title))})
    else:
        stem = os.path.splitext(os.path.basename(path))[0]
        chapters.append({'name': stem, 'title': stem, 'text': raw,
                         'out': '001-%s.md' % safe_stem(stem)})
    kind = '单文件（%s）%s' % (os.path.basename(path),
                             '按第X章切割' if parts else '未识别到章节，整本作为一章')
    return chapters, settings, kind, raw


# ---------------- 规划 / 执行 ----------------

def build_plan(src, name=None, root=None):
    src = os.path.abspath(src)
    if not os.path.exists(src):
        raise SystemExit('源路径不存在：%s' % src)
    root = os.path.abspath(root or default_projects_root())   # root 就是 projects 目录
    warnings = []

    if os.path.isdir(src):
        if os.path.isdir(os.path.join(src, CHAPTER_DIR)):
            chapters, settings, kind = scan_standard(src)
        else:
            chapters, settings, kind = scan_folder(src)
        default_name = os.path.basename(src.rstrip('\\/'))
    else:
        chapters, settings, kind, raw = scan_single(src)
        default_name = os.path.splitext(os.path.basename(src))[0]

    first_text = (locals().get('raw') or '')     # 单文件优先用整本原文猜书名（《雾镇》在第一章之前）
    if not first_text and chapters:
        first_text = chapters[0].get('text') or ''
    book = name or guess_name_from_text(first_text) or default_name or '未命名作品'
    book = safe_stem(book)
    target = os.path.join(root, book)

    plan = {'src': src, 'kind': kind, 'book': book, 'target': target,
            'chapters': chapters, 'settings': settings, 'warnings': warnings,
            'exists': os.path.exists(target)}
    if not chapters:
        warnings.append('没识别到任何章节内容，导入后会得到空项目')
    return plan


def execute(plan, force=False):
    target = plan['target']
    out = {'chapters': 0, 'settings': 0, 'skipped': [], 'created_setting_templates': 0}
    if plan['exists'] and not force:
        raise SystemExit('目标已存在：%s\n用 --force 允许写入（只补缺，不覆盖），或 --name 换个书名。' % target)
    os.makedirs(os.path.join(target, CHAPTER_DIR), exist_ok=True)
    os.makedirs(os.path.join(target, SETTING_DIR), exist_ok=True)

    for ch in plan['chapters']:
        dst = os.path.join(target, CHAPTER_DIR, ch['out'])
        if os.path.exists(dst):
            out['skipped'].append(os.path.relpath(dst, target))
            continue
        if ch.get('text') is not None:
            body = ch['text']
            if not body.lstrip().startswith('#'):
                body = '# %s\n\n%s' % (ch['title'], body)
            with open(dst, 'w', encoding='utf-8') as f:
                f.write(body)
        else:
            shutil.copy2(ch['src'], dst if ch.get('out') else os.path.join(target, CHAPTER_DIR, ch['name']))
        out['chapters'] += 1

    for st in plan['settings']:
        dst = os.path.join(target, SETTING_DIR, st['name'])
        if os.path.exists(dst):
            out['skipped'].append(os.path.relpath(dst, target))
            continue
        if st.get('text') is not None:
            with open(dst, 'w', encoding='utf-8') as f:
                f.write(st['text'])
        else:
            shutil.copy2(st['src'], dst)
        out['settings'] += 1

    for fname, tpl in SETTING_TEMPLATES.items():
        dst = os.path.join(target, SETTING_DIR, fname)
        if not os.path.exists(dst):
            with open(dst, 'w', encoding='utf-8') as f:
                f.write(tpl.replace('{book}', plan['book']))
            out['created_setting_templates'] += 1

    info = os.path.join(target, '项目信息.md')
    if not os.path.exists(info):
        with open(info, 'w', encoding='utf-8') as f:
            f.write('# %s\n\n- 状态：写作中\n- 当前进度：第 %d 章\n- 来源：%s\n- 导入时间：%s\n' % (
                plan['book'], len(plan['chapters']), plan['src'],
                time.strftime('%Y-%m-%d %H:%M')))
        out['info'] = True
    return out


def print_plan(plan):
    print('源: %s' % plan['src'])
    print('识别: %d 章, %d 个设定文件  （%s）' % (
        len(plan['chapters']), len(plan['settings']), plan['kind']))
    print('书名: %s' % plan['book'])
    print('目标: %s' % plan['target'])
    if plan['chapters']:
        print('章节目录:')
        for ch in plan['chapters'][:8]:
            print('  %-40s <- %s' % (ch.get('out') or ch['name'], ch['name']))
        if len(plan['chapters']) > 8:
            print('  …（还有 %d 章）' % (len(plan['chapters']) - 8))
    if plan['settings']:
        print('设定文件: %s' % '、'.join(s['name'] for s in plan['settings'][:8]))
    for w in plan['warnings']:
        print('注意: %s' % w)
    if plan['exists']:
        print('注意: 目标目录已存在%s' % ('，将只补缺、不覆盖同名文件'
                                       if getattr(plan, '_force_hint', None) else
                                       '（实际执行需要 --force）'))


def main():
    ap = argparse.ArgumentParser(description='导入已有稿子，整理成标准项目结构')
    ap.add_argument('src')
    ap.add_argument('--name', default=None)
    ap.add_argument('--root', default=None,
                    help='projects 目录本身（书建在 <root>/<书名>/）；默认按 NOVELAPP_PROJECTS > <app>/projects > <data>/projects')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    plan = build_plan(args.src, args.name, args.root)
    print_plan(plan)
    if args.dry_run:
        print()
        print('--dry-run：未写任何文件')
        return 0

    print()
    res = execute(plan, force=args.force)
    print('已复制 %d 章 → %s/' % (res['chapters'], CHAPTER_DIR))
    print('已整理 %d 个设定 → %s/' % (res['settings'], SETTING_DIR))
    print('已生成 %d 个账本模板 + 项目信息.md' % res['created_setting_templates'])
    if res['skipped']:
        print('跳过（已存在，未覆盖）: %s' % '、'.join(res['skipped'][:8]))
    print('完成：%s' % plan['target'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
