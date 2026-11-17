# -*- coding: utf-8 -*-
"""修复：/api/entries 增加发布包过期判定（issue-0001，幂等）。

判定：shipped_present 且 shipped_bytes < server_source_bytes * 0.8 → shipped_stale=true
并给 shipped_note，避免把 11-05 的旧包当成可发布的包。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, 'core', 'server.py')

OLD = """    shipped = os.path.join(ROOT, '发布桌面版', 'core', 'server.py')
    src = os.path.abspath(__file__)
    return {'ok': True,
            'entries': rows,
            'counts': counts,
            'server_source': src,
            'server_source_bytes': _server_bytes(src),
            'shipped_path': shipped,
            'shipped_bytes': _server_bytes(shipped),
            'shipped_present': os.path.isfile(shipped)}
"""

NEW = """    shipped = os.path.join(ROOT, '发布桌面版', 'core', 'server.py')
    src = os.path.abspath(__file__)
    src_bytes = _server_bytes(src)
    shipped_bytes = _server_bytes(shipped)
    shipped_present = os.path.isfile(shipped)
    # issue-0001：发布包比源码瘦一大截时要说出来，否则会有人直接把旧包发出去
    shipped_stale = bool(shipped_present and src_bytes and shipped_bytes < src_bytes * 0.8)
    if not shipped_present:
        shipped_note = '没有发布包（还没打包）'
    elif shipped_stale:
        shipped_note = ('发布包是旧版（%d 字节 vs 源码 %d 字节，仅 %.0f%%），'
                        '含已知安全修复缺失，先重新构建再用'
                        % (shipped_bytes, src_bytes, 100.0 * shipped_bytes / src_bytes))
    else:
        shipped_note = ''
    return {'ok': True,
            'entries': rows,
            'counts': counts,
            'server_source': src,
            'server_source_bytes': src_bytes,
            'shipped_path': shipped,
            'shipped_bytes': shipped_bytes,
            'shipped_present': shipped_present,
            'shipped_stale': shipped_stale,
            'shipped_note': shipped_note}
"""


def main():
    src = open(SERVER, encoding='utf-8', newline='').read()
    revert = '--revert' in sys.argv
    if revert:
        if NEW not in src:
            print('SKIP 未应用，无需回滚')
            return 0
        tmp = SERVER + '.tmp-fix'
        with open(tmp, 'w', encoding='utf-8', newline='') as f:
            f.write(src.replace(NEW, OLD, 1))
        os.replace(tmp, SERVER)
        print('REVERTED 已回滚 core/server.py（去掉 shipped_stale / shipped_note）')
        return 0
    if 'shipped_stale' in src:
        print('SKIP 已应用')
        return 0
    if src.count(OLD) != 1:
        print('FAIL 锚点命中 %d 次，停止' % src.count(OLD))
        return 1
    tmp = SERVER + '.tmp-fix'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(src.replace(OLD, NEW, 1))
    os.replace(tmp, SERVER)
    print('OK 已写入 core/server.py（entries_payload 加 shipped_stale / shipped_note）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
