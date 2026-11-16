# -*- coding: utf-8 -*-
"""冷冻架 —— 为「弃坑」设计（对照 NovelCrafter Scene Archive：「Don't abandon your scenes just yet」）

**语义（别只当成一个布尔标记，这条是研讨里 B 的论点四）**

    在架的书：不进晨报、不催，账本冻结（不老化）。

为什么要有这个状态：
    如果只做「红灯 + 催债」，客户放弃一本书时，归因会是「这软件一直说我写不完」——
    产品就变成了失败的见证者。冷冻架给「暂时放下」一个体面的出口：
    书还在，账不删，但今天不催。

哪些代码该读它：
    * 晨报 / 每日提示：if shelf.is_on_shelf(book): continue
    * 债 / 到期清单 / 压力类指标：在架 = 冻结，不参与老化，不进红灯
    * 版本历史、正文、账本数据：一律不动——冷冻不等于删除

存储：<书>/.shelf.json = {"on": true, "since": "2026-11-08", "note": ""}
      没有文件 / on=false = 不在架上。文件名以 '.' 开头，文件树里看不到。

用法：
    python core/shelf.py --set <书名> --on
    python core/shelf.py --set <书名> --off
    python core/shelf.py --list
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO
import promises as PM

FILE = '.shelf.json'
CHAPTERS = '章节'
NOTE_MAX = 200


def _projects_root():
    return CO.projects_root()


def _book_dir(book):
    b = str(book or '').strip()
    if not b:
        raise ValueError('book 不能为空')
    if os.path.isabs(b):
        return os.path.abspath(b)
    rel = b.replace('\\', '/').strip('/')
    if not rel or '..' in rel.split('/'):
        raise ValueError('book 不合法：%s' % book)
    return os.path.abspath(os.path.join(_projects_root(), rel))


def shelf_path(book):
    return os.path.join(_book_dir(book), FILE)


def _read(book):
    """读 .shelf.json；没有 / 坏掉都当「不在架上」，不让一个坏文件炸掉晨报。"""
    try:
        with open(shelf_path(book), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write(path, text):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def set_shelf(book, on=True, note=None):
    """把一本书放到冷冻架 / 从冷冻架取出。

    on=True ：写 {on: true, since: 今天, note}；已在架上则保留原来的 since（不刷新日期）。
    on=False：写 {on: false, since: '', note}，数据一个字不删。
    幂等：第二次调同样参数，内容完全一致 -> 不重复落盘（applied=False）。
    """
    bdir = _book_dir(book)
    if not os.path.isdir(bdir):
        raise ValueError('书不存在：%s' % book)
    on = bool(on)
    old = _read(book)
    old_on = bool(old.get('on'))
    since = ''
    if on:
        since = str(old.get('since') or '') if old_on else ''
        since = since or time.strftime('%Y-%m-%d')
    note_old = str(old.get('note') or '')
    note_new = note_old if note is None else str(note)
    note_new = note_new.strip()[:NOTE_MAX]
    payload = {'on': on, 'since': since, 'note': note_new}
    same = (old_on == on and str(old.get('since') or '') == since
            and note_old == note_new and os.path.isfile(shelf_path(book)))
    if not same:
        _atomic_write(shelf_path(book), json.dumps(payload, ensure_ascii=False, indent=1) + '\n')
    out = dict(payload)
    out['ok'] = True
    out['book'] = book
    out['applied'] = not same
    return out


def is_on_shelf(book):
    """读 .shelf.json；没有文件 = 不在架上。"""
    try:
        return bool(_read(book).get('on'))
    except Exception:
        return False


def _chapters(book):
    d = os.path.join(_book_dir(book), CHAPTERS)
    n = 0
    try:
        for f in os.listdir(d):
            if f.endswith('.md') and '.bak' not in f and not f.startswith('.') and not f.endswith('.draft'):
                n += 1
    except OSError:
        return 0
    return n


def _open_promises(book):
    """未偿账：承诺里「状态：进行」的条数（已兑付 / 已弃置不算）。"""
    try:
        return len([p for p in PM.load_all(book)
                    if str(p.get('状态') or '').strip() == '进行'])
    except Exception:
        return -1


def _debts(book):
    """节奏债条数（promises.debts：高强度 + 超阈值章没推进）。在架期间不算账，只报数。"""
    try:
        return len(PM.debts(book))
    except Exception:
        return -1


def shelf_list():
    """列出所有在架的书：书名 / 上架日 / 章数 / 未偿账数。

    额外给 frozen=True 与 debts 数字，读的人必须知道：在架期间这些债**不老化、不催**。
    """
    root = _projects_root()
    out = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return out
    for name in names:
        if name.startswith('.'):
            continue
        if not os.path.isdir(os.path.join(root, name)):
            continue
        if not is_on_shelf(name):
            continue
        data = _read(name)
        out.append({
            'book': name,
            'since': str(data.get('since') or ''),
            'note': str(data.get('note') or ''),
            'chapters': _chapters(name),
            'open_promises': _open_promises(name),
            'debts': _debts(name),
            'frozen': True,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', default=None)
    ap.add_argument('--on', action='store_true')
    ap.add_argument('--off', action='store_true')
    ap.add_argument('--note', default=None)
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    if a.set:
        print(json.dumps(set_shelf(a.set, on=not a.off, note=a.note), ensure_ascii=False))
    elif a.list:
        print(json.dumps(shelf_list(), ensure_ascii=False, indent=1))
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
