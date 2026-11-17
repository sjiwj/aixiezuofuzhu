# -*- coding: utf-8 -*-
"""版本历史 —— 章节快照 / diff / 回滚（对照 NovelCrafter 的 Revision History）

问题：改稿是覆盖式的（f.write('# 第 N 章\n\n%s\n')），旧内容直接没了。
      .bak-<时间戳> 只是临时备份，客户看不到「上一版长什么样」，也没法「恢复到某一版」。

存储（每章一个目录，纯文件，不引数据库）：
    <书>/.history/<章号>/<YYYYmmdd-HHMMSS>-<reason>.md          版本正文
    <书>/.history/<章号>/<YYYYmmdd-HHMMSS>-<reason>.meta.json   字数 / 来源 / 时间 / 原文件名

约定：
    * 版本 id = 正文文件名去掉 .md（如 20261108-153900-revise），可直接当 URL 参数传。
    * 同一秒内同 reason 重复调用 = 同一个 id，覆盖同名文件（幂等，版本数不增加）。
    * 写章（reason='ai-write'）与改稿（reason='revise'）在**写盘前**调 snapshot()，
      存下来的就是「即将被覆盖的那一版」——这正是客户要的「上一版」。
    * restore() 落盘之前先把当前稿存成 '-before-restore'，任何一次恢复都不会丢东西。
    * 每次 snapshot 之后自动 prune(keep=30)，每章只留最近 30 版，磁盘不会爆。
    * 目录以 '.' 开头：server.tree() / stats_path() 本来就跳过点目录，不会出现在文件树里。

用法：
    python core/history.py --book <书名> --ch 001 --list
    python core/history.py --book <书名> --ch 001 --snap --reason manual
    python core/history.py --book <书名> --ch 001 --diff ID_A ID_B
    python core/history.py --book <书名> --ch 001 --restore ID
    python core/history.py --book <书名> --ch 001 --prune --keep 30
"""
import argparse
import difflib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO
from errors import human, report          # v1.0.1 错误普通话化：界面只显示中文，原文进日志

HIST_DIR = '.history'
CHAPTERS = '章节'
REASONS = ('manual', 'revise', 'ai-write', 'review-fix', 'before-restore')
DEFAULT_KEEP = 30
PREVIEW_MAX = 80
STAMP_FMT = '%Y%m%d-%H%M%S'

_REASON_BAD = re.compile(r'[^a-z0-9-]')


# ---------- 路径 ----------

def _projects_root():
    return CO.projects_root()


def _book_dir(book):
    """书名 -> 书目录。允许直接给绝对路径（测试用），但拒绝越界拼接。"""
    b = str(book or '').strip()
    if not b:
        raise ValueError('book 不能为空')
    if os.path.isabs(b):
        return os.path.abspath(b)
    rel = b.replace('\\', '/').strip('/')
    if not rel or '..' in rel.split('/'):
        raise ValueError('book 不合法：%s' % book)
    return os.path.abspath(os.path.join(_projects_root(), rel))


def chapter_no(chapter):
    """'第1章' / '1' / 1 -> '001'；没有数字返回 None。与 stages.chapter_no 同口径。"""
    m = re.search(r'(\d{1,4})', str(chapter or ''))
    return m.group(1).zfill(3) if m else None


def chapter_path(book, chapter):
    """按章号找章节 md 的绝对路径；找不到返回 None。

    规则与 server.resolve_chapter_file 一致：<章号>-*.md，排除 .bak / .draft。
    """
    ch = chapter_no(chapter)
    if not ch:
        return None
    d = os.path.join(_book_dir(book), CHAPTERS)
    prefix = ch + '-'
    try:
        for f in sorted(os.listdir(d)):
            if not f.endswith('.md'):
                continue
            if '.bak' in f or f.endswith('.draft') or f.startswith('.'):
                continue
            if f.startswith(prefix):
                return os.path.join(d, f)
    except OSError:
        pass
    return None


def _versions_dir(bdir, ch):
    return os.path.join(bdir, HIST_DIR, ch)


def _safe_reason(reason):
    r = _REASON_BAD.sub('', str(reason or '').strip().lower())
    return r or 'manual'


def _safe_vid(vid):
    v = str(vid or '').strip()
    if not v or '/' in v or '\\' in v or '..' in v or v.startswith('.'):
        raise ValueError('版本 id 不合法：%s' % vid)
    return v


# ---------- 读写 ----------

def _read_text(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def _atomic_write(path, text):
    """先写 .tmp 再 os.replace()——半截文件永远不落到正式路径上。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return len(text)


def _atomic_write_json(path, obj):
    return _atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=1) + '\n')


def _list_ids(bdir, ch):
    """版本 id 列表，按时间倒序（id 以 YYYYmmdd-HHMMSS 开头，字符串排序即时间排序）。"""
    d = _versions_dir(bdir, ch)
    try:
        names = os.listdir(d)
    except OSError:
        return []
    ids = [n[:-3] for n in names if n.endswith('.md') and not n.startswith('.')]
    return sorted(ids, reverse=True)


def _meta_path(bdir, ch, vid):
    return os.path.join(_versions_dir(bdir, ch), vid + '.meta.json')


def _version_path(bdir, ch, vid):
    return os.path.join(_versions_dir(bdir, ch), vid + '.md')


def _preview(text, n=PREVIEW_MAX):
    body = re.sub(r'^\s*#.*$', '', text or '', count=1, flags=re.M)   # 去掉「# 第 N 章」标题行
    body = re.sub(r'\s+', ' ', body).strip()
    return body[:n] + ('…' if len(body) > n else '')


def _meta_of(bdir, ch, vid):
    """读 meta；meta 丢了就按正文现算一份（旧数据自愈）。"""
    try:
        with open(_meta_path(bdir, ch, vid), encoding='utf-8') as f:
            meta = json.load(f)
    except (OSError, ValueError):
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    text = _read_text(_version_path(bdir, ch, vid))
    stamp = vid.split('-', 2)
    at = meta.get('at') or ('%s-%s-%sT%s:%s:%s' % (
        stamp[0][:4], stamp[0][4:6], stamp[0][6:8], stamp[1][:2], stamp[1][2:4], stamp[1][4:6])
        if len(stamp) >= 2 and len(stamp[0]) == 8 and len(stamp[1]) == 6 else '')
    reason = meta.get('reason') or (vid.split('-')[2] if len(stamp) >= 3 else '')
    return {
        'id': vid,
        'at': at,
        'reason': reason,
        'chars': int(meta.get('chars') if meta.get('chars') is not None else len(text)),
        'file': meta.get('file') or '',
        'preview': _preview(text),
    }


# ---------- 对外 API ----------

def snapshot(book, chapter, reason='manual'):
    """给某一章存一个版本。存到 <书>/.history/<章号>/<时间戳>-<reason>.md

    内容 = 调用这一刻磁盘上的章节正文（写章/改稿在写盘前调用，所以存的是被覆盖那版）。
    meta 同时落盘：字数 / 来源 / 时间 / 原文件名。
    同一秒内同 reason 重复调用幂等：id 相同 -> 覆盖同名，版本数不增加。
    返回 {'ok': True, 'id', 'at', 'reason', 'chars', 'file'}；
    失败返回 {'ok': False, 'error': ...} 而不抛异常——它在写章主流程里，不能拖死写盘。
    """
    try:
        bdir = _book_dir(book)
        ch = chapter_no(chapter)
        if not ch:
            return {'ok': False, 'error': 'chapter 不合法：%s' % chapter}
        src = chapter_path(book, chapter)
        if not src:
            return {'ok': False, 'error': '章节文件不存在，没有可存的旧稿', 'skipped': True}
        text = _read_text(src)
        meta = _write_version(bdir, ch, text, reason, os.path.basename(src))
        _prune_dir(bdir, ch, DEFAULT_KEEP)
        return meta
    except Exception as e:
        return {'ok': False, 'error': report(e)}


def snapshot_path(rel_or_abs, reason='revise'):
    """改稿写盘前的便捷入口：接受 'projects/<书>/章节/<章>.md' 或绝对路径。

    只对「章节正文」生效（路径里必须有 章节/，文件名必须 <3 位章号>-*.md），
    其它文件（设定库 / 大纲 / 片段）直接跳过，不产生版本。
    """
    try:
        p = str(rel_or_abs or '').strip()
        if not p:
            return {'ok': False, 'error': 'path 不能为空', 'skipped': True}
        if not os.path.isabs(p):
            p = os.path.join(os.path.dirname(_projects_root()), p.replace('\\', '/'))
        p = os.path.abspath(p)
        root = _projects_root()
        if not p.startswith(root + os.sep):
            return {'ok': False, 'error': '不在 projects/ 下', 'skipped': True}
        parts = p[len(root) + 1:].split(os.sep)
        if len(parts) < 3 or parts[1] != CHAPTERS:
            return {'ok': False, 'error': '不是章节正文', 'skipped': True}
        fname = parts[-1]
        if not fname.endswith('.md') or '.bak' in fname or fname.startswith('.'):
            return {'ok': False, 'error': '不是章节正文', 'skipped': True}
        ch = chapter_no(fname.split('-')[0])
        if not ch:
            return {'ok': False, 'error': '文件名没有章号', 'skipped': True}
        bdir = os.path.join(root, parts[0])
        text = _read_text(p)
        meta = _write_version(bdir, ch, text, reason, fname)
        _prune_dir(bdir, ch, DEFAULT_KEEP)
        return meta
    except Exception as e:
        return {'ok': False, 'error': report(e)}


def _write_version(bdir, ch, text, reason, src_name=''):
    reason = _safe_reason(reason)
    stamp = time.strftime(STAMP_FMT)
    vid = '%s-%s' % (stamp, reason)
    vd = _versions_dir(bdir, ch)
    os.makedirs(vd, exist_ok=True)
    _atomic_write(_version_path(bdir, ch, vid), text)
    meta = {
        'id': vid,
        'at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'reason': reason,
        'chars': len(text),
        'chars_cn': len(re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]', text)),
        'file': src_name,
    }
    _atomic_write_json(_meta_path(bdir, ch, vid), meta)
    meta['ok'] = True
    return meta


def list_versions(book, chapter):
    """返回 [{id, at, reason, chars, preview}]，按时间倒序。"""
    bdir = _book_dir(book)
    ch = chapter_no(chapter)
    if not ch:
        raise ValueError('chapter 不合法：%s' % chapter)
    return [_meta_of(bdir, ch, vid) for vid in _list_ids(bdir, ch)]


def _read_version(bdir, ch, vid):
    vid = _safe_vid(vid)
    p = _version_path(bdir, ch, vid)
    if not os.path.isfile(p):
        raise ValueError('版本不存在：%s' % vid)
    return _read_text(p)


def diff(book, chapter, id_a, id_b):
    """两个版本的 unified diff（difflib，3 行上下文），返回字符串；两版相同返回 ''。"""
    bdir = _book_dir(book)
    ch = chapter_no(chapter)
    if not ch:
        raise ValueError('chapter 不合法：%s' % chapter)
    a = _read_version(bdir, ch, id_a)
    b = _read_version(bdir, ch, id_b)
    return ''.join(difflib.unified_diff(
        a.splitlines(True), b.splitlines(True),
        fromfile=str(id_a), tofile=str(id_b), lineterm='\n'))


def restore(book, chapter, vid):
    """恢复某版本。恢复前先把当前稿存成 '-before-restore'，绝不丢东西。"""
    bdir = _book_dir(book)
    ch = chapter_no(chapter)
    if not ch:
        raise ValueError('chapter 不合法：%s' % chapter)
    vid = _safe_vid(vid)
    text = _read_version(bdir, ch, vid)
    src = chapter_path(book, ch)
    if not src:
        raise ValueError('章节文件不存在，无法恢复（第 %s 章）' % ch)
    before = ''
    try:
        old = _read_text(src)
    except OSError:
        old = ''
    if old.strip():
        meta = _write_version(bdir, ch, old, 'before-restore', os.path.basename(src))
        before = meta.get('id') or ''
    _atomic_write(src, text)
    _prune_dir(bdir, ch, DEFAULT_KEEP)
    return {'ok': True, 'restored': vid, 'before_restore': before,
            'chars': len(text), 'path': src}


def prune(book, chapter, keep=DEFAULT_KEEP):
    """只留最近 keep 个版本，更老的删掉（.md 与 .meta.json 一起删）。"""
    bdir = _book_dir(book)
    ch = chapter_no(chapter)
    if not ch:
        raise ValueError('chapter 不合法：%s' % chapter)
    return _prune_dir(bdir, ch, keep)


def _prune_dir(bdir, ch, keep=DEFAULT_KEEP):
    try:
        keep_n = max(int(keep), 1)
    except (TypeError, ValueError):
        keep_n = DEFAULT_KEEP
    ids = _list_ids(bdir, ch)
    removed = []
    for vid in ids[keep_n:]:
        for p in (_version_path(bdir, ch, vid), _meta_path(bdir, ch, vid)):
            try:
                os.remove(p)
                if p.endswith('.md'):
                    removed.append(vid)
            except OSError:
                pass
    return {'ok': True, 'kept': min(len(ids), keep_n), 'removed': removed}


# ---------- 命令行（手工验收用） ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--book', required=True)
    ap.add_argument('--ch', required=True)
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--snap', action='store_true')
    ap.add_argument('--reason', default='manual')
    ap.add_argument('--diff', nargs=2, metavar=('ID_A', 'ID_B'))
    ap.add_argument('--restore', default=None)
    ap.add_argument('--prune', action='store_true')
    ap.add_argument('--keep', type=int, default=DEFAULT_KEEP)
    a = ap.parse_args()
    if a.list:
        for v in list_versions(a.book, a.ch):
            print('%-28s %-14s %6d  %s' % (v['id'], v['reason'], v['chars'], v['preview']))
    elif a.snap:
        print(json.dumps(snapshot(a.book, a.ch, a.reason), ensure_ascii=False))
    elif a.diff:
        print(diff(a.book, a.ch, a.diff[0], a.diff[1]))
    elif a.restore:
        print(json.dumps(restore(a.book, a.ch, a.restore), ensure_ascii=False))
    elif a.prune:
        print(json.dumps(prune(a.book, a.ch, a.keep), ensure_ascii=False))
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
