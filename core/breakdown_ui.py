# -*- coding: utf-8 -*-
"""拆一本参考书：读文件 → 调思维层 → 写 拆书库/书籍拆解/<书名>/

为什么不在 UI 里直接跑 breakdown_book.py：那个脚本只准备提示词、不调模型
（它第 144/156 行写得很清楚）。真正拆解要「读原文 + 调模型 + 落盘」，所以这里做。

只拆两个维度，不是偷懒，是算过账：
  01-开篇钩子   给发散/评估当参照，最常用
  十合一        整体技法总结，chips 里标「有十合一」
每拆一个维度要读 8000 字节选、单个维度一次调用；13 个维度全拆要十几分钟，
等作者真需要某个维度（战斗写不好、对话不像人）再单独拆更合理。

所以有 import_dimension(book, code)：按需再拆一个维度，一次模型调用。
原文路径不另存，写进 <书>/_source.json（path / chars / encoding / time），
下次拆别的维度直接读它。_source.json 不以 .md 结尾，拆书库列表（listDocs）本来就看不见。

只给技法，不给原文：prompt 里明确要求「不引原文、不复述情节、不写人名」。
"""
import io
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO
import breakdown_book as BB

EXCERPT = 8000
MAX_TITLE = 40
SOURCE_FILE = '_source.json'

DIMS = [
    ('01', '开篇钩子', '01-开篇钩子.md',
     '黄金三章怎么抓人：第一段、第一个人、第一个悬念'),
    ('ten', '十合一', '十合一.md',
     '把整本书的写法揉成一份能迁移的总结：内核 / 规则 / 反面 / 怎么用到自己书上'),
]

_FMT = ('输出格式：\n'
        '## 一句话内核\n（这个维度，这本书的核心做法）\n\n'
        '## 可复用写法规则\n（具体怎么做，能直接用的，列 3-7 条）\n\n'
        '## 反面（别这样写）\n（这本书没做的事，或者踩过的坑）\n\n'
        '## 迁移要点\n（怎么用到自己的书上，注意什么）\n')

# 同一个 (书, 维度) 同时只让一个请求进去：两个并发请求都过了「已存在」检查时，
# 后者会覆盖前者的产物（内容一样但白花一次钱）。锁只在本进程内有效，跨进程靠原子写。
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(key):
    with _LOCKS_GUARD:
        lk = _LOCKS.get(key)
        if lk is None:
            lk = threading.Lock()
            _LOCKS[key] = lk
        return lk


def _sys(dim, desc):
    return ('你是网文拆解专家。把一本书的「%s」维度拆出来。\n\n拆解目标：%s\n\n%s'
            % (dim, desc, _FMT))


def _user(book_name, dim, excerpt):
    return ('书名：%s\n\n'
            '请只针对「%s」这一个维度拆解，不要泛泛而谈。\n'
            '拆不出就写「这本书这个维度不突出」，不要编。\n'
            '只写技法，不写原文：\n'
            '- 不要引用原文句子，也不要用引号“…”复述原文描写；要举例就改写成抽象说法'
            '（如「主角拔剑前会停顿」）。\n'
            '- 不要写具体人名、地名、门派名、器物名（剑名/法宝名）、招式名；'
            '一律用「主角」「对手」「那件器物」「某个门派」代替。\n'
            '- 不要复述情节和场景细节。\n\n'
            '=== 正文（节选，约 %d 字）===\n%s'
            % (book_name, dim, len(excerpt), excerpt))


def _lib_dir(name):
    return os.path.join(os.path.dirname(CO.projects_root()), '拆书库', '书籍拆解', name)


def _safe_name(name):
    """书名 = 拆书库/书籍拆解 下的目录名：只允许一层，挡住 ../ 和盘符。"""
    n = (name or '').strip()
    if not n or n in ('.', '..'):
        return None
    if len(n) > MAX_TITLE:
        return None
    for bad in ('/', '\\', ':', '\x00'):
        if bad in n:
            return None
    if n.startswith('.'):
        return None
    return n


def _dim_table():
    """code -> (维度名, 落盘文件名, 拆解目标)。13 个来自 breakdown_book.DIMENSIONS，另加 ten。"""
    out = {}
    for code, dim, desc in BB.DIMENSIONS:
        out[code] = (dim, '%s-%s.md' % (code, dim), desc)
    out['ten'] = ('十合一', '十合一.md',
                  '把整本书的写法揉成一份能迁移的总结：内核 / 规则 / 反面 / 怎么用到自己书上')
    return out


def _source_path(book_dir):
    return os.path.join(book_dir, SOURCE_FILE)


def _read_source(book_dir):
    """读 <书>/_source.json；没有或读坏返回 None。"""
    try:
        with io.open(_source_path(book_dir), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _write_atomic(path, body):
    tmp = path + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(body)
    os.replace(tmp, path)


def _write_source(book_dir, src_path, text, enc, name):
    """记下原文在哪 —— 下次拆别的维度不用让作者再选一次文件。"""
    payload = {'path': os.path.abspath(src_path),
               'chars': len(text),
               'encoding': enc,
               'name': name,
               'time': time.strftime('%Y-%m-%dT%H:%M:%S')}
    _write_atomic(_source_path(book_dir),
                  json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    return payload


def _thinking_cfg():
    """思维层配置：和 import_book 原来那段一模一样。"""
    layer = CO.resolve_layer('thinking') or {}
    cfg = {'model': layer.get('model') or 'deepseek-v4-pro',
           'temperature': 0.4,
           'max_tokens': int(layer.get('max_tokens') or 4000)}
    if layer.get('thinking') is True:
        cfg['extra_body'] = {'thinking': {'type': 'enabled'}}
    return cfg


def _run_dim(cfg, book_name, dim, desc, excerpt):
    """跑一个维度，返回 (正文, 错误串)；成功时错误串为空。"""
    try:
        resp = CO.chat(cfg, [
            {'role': 'system', 'content': _sys(dim, desc)},
            {'role': 'user', 'content': _user(book_name, dim, excerpt)},
        ])
        return CO.sanitize_worker_text(CO._extract_content(resp) or ''), ''
    except Exception as e:
        return '', '「%s」拆解失败：%s: %s' % (dim, type(e).__name__, str(e)[:80])


def import_book(path, book_name=None):
    """读一本书，拆出 01 与十合一并落盘。返回 {ok, book, files, chars, encoding}。"""
    if not path or not os.path.isfile(path):
        return {'ok': False, 'error': '文件不存在：%s' % path}
    text, enc = BB.read_book(path)
    if text is None:
        return {'ok': False, 'error': '读不了（编码认不出来，试过 utf-8/gbk/gb18030/utf-16）'}
    name = (book_name or os.path.splitext(os.path.basename(path))[0]).strip()[:MAX_TITLE]
    if not name:
        return {'ok': False, 'error': '书名是空的'}
    excerpt = text[:EXCERPT]
    if len(excerpt.strip()) < 800:
        return {'ok': False, 'error': '这本太短了（%d 字），拆不出东西' % len(excerpt.strip())}

    out = _lib_dir(name)
    os.makedirs(out, exist_ok=True)

    cfg = _thinking_cfg()

    made = []
    for code, dim, fname, desc in DIMS:
        body, err = _run_dim(cfg, name, dim, desc, excerpt)
        if err:
            return {'ok': bool(made), 'book': name, 'files': made, 'error': err}
        if not body.strip():
            continue
        _write_atomic(os.path.join(out, fname), body.strip() + '\n')
        made.append(fname)

    if not made:
        return {'ok': False, 'book': name, 'files': [], 'error': '模型没有输出'}

    # 原文路径落盘：之后 import_dimension 靠它读原文（拆出来的 md 里不存原文）
    try:
        _write_source(out, path, text, enc, name)
    except OSError as e:
        return {'ok': True, 'book': name, 'files': made, 'chars': len(excerpt),
                'encoding': enc, 'path': out,
                'warning': '拆解已写好，但原文路径没记住（%s: %s）' % (type(e).__name__, e)}

    return {'ok': True, 'book': name, 'files': made,
            'chars': len(excerpt), 'encoding': enc, 'path': out}


def import_dimension(book_dir_name, code, force=False):
    """给一本已拆过的书再拆一个维度。返回 {ok, book, code, file, chars, error?}。

    code 取 breakdown_book.DIMENSIONS 的 code（01..11 / 05b / 08b）或 'ten'。
    已有同名文件时不覆盖，返回 {ok: False, error: '这个维度已经拆过了', exists: True}；
    force=True 才重拆。
    """
    name = _safe_name(book_dir_name)
    if not name:
        return {'ok': False, 'error': '书名不合法：%s' % (book_dir_name or '')}
    code = str(code or '').strip()
    table = _dim_table()
    if code not in table:
        return {'ok': False, 'book': name, 'code': code,
                'error': '没有这个维度：%s' % (code or '')}
    dim, fname, desc = table[code]
    out = _lib_dir(name)
    target = os.path.join(out, fname)

    with _lock_for(name + '|' + code):
        if not os.path.isdir(out):
            return {'ok': False, 'book': name, 'code': code, 'file': fname,
                    'error': '这本书还没拆过：先「+ 拆一本」'}
        try:
            has_file = os.path.isfile(target) and os.path.getsize(target) > 0
        except OSError:
            has_file = False
        if has_file and not force:
            return {'ok': False, 'book': name, 'code': code, 'file': fname,
                    'exists': True, 'error': '这个维度已经拆过了'}

        src = _read_source(out)
        if not src or not src.get('path'):
            return {'ok': False, 'book': name, 'code': code, 'file': fname,
                    'error': '找不到原文路径（%s 缺失或损坏），请重新「+ 拆一本」' % SOURCE_FILE}
        src_path = str(src.get('path') or '')
        if not os.path.isfile(src_path):
            return {'ok': False, 'book': name, 'code': code, 'file': fname,
                    'error': '原文不在了：%s' % src_path}

        text, enc = BB.read_book(src_path)
        if text is None:
            return {'ok': False, 'book': name, 'code': code, 'file': fname,
                    'error': '读不了原文（编码认不出来）'}
        excerpt = text[:EXCERPT]
        if len(excerpt.strip()) < 800:
            return {'ok': False, 'book': name, 'code': code, 'file': fname,
                    'error': '原文太短了（%d 字），拆不出东西' % len(excerpt.strip())}

        body, err = _run_dim(_thinking_cfg(), name, dim, desc, excerpt)
        if err:
            return {'ok': False, 'book': name, 'code': code, 'file': fname, 'error': err}
        if not body.strip():
            return {'ok': False, 'book': name, 'code': code, 'file': fname,
                    'error': '模型没有输出'}

        _write_atomic(target, body.strip() + '\n')

    return {'ok': True, 'book': name, 'code': code, 'file': fname,
            'chars': len(excerpt), 'encoding': enc, 'forced': bool(force)}


def list_dimensions(book_dir_name):
    """GET /api/breakdown/dimensions 的数据：哪些拆过了、全部维度清单。"""
    name = _safe_name(book_dir_name)
    if not name:
        return {'ok': False, 'error': '书名不合法：%s' % (book_dir_name or '')}
    out = _lib_dir(name)
    table = _dim_table()
    order = [c for c, _n, _d in BB.DIMENSIONS] + ['ten']
    have = []
    for code in order:
        fname = table[code][1]
        p = os.path.join(out, fname)
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                have.append(code)
        except OSError:
            continue
    src = _read_source(out)
    return {'ok': True, 'book': name, 'have': have,
            'all': [{'code': c, 'name': table[c][0], 'desc': table[c][2]} for c in order],
            'chars': int((src or {}).get('chars') or 0),
            'source_ok': bool(src and src.get('path')
                              and os.path.isfile(str(src.get('path'))))}
