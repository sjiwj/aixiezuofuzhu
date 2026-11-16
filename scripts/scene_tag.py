# -*- coding: utf-8 -*-
"""章节「场景标签」：读写章节 md 文件头的那一行注释。

对外契约
    parse(chapter_path)        -> {'place','time','raw'} | None
    set_tag(chapter_path, raw) -> {'changed': bool, 'raw': str, 'removed': int}

CLI
    python scripts/scene_tag.py <章节.md> --get
    python scripts/scene_tag.py <章节.md> --set "示例镇·<书名> · 清晨"
    python scripts/scene_tag.py <章节.md> --set ""          # 清掉标签
    加 --json 输出机器可读结构

格式（唯一写法，固定一行，写在文件最前面）
    <!-- 场景：示例镇·<书名> · 清晨 -->

为什么是 HTML 注释，不是 YAML frontmatter
  1) 渲染：CommonMark 把 <!-- ... --> 当 HTML 块，整行吃掉，任何渲染器都不显示；
     frontmatter 的 --- 会被当分隔线，place: xxx 会被当正文段落直接显示出来。
  2) 结构：frontmatter 占 3 行且首行 --- 与「分隔线 / 被删掉的标题」同形；
     导入器按「# 第 N 章」切章时，前置 3 行更容易被算进上一章。注释只有 1 行。
  3) 质检字数：l1_l2_check.cn_count() 对全文统计汉字，两种格式都会被算进去；
     单行注释只多出标签本身的汉字（十来个字），frontmatter 还要多算键名。

解析约定
    raw 用「 · 」（前后带空格的间隔号）切地点/时间；没有就整串当地点。
    地点内部的「示例镇·<书名>」这种不带空格的间隔号不会被切开。
"""
import json
import os
import re
import shutil
import sys
import tempfile

TAG_PREFIX = '<!-- 场景：'
TAG_SUFFIX = ' -->'
# 整行匹配；容忍 BOM 之外的空白、全角/半角冒号
TAG_RE = re.compile(r'^[ \t]*<!--\s*场景\s*[：:]\s*(.*?)\s*-->[ \t]*$')
MAX_SCAN = 5          # 只在文件头这几行里找标签，正文里的同名注释不算
SPLIT_SEP = ' \u00b7 '  # ' · '
MAX_RAW = 120


def split_raw(raw):
    """'示例镇·<书名> · 清晨' -> ('示例镇·<书名>', '清晨')"""
    s = (raw or '').strip()
    if SPLIT_SEP in s:
        place, _, time = s.rpartition(SPLIT_SEP)
        if place.strip():
            return place.strip(), time.strip()
    return s, ''


def _clean(raw):
    s = '' if raw is None else str(raw)
    s = (s.replace('\r', ' ').replace('\n', ' ')
          .replace('<!--', '').replace('-->', '').strip())
    if len(s) > MAX_RAW:
        s = s[:MAX_RAW].strip()
    return s


def _read(path):
    # newline='' ：原样保留 CRLF/LF，写回时才能做到「除了标签行，正文一个字节都不动」
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def _atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(prefix='.scene-tag-', suffix='.tmp', dir=d)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        try:
            shutil.copymode(path, tmp)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _split_bom(text):
    if text.startswith('\ufeff'):
        return '\ufeff', text[1:]
    return '', text


def parse(chapter_path):
    """读章节文件头，有标签返回 {'place','time','raw'}，没有返回 None。"""
    text = _read(chapter_path)
    _, body = _split_bom(text)
    for line in body.split('\n')[:MAX_SCAN]:
        stripped = line.rstrip('\r')
        m = TAG_RE.match(stripped)
        if m:
            raw = (m.group(1) or '').strip()
            if not raw:
                return None
            place, time = split_raw(raw)
            return {'place': place, 'time': time, 'raw': raw}
        if stripped.strip():
            break          # 第一个非空行不是标签 -> 这一章没有标签
    return None


def set_tag(chapter_path, raw):
    """写入/更新/清除标签。正文（标签行之外的每个字节）保持不动。

    返回 {'changed': bool, 'raw': str, 'removed': int}
    changed=False 表示内容本来就是目标状态（幂等，第二遍调用不写盘）。
    """
    raw = _clean(raw)
    text = _read(chapter_path)
    bom, body = _split_bom(text)
    nl = '\r\n' if '\r\n' in body else '\n'
    lines = body.split('\n')

    removed = 0
    i = 0
    while i < len(lines) and i < MAX_SCAN:
        stripped = lines[i].rstrip('\r')
        if TAG_RE.match(stripped):
            del lines[i]
            removed += 1
            continue
        if stripped.strip():
            break
        i += 1

    if raw:
        line = TAG_PREFIX + raw + TAG_SUFFIX
        lines.insert(0, line + '\r' if nl == '\r\n' else line)

    new_text = bom + '\n'.join(lines)
    changed = new_text != text
    if changed:
        _atomic_write(chapter_path, new_text)
    return {'changed': changed, 'raw': raw, 'removed': removed}


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description='章节场景标签（读写 md 文件头的一行注释）')
    ap.add_argument('chapter', help='章节 md 路径')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--get', action='store_true', help='读标签')
    g.add_argument('--set', metavar='RAW', help='写标签，形如「地点 · 时间」；传空串即清除')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    args = ap.parse_args(argv)

    path = args.chapter
    if not os.path.isfile(path):
        sys.stderr.write('找不到章节文件：%s\n' % path)
        return 2

    if args.set is not None:
        res = set_tag(path, args.set)
        tag = parse(path)
        if args.json:
            print(json.dumps({'ok': True, 'changed': res['changed'],
                              'removed': res['removed'], 'tag': tag}, ensure_ascii=False))
        elif not res['raw']:
            print('已清除场景标签' + ('' if res['changed'] else '（本来就没有）'))
        else:
            print(('已写入：' if res['changed'] else '无变化：')
                  + ('📍 ' + tag['raw'] if tag else '（空）'))
        return 0

    tag = parse(path)
    if args.json:
        print(json.dumps({'ok': True, 'tag': tag}, ensure_ascii=False))
    elif tag:
        print('📍 ' + tag['raw'])
        print('地点：' + (tag['place'] or '（未写）'))
        print('时间：' + (tag['time'] or '（未写）'))
    else:
        print('（这一章还没有场景标签）')
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
