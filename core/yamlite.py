# -*- coding: utf-8 -*-
"""极简 YAML 读取器（只用标准库）

只覆盖本项目配置文件用到的子集：
  - 缩进映射 / 列表
  - 列表项为映射（- id: xxx 后接同缩进键）
  - 标量：true/false/null、整数、浮点、带引号字符串、裸字符串
  - 注释：# 开头整行，或值后面的 " #"
  - 块标量：key: |  + 缩进文本（多行）

不支持锚点/别名、多文档、复杂流式语法 —— 遇到就直接报错，不静默瞎猜。
"""
import re


class YamlError(ValueError):
    pass


def _strip_comment(line):
    """去掉行尾注释，但保留引号内与块标量里的 #。"""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == '#' and (i == 0 or line[i - 1] in ' \t'):
            return line[:i].rstrip()
    return line.rstrip()


def _flow_list(s):
    """支持 [a, b, 'c'] 这种行内列表（空 [] 也算）。"""
    inner = s[1:-1].strip()
    if inner == '':
        return []
    out, buf, quote = [], '', None
    for ch in inner:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
            buf += ch
        elif ch == ',':
            out.append(_scalar(buf))
            buf = ''
        else:
            buf += ch
    if buf.strip():
        out.append(_scalar(buf))
    return out


def _scalar(text):
    s = text.strip()
    if s == '':
        return ''
    if s == '[]':
        return []
    if s == '{}':
        return {}
    if len(s) >= 2 and s[0] == '[' and s[-1] == ']':
        return _flow_list(s)
    if (s[0] == s[-1]) and s[0] in ('"', "'") and len(s) >= 2:
        return s[1:-1]
    low = s.lower()
    if low in ('true', 'yes', 'on'):
        return True
    if low in ('false', 'no', 'off'):
        return False
    if low in ('null', '~', 'none'):
        return None
    if re.fullmatch(r'-?\d+', s):
        return int(s)
    if re.fullmatch(r'-?\d+\.\d+', s):
        return float(s)
    return s


def loads(text):
    raw = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    # 预扫描：把块标量（key: |）整段抽出来，其余行进常规解析
    lines = []
    i = 0
    while i < len(raw):
        line = raw[i]
        stripped = line.strip()
        m = re.match(r'^(\s*)([^:#]+):\s*[|>]\s*$', line)
        if m:
            indent = len(m.group(1))
            key = m.group(2).strip()
            body = []
            i += 1
            while i < len(raw):
                nxt = raw[i]
                if nxt.strip() == '' or (len(nxt) - len(nxt.lstrip())) > indent:
                    body.append(nxt[indent + 2:] if nxt.strip() else '')
                    i += 1
                else:
                    break
            while body and body[-1].strip() == '':
                body.pop()
            lines.append((indent, key + ': ' + json_quote('\n'.join(body) + '\n')))
            continue
        lines.append((len(line) - len(line.lstrip()), _strip_comment(line)))
        i += 1

    items = [(ind, ln) for ind, ln in lines if ln.strip() != '']

    def parse_block(idx, indent):
        """返回 (value, next_idx)。"""
        if idx >= len(items):
            return None, idx
        ind, ln = items[idx]
        if ind < indent:
            return None, idx
        if ln.strip().startswith('- '):
            return parse_list(idx, ind)
        return parse_map(idx, ind)

    def parse_map(idx, indent):
        out = {}
        while idx < len(items):
            ind, ln = items[idx]
            if ind < indent:
                break
            if ind > indent:
                raise YamlError('缩进异常: %r' % ln)
            body = ln.strip()
            if body.startswith('- '):
                break
            if ':' not in body:
                raise YamlError('不是 key: value: %r' % body)
            key, _, rest = body.partition(':')
            key = key.strip()
            rest = rest.strip()
            if rest == '':
                idx += 1
                if idx < len(items) and items[idx][0] > ind:
                    val, idx = parse_block(idx, items[idx][0])
                elif idx < len(items) and items[idx][0] == ind and items[idx][1].strip().startswith('- '):
                    val, idx = parse_list(idx, ind)
                else:
                    val = None
                out[key] = val
            else:
                out[key] = _scalar(rest)
                idx += 1
        return out, idx

    def parse_list(idx, indent):
        out = []
        while idx < len(items):
            ind, ln = items[idx]
            if ind != indent or not ln.strip().startswith('- '):
                break
            body = ln.strip()[2:].strip()
            if body == '':
                idx += 1
                val, idx = parse_block(idx, items[idx][0]) if idx < len(items) else (None, idx)
                out.append(val)
                continue
            if ':' in body and not body.startswith('"') and not body.startswith("'"):
                # 列表项是映射：第一行用单独缩进处理，后续同层键并入
                item = {}
                key, _, rest = body.partition(':')
                key, rest = key.strip(), rest.strip()
                idx += 1
                if rest == '':
                    if idx < len(items) and items[idx][0] > indent:
                        val, idx = parse_block(idx, items[idx][0])
                    else:
                        val = None
                    item[key] = val
                else:
                    item[key] = _scalar(rest)
                # 后续与第一行同缩进的 key: value
                item_indent = indent + 2
                while idx < len(items) and items[idx][0] == item_indent \
                        and not items[idx][1].strip().startswith('- '):
                    sub = items[idx][1].strip()
                    k2, _, r2 = sub.partition(':')
                    k2, r2 = k2.strip(), r2.strip()
                    idx += 1
                    if r2 == '':
                        if idx < len(items) and items[idx][0] > item_indent:
                            v2, idx = parse_block(idx, items[idx][0])
                        else:
                            v2 = None
                        item[k2] = v2
                    else:
                        item[k2] = _scalar(r2)
                out.append(item)
            else:
                out.append(_scalar(body))
                idx += 1
        return out, idx

    value, idx = parse_block(0, items[0][0] if items else 0)
    return value if value is not None else {}


def json_quote(s):
    import json as _json
    return _json.dumps(s, ensure_ascii=False)


def load_file(path):
    with open(path, encoding='utf-8-sig') as f:
        return loads(f.read())
