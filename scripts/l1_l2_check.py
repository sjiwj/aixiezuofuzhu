# -*- coding: utf-8 -*-
"""L1 格式检查 + L2 重复检查

用法:
    python l1_l2_check.py <章节文件> [--rules config/qc_rules.json]
                          [--json [输出路径]] [--strict]

配置: 全部阈值来自 config/qc_rules.json 的 l1 / l2 节（缺文件时用内置兜底，不崩）。
输出: 人类可读报告 + JSON（默认写到 <章节目录>/../reports/<章名>.json）

CLI 约定（与 l3_l4_check.py 一致）:
    --json          只向 stdout 打印合法 JSON（结构 {"file","stats","issues"}），不打印报告
    --json PATH     同上，并额外写入 PATH
    --strict        存在 error 级问题时退出码 1
"""
import re, sys, json, os, hashlib, time
from collections import Counter

def _candidate_roots():
    """配置根候选，按优先级：NOVELAPP_ROOT > frozen 时 sys.executable 目录 > 源码 __file__ 上两级。

    PyInstaller 打包后 __file__ 指向 _MEIPASS，直接用它拼路径会导致 config 静默找不到，
    所以先看环境变量、再看 exe 所在目录，最后才用源码布局。
    """
    roots = []
    env = os.environ.get('NOVELAPP_ROOT')
    if env:
        roots.append(os.path.abspath(env))
    if getattr(sys, 'frozen', False):
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        roots.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return roots


def _base_dir():
    """第一个含 config/ 的候选根；都不含则退回候选首位（保持旧行为不崩）。"""
    roots = _candidate_roots()
    for r in roots:
        if os.path.isdir(os.path.join(r, 'config')):
            return r
    return roots[0]


BASE = _base_dir()
DEFAULT_RULES = os.path.join('config', 'qc_rules.json')

# 配置缺失时的兜底（与 config/qc_rules.json 的 l1/l2 节保持一致）
DEFAULT_CFG = {
    "l1": {
        "dash_max": 0,
        "arabic_number_max": 0,
        "paragraph_max_chars": 100,
        "word_count_min": 3000,
        "word_count_max": 4000,
    },
    "l2": {
        "protagonist": "甲",
        # 按字数比例算：每 200-300 字出现一次
        "protagonist_per_1000_min": 3,
        "protagonist_per_1000_max": 6,
        "repeat_phrase_max": 3,
        "phrase_len": 3,
        "dialogue_tag_max_consecutive": 2,
        "whitelist": ["示例镇", "雷公地", "老蔫叔", "乙", "苏姑娘", "示例滩", "后半晌"],
    },
}


def load_cfg(path):
    """读配置并与内置兜底深度合并；文件缺失/损坏时退回兜底。"""
    import copy
    cfg = copy.deepcopy(DEFAULT_CFG)
    if not path:
        return cfg
    if not os.path.exists(path):
        sys.stderr.write('[warn] 配置不存在，使用内置兜底: %s\n' % path)
        return cfg
    try:
        # utf-8-sig：兼容带/不带 BOM（记事本、PowerShell 5.1 另存都会加 BOM）
        with open(path, encoding='utf-8-sig') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        sys.stderr.write('[warn] 配置读取失败（%s），使用内置兜底\n' % e)
        return cfg
    for section in ('l1', 'l2'):
        val = data.get(section)
        if isinstance(val, dict):
            cfg[section].update(val)
    cfg['cliche'] = load_cliche()
    return cfg


def resolve_path(p, default_rel):
    p = p or default_rel
    if os.path.isabs(p) or os.path.exists(p):
        return p
    alt = os.path.join(BASE, p)
    return alt if os.path.exists(alt) else p


# ---------------------------------------------------------------- 判定 / 覆盖 / 缓存
# OpenWrite P0 两条：
#   ① 没检查的规则不能算 pass —— 覆盖不全时 verdict=inconclusive
#   ② 正文 sha256 变了，旧质检结果作废 —— stale=true，并保留上一版 revision 供比对
VERDICT_PASS, VERDICT_FAIL, VERDICT_INCONCLUSIVE = 'pass', 'fail', 'inconclusive'
CACHE_VERSION = 1


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def coverage_of(checks):
    """checks: [(rule, 'checked'|'skipped', reason)]"""
    checked = [r for r, s, _ in checks if s == 'checked']
    skipped = [{'rule': r, 'reason': why} for r, s, why in checks if s == 'skipped']
    return {'checked': len(checked), 'skipped': len(skipped), 'total': len(checks),
            'checked_rules': checked, 'skipped_rules': skipped}


def decide_verdict(issues, coverage):
    """有 error -> fail；有规则没跑到 -> inconclusive；全查过且无 error 才是 pass。"""
    if any((i.get('severity') or '').lower() == 'error' for i in issues):
        return VERDICT_FAIL
    if coverage['skipped'] > 0:
        return VERDICT_INCONCLUSIVE
    return VERDICT_PASS


def resolve_cache_path(chapter_path, explicit=None, disabled=False):
    if disabled:
        return None
    if explicit:
        return os.path.abspath(explicit)
    return os.path.abspath(os.path.join(os.path.dirname(chapter_path), '..', 'reports', '.qc-cache.json'))


def cache_read(path):
    if not path:
        return {}
    try:
        with open(path, encoding='utf-8-sig') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def cache_lookup(cache, key, revision):
    ent = (cache.get('entries') or {}).get(key)
    if not isinstance(ent, dict):
        return None
    ent = dict(ent)
    stored = str(ent.get('source_revision') or '').replace('sha256:', '')
    ent['stale'] = stored != revision
    return ent


def cache_write(path, key, entry):
    if not path:
        return
    data = cache_read(path)
    data['version'] = data.get('version') or CACHE_VERSION
    entries = data.get('entries')
    if not isinstance(entries, dict):
        entries = {}
    entries[key] = entry
    data['entries'] = entries
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        tmp = path + '.tmp~'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        sys.stderr.write('[warn] 质检缓存写入失败: %s\n' % e)


def verdict_line(verdict, coverage):
    if verdict == VERDICT_PASS:
        return '判定: pass（%d 项全查）' % coverage['total']
    if verdict == VERDICT_FAIL:
        return '判定: fail（存在 error 级问题）'
    names = '、'.join(x['rule'] for x in coverage['skipped_rules'][:5])
    tail = '' if coverage['skipped'] <= 5 else ' 等 %d 项' % coverage['skipped']
    return '判定: inconclusive（%d/%d 项未覆盖：%s%s）' % (
        coverage['skipped'], coverage['total'], names, tail)


def coverage_l1_l2(text, cfg, chapter_path=None):
    """每条规则的「能不能判」：缺配置/缺样本 -> skipped（进 inconclusive）。"""
    total = cn_count(text)
    c1, c2 = cfg['l1'], cfg['l2']
    checks = [
        ('dash_count', 'checked', ''),
        ('arabic_number', 'checked', ''),
        ('paragraph_length', 'checked', ''),
    ]
    if c1.get('word_count_min') is None or c1.get('word_count_max') is None:
        checks.append(('word_count', 'skipped', '缺少 word_count_min/max 配置'))
    else:
        checks.append(('word_count', 'checked', ''))
    checks.append(('quote_pairs', 'checked', ''))
    if not str(c2.get('protagonist') or '').strip():
        checks.append(('pronoun_density', 'skipped', '未配置主角名 protagonist'))
    else:
        checks.append(('pronoun_density', 'checked', ''))
    if total < 300:
        checks.append(('repeated_phrase', 'skipped', '正文不足 300 字，重复短语统计不可信'))
    else:
        checks.append(('repeated_phrase', 'checked', ''))
    if c2.get('dialogue_tag_max_consecutive') is None:
        checks.append(('dialogue_tag', 'skipped', '缺少 dialogue_tag_max_consecutive 配置'))
    else:
        checks.append(('dialogue_tag', 'checked', ''))
    cl = cfg.get('cliche') or {}
    groups = cl.get('groups') or {}
    if not groups:
        checks.append(('cliche', 'skipped', '缺少 config/cliche.json 或 groups 为空'))
    else:
        checks.append(('cliche', 'checked', ''))
        win = int((cl.get('limits') or {}).get('cross_chapter_window', 5))
        if chapter_path and prev_chapter_texts(chapter_path, win):
            checks.append(('cliche_cross_chapter', 'checked', ''))
        else:
            checks.append(('cliche_cross_chapter', 'skipped', '这一章没有可比的上一章，跨章重复查不了'))
    return coverage_of(checks)


def cn_count(text):
    """中文字数：汉字 + 数字 + 字母，不含标点空白"""
    return len(re.findall(r'[\u4e00-\u9fa5A-Za-z0-9]', text))


def split_paragraphs(text):
    """按空行分段，返回 [(起始行号, 段落文本)]"""
    blocks, buf, start = [], [], 1
    for i, line in enumerate(text.split('\n'), 1):
        if line.strip() == '':
            if buf:
                blocks.append((start, '\n'.join(buf)))
                buf = []
            start = i + 1
        else:
            if not buf:
                start = i
            buf.append(line)
    if buf:
        blocks.append((start, '\n'.join(buf)))
    return blocks


def first_unpaired_quote(text):
    """第一个不成对引号的字符位置；成对返回 None。"""
    stack = []
    for m in re.finditer(r'[“”]', text):
        if m.group() == '“':
            stack.append(m.start())
        elif stack:
            stack.pop()
        else:
            return m.start()
    return stack[0] if stack else None


def check_l1(text, cfg):
    issues = []
    c = cfg['l1']

    dash_hits = list(re.finditer(r'——|—{1,2}(?!—)', text))
    dash = len(dash_hits)
    if dash > c['dash_max']:
        issues.append({"rule": "dash_count", "severity": "warn",   # 风格类：降 warn（见 docs/quality/规则来源.md）
                       "message": f"破折号 {dash} 个，上限 {c['dash_max']}",
                       "snippet": "——" if dash else "",
                       # json_line：只给 JSON 用；人类报告不打印这条的行号，保证文本逐字不变
                       "json_line": text[:dash_hits[0].start()].count('\n') + 1})

    arabic = [(m.start(), m.group()) for m in re.finditer(r'\d+', text)]
    if len(arabic) > c['arabic_number_max']:
        lines = text[:arabic[0][0]].count('\n') + 1 if arabic else 0
        issues.append({"rule": "arabic_number", "severity": "warn",   # 风格类：降 warn（见 docs/quality/规则来源.md）
                       "message": f"阿拉伯数字 {len(arabic)} 处，上限 {c['arabic_number_max']}",
                       "line": lines,
                       "snippet": ', '.join(x[1] for x in arabic[:8])})

    paras = split_paragraphs(text)
    long_paras = [(ln, cn_count(p)) for ln, p in paras if cn_count(p) > c['paragraph_max_chars']]
    if long_paras:
        issues.append({"rule": "paragraph_length", "severity": "warn",
                       "message": f"{len(long_paras)} 段超过 {c['paragraph_max_chars']} 字",
                       "line": long_paras[0][0],
                       "snippet": f"最长 {max(x[1] for x in long_paras)} 字，行号 {[x[0] for x in long_paras[:5]]}"})

    total = cn_count(text)
    if total < c['word_count_min'] or total > c['word_count_max']:
        issues.append({"rule": "word_count", "severity": "warn",
                       "message": f"全章 {total} 字，要求 {c['word_count_min']}-{c['word_count_max']}",
                       "snippet": "超出" if total > c['word_count_max'] else "不足"})

    left, right = text.count('“'), text.count('”')
    if left != right:
        pos = first_unpaired_quote(text)
        issues.append({"rule": "quote_pairs", "severity": "error",
                       "message": f"引号不成对：左 {left} 右 {right}",
                       "json_line": (text[:pos].count('\n') + 1) if pos is not None else None})

    return issues, {"word_count": total, "paragraphs": len(paras), "dash": dash, "arabic": len(arabic)}


def check_l2(text, cfg):
    issues = []
    c = cfg['l2']

    name = c['protagonist']
    n = text.count(name)
    total_chars = cn_count(text)
    per1000 = n / (total_chars / 1000) if total_chars else 0
    lo, hi = c['protagonist_per_1000_min'], c['protagonist_per_1000_max']
    if per1000 < lo or per1000 > hi:
        issues.append({"rule": "pronoun_density", "severity": "warn",
                       "message": f"主角名「{name}」{n} 次 / {total_chars} 字 = {per1000:.1f} 次每千字，要求 {lo}-{hi}"})

    L = c['phrase_len']
    cjk = re.sub(r'[^\u4e00-\u9fa5]', ' ', text)
    grams = Counter()
    for seg in cjk.split():
        for i in range(len(seg) - L + 1):
            grams[seg[i:i+L]] += 1
    wl = set(c.get('whitelist', []))
    over = [(g, k) for g, k in grams.most_common(60)
            if k > c['repeat_phrase_max'] and not any(w in g for w in wl)]
    if over:
        issues.append({"rule": "repeated_phrase", "severity": "warn",
                       "message": f"{len(over)} 个 {L} 字短语超过 {c['repeat_phrase_max']} 次",
                       "snippet": ', '.join(f"{g}×{k}" for g, k in over[:10])})

    tags = re.findall(r'[他说道]{2,}', text)
    seq = 0
    for m in re.finditer(r'(?:他说|她道|他道|她说)', text):
        seq += 1
        if seq > c['dialogue_tag_max_consecutive']:
            issues.append({"rule": "dialogue_tag", "severity": "info",
                           "message": f"「他说/他道」连续 {seq} 次",
                           "line": text[:m.start()].count('\n') + 1})
            break
    else:
        seq = 0

    return issues, {"protagonist_count": n, "repeated_phrases": len(over),
                    "protagonist_per_1000": round(per1000, 1)}


# ---------------------------------------------------------------- 套话 / 偷懒句式
def load_cliche():
    """config/cliche.json：质检与写作层共用同一份词表（改一处两边生效）。"""
    cands = [os.path.join(BASE, 'config', 'cliche.json'), resolve_path(None, os.path.join('config', 'cliche.json'))]
    for p in cands:
        try:
            if p and os.path.exists(p):
                with open(p, encoding='utf-8-sig') as f:
                    return json.load(f)
        except (OSError, ValueError) as e:
            sys.stderr.write('[warn] cliche.json 读取失败（%s），套话检查跳过\n' % e)
            return {}
    return {}


def prev_chapter_texts(path, window):
    """同目录里排在当前章前面的 window 章（按文件名排序，跳过 .bak）。"""
    d = os.path.dirname(os.path.abspath(path))
    try:
        files = sorted(f for f in os.listdir(d) if f.endswith('.md') and '.bak' not in f)
    except OSError:
        return []
    stem = os.path.basename(path)
    if stem in files:
        i = files.index(stem)
        cand = files[max(0, i - window):i]
    else:
        cand = files[-window:]
    out = []
    for f in cand:
        try:
            with open(os.path.join(d, f), encoding='utf-8-sig') as fh:
                out.append((f, fh.read()))
        except OSError:
            continue
    return out


def check_cliche(text, chapter_path, cfg):
    """套话与偷懒句式：单条超频、整章密度过高、跨章反复用同一句。"""
    cl = cfg.get('cliche') or {}
    groups = cl.get('groups') or {}
    limits = cl.get('limits') or {}
    issues = []
    hits = {}
    total_chars = cn_count(text) or 1
    per1000_max = limits.get('per_1000_max', 5)
    single_max = limits.get('single_phrase_max', 2)

    def line_of(pos):
        return text[:pos].count('\n') + 1

    for gkey, g in groups.items():
        if not isinstance(g, dict):
            continue
        sev = g.get('severity', 'warn')
        label = g.get('label') or gkey
        hint = g.get('hint') or ''
        for ph in (g.get('phrases') or []):
            cnt = text.count(ph)
            if not cnt:
                continue
            hits[ph] = hits.get(ph, 0) + cnt
            if cnt > single_max:
                issues.append({'rule': 'cliche_' + gkey, 'severity': sev,
                               'line': line_of(text.find(ph)),
                               'message': '%s：「%s」用了 %d 次（上限 %d）' % (label, ph, cnt, single_max),
                               'snippet': hint})
        for pat in (g.get('patterns') or []):
            try:
                ms = list(re.finditer(pat, text))
            except re.error:
                continue
            for m in ms:
                ph = m.group(0)
                hits[ph] = hits.get(ph, 0) + 1
                if hits[ph] == 1:
                    issues.append({'rule': 'cliche_' + gkey, 'severity': sev,
                                   'line': line_of(m.start()),
                                   'message': '%s：「%s」' % (label, ph),
                                   'snippet': hint})
        for word in (g.get('standalone') or []):
            pat = '(^|[\n「“])' + re.escape(word) + '([。！？…，]|」|”|$)'
            try:
                ms = list(re.finditer(pat, text))
            except re.error:
                continue
            for m in ms:
                hits[word] = hits.get(word, 0) + 1
                if hits[word] <= single_max:
                    issues.append({'rule': 'cliche_' + gkey, 'severity': sev,
                                   'line': line_of(m.start()),
                                   'message': '%s：「%s」独立成句' % (label, word),
                                   'snippet': hint})

    total_hits = sum(hits.values())
    per1000 = total_hits / (total_chars / 1000.0)
    if per1000 > per1000_max:
        top = sorted(hits.items(), key=lambda kv: -kv[1])[:8]
        issues.append({'rule': 'cliche_density', 'severity': 'error',
                       'message': '套话密度 %.1f 次/千字（上限 %s）' % (per1000, per1000_max),
                       'snippet': '、'.join('%s×%d' % (k, v) for k, v in top)})

    window = int(limits.get('cross_chapter_window', 5))
    need = int(limits.get('cross_chapter_hits', 2))
    prevs = prev_chapter_texts(chapter_path, window)
    for ph in list(hits.keys()):
        if len(ph) < 3:
            continue
        total = hits[ph]
        where = ['本章×%d' % hits[ph]]
        for fname, ptxt in prevs:
            c = ptxt.count(ph)
            if c:
                total += c
                where.append('%s×%d' % (fname.replace('.md', ''), c))
        if total >= need and len(where) >= 2:
            issues.append({'rule': 'cliche_repeat', 'severity': 'error',
                           'message': '「%s」在最近 %d 章里出现 %d 次（%s）' % (ph, len(prevs) + 1, total, ' / '.join(where)),
                           'snippet': '同一句式反复用 = 偷懒；换成具体动作或物件'})

    return issues, {'cliche_hits': total_hits, 'cliche_per_1000': round(per1000, 1),
                    'cliche_distinct': len(hits), 'cliche_prev_chapters': len(prevs)}

def normalize_issues(issues):
    """统一 issues 结构：rule/severity/line/message/snippet 五个键齐全，未知行号为 null。

    line 取 i['line']；若没有则退回 i['json_line']（只对 JSON 生效的行号，
    人类报告不打印它，从而保持文本输出逐字不变）。
    """
    out = []
    for i in issues:
        line = i.get("line")
        if line is None:
            line = i.get("json_line")
        out.append({
            "rule": i.get("rule"),
            "severity": i.get("severity"),
            "line": line,
            "message": i.get("message"),
            "snippet": i.get("snippet"),
        })
    return out


def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python l1_l2_check.py <章节文件> [--rules config/qc_rules.json] "
              "[--json [路径]] [--strict]")
        return 0
    path = args[0]
    rules_path = resolve_path(args[args.index('--rules') + 1] if '--rules' in args else None,
                              DEFAULT_RULES)
    want_json = '--json' in args
    strict = '--strict' in args
    use_cache = '--use-cache' in args
    no_cache = '--no-cache' in args
    cache_arg = (args[args.index('--cache') + 1]
                 if '--cache' in args and args.index('--cache') + 1 < len(args) else None)
    json_path = None
    if want_json:
        idx = args.index('--json')
        if idx + 1 < len(args) and not args[idx + 1].startswith('--'):
            json_path = args[idx + 1]

    text = open(path, encoding='utf-8-sig').read()
    cfg = load_cfg(rules_path)

    revision = sha256_file(path)
    cache_path = resolve_cache_path(path, cache_arg, no_cache)
    cache_key = 'l1_l2:' + os.path.abspath(path)
    prev = cache_lookup(cache_read(cache_path), cache_key, revision)
    stale = bool(prev and prev.get('stale'))

    if use_cache and prev and not stale and isinstance(prev.get('issues'), list):
        coverage = prev.get('coverage') or coverage_of([])
        payload = {
            'file': path, 'stats': prev.get('stats') or {}, 'issues': prev['issues'],
            'verdict': prev.get('verdict') or VERDICT_INCONCLUSIVE,
            'source_revision': 'sha256:' + revision, 'coverage': coverage,
            'stale': False, 'reused': True,
            'cache': {'path': cache_path,
                      'previous_revision': prev.get('source_revision'),
                      'previous_verdict': prev.get('verdict'),
                      'checked_at': prev.get('checked_at')},
        }
        if want_json and json_path:
            reuse_out = os.path.abspath(json_path)
            os.makedirs(os.path.dirname(reuse_out) or '.', exist_ok=True)
            with open(reuse_out, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        if want_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(verdict_line(payload['verdict'], coverage) + '（缓存复用，正文未变）')
        return 0

    l1, stat1 = check_l1(text, cfg)
    l2, stat2 = check_l2(text, cfg)
    l3, stat3 = check_cliche(text, path, cfg)
    all_issues = l1 + l2 + l3
    stats = {**stat1, **stat2, **stat3, 'root': BASE, 'rules': os.path.abspath(rules_path)}
    coverage = coverage_l1_l2(text, cfg, path)
    verdict = decide_verdict(all_issues, coverage)

    if not want_json:
        print("=" * 66)
        print(f"质检报告  {os.path.basename(path)}")
        print("=" * 66)
        print(verdict_line(verdict, coverage))
        if stale:
            print('⚠️  正文已变更：上一版结果作废（%s -> %s）' % (
                (prev or {}).get('source_revision'), 'sha256:' + revision))
        print(f"字数 {stat1['word_count']}   段落 {stat1['paragraphs']}   "
              f"破折号 {stat1['dash']}   阿拉伯数字 {stat1['arabic']}   "
              f"主角名 {stat2['protagonist_count']} 次")
        print("-" * 66)

        if not all_issues:
            print("✅ 全部通过")
        else:
            errors = [i for i in all_issues if i['severity'] == 'error']
            warns  = [i for i in all_issues if i['severity'] == 'warn']
            infos  = [i for i in all_issues if i['severity'] == 'info']
            for tag, group, icon in [("ERROR", errors, "❌"), ("WARN", warns, "⚠️ "), ("INFO", infos, "ℹ️ ")]:
                for i in group:
                    loc = f" [行 {i['line']}]" if i.get('line') else ""
                    print(f"{icon} {tag:5} {i['rule']:18}{loc}  {i['message']}")
                    if i.get('snippet'):
                        print(f"        → {i['snippet']}")
            print("-" * 66)
            print(f"合计: {len(errors)} 错误 / {len(warns)} 警告 / {len(infos)} 提示")

    stem = os.path.splitext(os.path.basename(path))[0]
    out = json_path or os.path.join(os.path.dirname(path), '..', 'reports', stem + '.json')
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    normalized = normalize_issues(all_issues)
    payload = {"file": path, "stats": stats, "issues": normalized,
               "verdict": verdict,
               "source_revision": 'sha256:' + revision,
               "coverage": coverage,
               "stale": stale,
               "reused": False,
               "cache": {"path": cache_path,
                         "previous_revision": (prev or {}).get('source_revision'),
                         "previous_verdict": (prev or {}).get('verdict')}}
    cache_write(cache_path, cache_key, {
        'source_revision': 'sha256:' + revision, 'verdict': verdict,
        'coverage': {k: coverage[k] for k in ('checked', 'skipped', 'total')},
        'issues': normalized, 'stats': stats,
        'checked_at': time.strftime('%Y-%m-%d %H:%M:%S')})
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if want_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print()
        print(f"JSON: {out}")

    errors = [i for i in all_issues if i['severity'] == 'error']
    return 1 if (strict and errors) else 0


if __name__ == '__main__':
    sys.exit(main())
