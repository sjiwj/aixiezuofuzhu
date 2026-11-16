#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基线统计：对一份章节正文算三个指标

1) 套话每千字    —— 命中 config/cliche.json 的词组数 / 千字
2) 单字评语句数  —— 独立成句的单字评语（稳/平/行/很直…）
3) 动作句/评语句比 —— 含具体动作或物件的句子数 ÷ 纯评价句数
"""
import io, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLICHE = os.path.join(ROOT, 'config', 'cliche.json')


def load_cliche():
    """读 config/cliche.json：phrases / patterns / standalone 三路都要。"""
    empty = {'phrases': [], 'patterns': [], 'standalone': [], 'groups': {}}
    if not os.path.exists(CLICHE):
        return empty
    with io.open(CLICHE, encoding='utf-8') as f:
        j = json.load(f)
    phrases, patterns, standalone, groups = [], [], [], {}
    for name, grp in (j.get('groups') or {}).items():
        ph = grp.get('phrases') or []
        pa = grp.get('patterns') or []
        sa = grp.get('standalone') or []
        phrases.extend(ph)
        patterns.extend(pa)
        standalone.extend(sa)
        groups[name] = {'severity': grp.get('severity'), 'label': grp.get('label'),
                        'phrases': ph, 'patterns': pa, 'standalone': sa}
    return {'phrases': [p for p in phrases if p],
            'patterns': [p for p in patterns if p],
            'standalone': [s for s in standalone if s],
            'groups': groups}


def split_sentences(text):
    body = re.sub(r'^#.*$', '', text, flags=re.M)
    parts = re.split(r'[。！？…]+', body)
    return [p.strip() for p in parts if p.strip()]


ACTION_HINTS = ('拿', '摸', '放', '走', '站', '坐', '蹲', '抬', '推', '拉', '抓',
                '按', '捏', '翻', '抽', '插', '递', '接', '收', '掏', '揣',
                '提', '拎', '扛', '背', '踩', '跨', '转', '回', '点', '摇',
                '敲', '拍', '拂', '擦', '抹', '投', '扔', '压', '提', '伸',
                '缩', '低', '弯', '直', '停', '迈', '踩', '踩', '看', '听',
                '闻', '咬', '咽', '吐', '呼', '吸')
OBJECT_HINTS = ('刀', '碗', '瓢', '桶', '绳', '门', '墙', '床', '石', '土',
                '雾', '灯', '钱', '米', '鞋', '线', '布', '木', '铁', '纸',
                '秤', '牌', '柜', '柴', '水', '火', '锅', '盆', '窗', '井')


def classify(sent):
    """粗分：有动作或物件 = action，否则若很短且是评价 = eval，其余 = narrative"""
    has_action = any(h in sent for h in ACTION_HINTS)
    has_object = any(h in sent for h in OBJECT_HINTS)
    if has_action or has_object:
        return 'action'
    if len(sent) <= 8:
        return 'eval'
    return 'narrative'


def stats(path):
    with io.open(path, encoding='utf-8') as f:
        text = f.read()
    cjk = len(re.findall(r'[\u4e00-\u9fff]', text))
    cl = load_cliche()

    hits = []
    for p in cl['phrases']:
        n = text.count(p)
        if n:
            hits.append((p, n))
    for pat in cl['patterns']:
        try:
            ms = re.findall(pat, text)
        except re.error:
            continue
        if ms:
            hits.append(('RE:' + pat[:24], len(ms)))
    hit_total = sum(n for _, n in hits)

    sents = split_sentences(text)
    standalone_hit = [s for s in sents if s in cl['standalone']]
    kinds = {'action': 0, 'eval': 0, 'narrative': 0}
    for s in sents:
        kinds[classify(s)] += 1

    per1000 = (hit_total / cjk * 1000) if cjk else 0
    ratio = (kinds['action'] / kinds['eval']) if kinds['eval'] else float('inf')

    return {
        'file': os.path.basename(path),
        'chars_cn': cjk,
        'sentences': len(sents),
        'cliche_hits': hit_total,
        'cliche_detail': hits[:10],
        'cliche_per_1000': round(per1000, 2),
        'standalone_eval': len(standalone_hit),
        'standalone_detail': standalone_hit[:8],
        'action_sents': kinds['action'],
        'eval_sents': kinds['eval'],
        'narrative_sents': kinds['narrative'],
        'action_eval_ratio': round(ratio, 2) if ratio != float('inf') else None,
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python baseline_stats.py <章.md> [更多.md ...]')
        sys.exit(2)
    out = []
    for p in sys.argv[1:]:
        if not os.path.exists(p):
            print('找不到:', p)
            continue
        s = stats(p)
        out.append(s)
        print('=' * 62)
        print(s['file'])
        print('  汉字数        %d' % s['chars_cn'])
        print('  句数          %d' % s['sentences'])
        print('  套话命中      %d 条  (每千字 %.2f)' % (s['cliche_hits'], s['cliche_per_1000']))
        if s['cliche_detail']:
            print('                %s' % s['cliche_detail'])
        print('  单字评语句    %d' % s['standalone_eval'])
        if s['standalone_detail']:
            print('                %s' % s['standalone_detail'])
        print('  动作句        %d' % s['action_sents'])
        print('  评价句        %d' % s['eval_sents'])
        print('  叙述句        %d' % s['narrative_sents'])
        print('  动作/评价比   %s' % s['action_eval_ratio'])
    print()
    print(json.dumps(out, ensure_ascii=False, indent=1))
