# -*- coding: utf-8 -*-
"""机检（precheck）：能数的事不让模型判

跑在审稿团之前：不过关直接退回重写，不花模型钱。
八条：
  1 字数 < target*0.8              critical
  2 禁词命中                        high（每个）
  3 敏感词命中                      critical
  4 新专名不在名册                  medium（进待消歧）
  5 提到的角色不在角色卡            high（疑似幻觉）
  6 出现「第X章」且 X > 当前章      critical（穿越）
  7 连续两段相似度 > 0.8            medium
  8 对话占比 < 5%                   medium
"""
import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

SEVERITY = {
    'critical': {'score': 35, 'blocking': True},
    'high': {'score': 15, 'blocking': False},
    'medium': {'score': 6, 'blocking': False},
    'low': {'score': 2, 'blocking': False},
}

CHAP_HEAD = re.compile(r'第\s*([零一二三四五六七八九十百\d]{1,6})\s*章')
CN = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6,
      '七': 7, '八': 8, '九': 9, '十': 10, '百': 100}
DIALOG_RE = re.compile(r'[“"「][^”"」]{1,200}[”"」]|：\s*[“"「]')


def _cn2int(s):
    s = str(s or '')
    if s.isdigit():
        return int(s)
    if '十' in s:
        head, _, tail = s.partition('十')
        return (CN.get(head, 1) if head else 1) * 10 + (CN.get(tail, 0) if tail else 0)
    return CN.get(s, 0)


def _read(p):
    try:
        with open(p, encoding='utf-8-sig') as f:
            return f.read()
    except OSError:
        return ''


def severity_score(issues):
    """100 - sum(扣分)，最低 0。"""
    total = 0
    for it in issues:
        sev = (it or {}).get('severity', 'low')
        total += SEVERITY.get(sev, SEVERITY['low'])['score']
    return max(0, 100 - total)


def is_blocking(issue):
    return bool(SEVERITY.get((issue or {}).get('severity'), {}).get('blocking'))


def _names(book, kind):
    base = os.path.join(CO.projects_root(), book, '设定库')
    if kind == 'roles':
        f = '角色状态.md'
    elif kind == 'places':
        f = '世界地图.md'
    else:
        f = '角色卡.md'
    text = _read(os.path.join(base, f))
    out = set()
    if kind == 'places':
        for line in text.split('\n'):
            s = line.strip()
            if not s.startswith('|'):
                continue
            cells = [c.strip() for c in s.strip('|').split('|')]
            if len(cells) >= 2 and 2 <= len(cells[0]) <= 8 and cells[0] not in ('地点', '路线', '方式'):
                out.add(cells[0])
        return out
    if kind == 'roles':
        # 名册有三处来源，必须都读：
        #   角色状态.md 的 ## 段（已经写进状态的）
        #   角色卡.md 的 [[双链]]（索引里登记过的）
        #   角色卡/ 目录的文件名（一人一张卡）
        # 只读第一处会把「苏掌柜」这种"建了卡、还没进状态"的人误判成幻觉角色。
        for line in _read(os.path.join(base, '角色状态.md')).split('\n'):
            if line.startswith('## '):
                nm = re.sub(r'[（(].*?[)）]', '', line[3:]).strip()
                nm = re.sub(r'^[一二三四五六七八九十百]+、', '', nm).strip()
                if 1 <= len(nm) <= 8:
                    out.add(nm)
        card = _read(os.path.join(base, '角色卡.md'))
        for m in re.findall(r'\[\[([^\]|]{1,12})', card):
            nm = m.strip()
            if nm:
                out.add(nm)
        try:
            for f2 in os.listdir(os.path.join(base, '角色卡')):
                if f2.endswith('.md'):
                    out.add(f2[:-3])
        except OSError:
            pass
        return out
    for line in text.split('\n'):
        if line.startswith('## '):
            nm = re.sub(r'[（(].*?[)）]', '', line[3:]).strip()
            nm = re.sub(r'^[一二三四五六七八九十百]+、', '', nm).strip()
            if 1 <= len(nm) <= 8:
                out.add(nm)
    return out


def _target_words(book):
    try:
        import coordinator as _CO
        layer = _CO.resolve_layer('writing')
        return int(layer.get('target_words') or 0)
    except Exception:
        return 0


def _gate_words():
    """config/gate.yaml 里的敏感词/正则。"""
    try:
        import yamlite
        p = os.path.join(CO.ROOT, 'config', 'gate.yaml')
        d = yamlite.load_file(p)
        sens = (d or {}).get('sensitive') or {}
        words = [w for w in (sens.get('words') or []) if isinstance(w, str) and w]
        pats = [p for p in (sens.get('patterns') or []) if isinstance(p, str) and p]
        return words, pats
    except Exception:
        return [], []


def _banned_words(book):
    try:
        import yamlite
        p = os.path.join(CO.projects_root(), book, '设定库', '角色卡.md')
        text = _read(p)
        m = re.search(r'禁用词\s*[:：]\s*(.+)', text)
        if not m:
            return []
        return [w.strip() for w in re.split(r'[、,，\s]+', m.group(1)) if w.strip()]
    except Exception:
        return []


def precheck(book, chapter, text=None):
    ch = str(chapter).zfill(3)
    if text is None:
        d = os.path.join(CO.projects_root(), book, '章节')
        for f in (os.listdir(d) if os.path.isdir(d) else []):
            if f.startswith(ch) and f.endswith('.md'):
                text = _read(os.path.join(d, f))
                break
    text = text or ''
    body = re.sub(r'^\s*#.*$', '', text, count=1, flags=re.M)
    cn = len(re.findall(r'[\u4e00-\u9fa5]', body))

    blocking, warnings = [], []

    # 1 字数
    target = _target_words(book)
    if target and cn < target * 0.8:
        blocking.append({'type': 'word_count', 'severity': 'critical',
                         'detail': '只有 %d 字，目标 %d（下限 %d）' % (cn, target, int(target * 0.8))})

    # 2 禁词
    for w in _banned_words(book):
        if w and w in body:
            warnings.append({'type': 'banned_word', 'severity': 'high',
                             'detail': '禁用词命中：%s' % w})

    # 3 敏感词
    words, pats = _gate_words()
    hits = [w for w in words if w and w in body]
    for p in pats:
        try:
            if re.search(p, body):
                hits.append(p)
        except re.error:
            continue
    if hits:
        blocking.append({'type': 'sensitive', 'severity': 'critical',
                         'detail': '敏感词命中：%s' % '、'.join(hits[:6])})

    # 4 新专名（中文 2-4 字的人名/地名形态：以「」或引号出现，且不在名册）
    known = _names(book, 'roles') | _names(book, 'places')
    quoted = set(re.findall(r'[「『]([^」』]{2,4})[」』]', body))
    for q in quoted:
        if re.fullmatch(r'[\u4e00-\u9fa5]{2,4}', q) and q not in known:
            warnings.append({'type': 'new_entity', 'severity': 'medium',
                             'detail': '新专名「%s」不在名册' % q})

    # 5 疑似幻觉角色：2-3 字说话人 + 不在名册 + 正文里反复出现 + 不含虚词
    # 「对自己说」「跟他说」这类会切出「对自己」「跟他」，都不是人名 —— 2026-11-09 补
    STOP = set('的了是在和与就都也还被把没不我你他她它们这那有要会能上下中前后里外么吧呢啊着过地得'
               '对自跟向朝和跟自己')
    roles = _names(book, 'roles')
    said = set(re.findall(r'([\u4e00-\u9fa5]{2,3})(?:说|问|道)', body))
    for nm in said:
        if nm in roles or nm in known:
            continue
        if set(nm) & STOP or nm.startswith(('他', '她', '我', '你', '这', '那')):
            continue
        # 亲属/身份称谓不是名字：真实数据里「小叔子说」被当成幻觉角色报过
        if nm in ('老辈儿', '镇上人', '众人', '大家', '有人', '老人', '汉子', '老头', '老汉',
                  '小叔子', '小舅子', '婶子', '嫂子', '婆娘', '媳妇', '后生', '丫头', '小子',
                  '娘', '爹', '哥', '姐', '弟', '妹', '掌柜的', '伙计', '客人', '东家'):
            continue
        if body.count(nm) < 2:
            continue
        warnings.append({'type': 'unknown_role', 'severity': 'high',
                         'detail': '「%s」说话了，但不在角色卡里' % nm})

    # 6 章号穿越
    cur = int(ch) if ch.isdigit() else 0
    for m in CHAP_HEAD.finditer(text[:400]):
        n = _cn2int(m.group(1))
        if n and cur and n > cur:
            blocking.append({'type': 'chapter_ahead', 'severity': 'critical',
                             'detail': '正文出现「%s」，晚于本章（%s）' % (m.group(0).strip(), ch)})
            break

    # 7 段落重复
    paras = [p.strip() for p in re.split(r'\n\s*\n', body) if len(p.strip()) > 30]
    for a, b in zip(paras, paras[1:]):
        if difflib.SequenceMatcher(None, a, b).ratio() > 0.8:
            warnings.append({'type': 'dup_paragraph', 'severity': 'medium',
                             'detail': '连续两段高度相似：%s…' % a[:20]})
            break

    # 8 对话占比
    if cn >= 300:
        dlg = sum(len(m.group(0)) for m in DIALOG_RE.finditer(body))
        if dlg / max(cn, 1) < 0.05:
            warnings.append({'type': 'low_dialog', 'severity': 'medium',
                             'detail': '对话占比 %.1f%%（<5%%，全是叙述）' % (dlg * 100.0 / cn)})

    # 9 信息差（泄密 / 废笔）
    try:
        import infogap as _IG
        ig = _IG.check_chapter(book, ch)
        if ig.get("ok"):
            for it in ig.get("blocking", []):
                blocking.append({"type": "infogap_leak", "severity": "critical",
                                 "detail": it["detail"]})
            for it in ig.get("warnings", []):
                warnings.append({"type": "infogap_" + it["type"],
                                 "severity": it.get("severity", "medium"),
                                 "detail": it["detail"]})
    except Exception as e:
        warnings.append({"type": "infogap_error", "severity": "low",
                         "detail": "信息差检查跳过了：%s" % str(e)[:50]})

    # 10 承诺结转（本章有没有推进任何承诺）
    try:
        import promises as _P
        ps = _P.load_all(book)
        cur_int = int(ch) if str(ch).isdigit() else 0
        active = [p for p in ps if p.get("状态") == "进行"]
        touched = [p for p in active if _P.to_int(p.get("最后推进章")) == cur_int]
        if active and not touched:
            warnings.append({"type": "no_promise_touch", "severity": "medium",
                             "detail": "本章没有推进任何承诺（%d 条在等）" % len(active)})
    except Exception as e:
        pass

    # 11-13 跨章/空间/时间三项（L2/L3/L4）
    # 为什么用子模块：这三类都要读设定库的表格和前面几章，塞进本文件会让八条变得
    # 又长又难测。接口统一 check(book, chapter, text) -> {'blocking','warnings'}。
    # 「数据不足，跳过」这类说明（*_skipped）不进告警，否则每章都会刷一条噪音。
    for _mod, _label in (('qc_l2', 'L2 跨章对账'),
                         ('qc_space', 'L3 空间一致性'),
                         ('qc_time', 'L4 时间一致性')):
        try:
            _m = __import__(_mod)
        except ImportError:
            continue                      # 模块没装就当没有这一关，不报错
        try:
            _r = _m.check(book, ch, text)
            for _it in (_r.get('blocking') or []):
                blocking.append(_it)
            for _it in (_r.get('warnings') or []):
                if str(_it.get('type') or '').endswith('_skipped'):
                    continue
                warnings.append(_it)
        except Exception as _e:
            warnings.append({'type': _mod + '_error', 'severity': 'low',
                             'detail': '%s 检查跳过了：%s' % (_label, str(_e)[:60])})

    issues = blocking + warnings
    return {'book': book, 'chapter': ch, 'chars': cn, 'target_words': target,
            'layers': ['L1', 'L2', 'L3', 'L4'],
            'passed': len(blocking) == 0, 'blocking': blocking, 'warnings': warnings,
            'score': severity_score(issues)}


def main():
    ap = argparse.ArgumentParser(description='机检（审稿团之前的硬门槛）')
    ap.add_argument('--book', required=True)
    ap.add_argument('--chapter', required=True)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    r = precheck(args.book, args.chapter)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print('第 %s 章：%s（%d 字 / 目标 %s，得分 %d）' % (
            r['chapter'], '通过' if r['passed'] else '退回重写', r['chars'],
            r['target_words'] or '未配置', r['score']))
        for it in r['blocking']:
            print('  [blocking/%s] %s' % (it['severity'], it['detail']))
        for it in r['warnings']:
            print('  [warn/%s] %s' % (it['severity'], it['detail']))
    return 0 if r['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
