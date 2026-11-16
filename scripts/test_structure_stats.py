#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""structure_stats.py 的口径自测（全部用临时目录里的合成样本，不碰客户数据）

跑法：python scripts/test_structure_stats.py
只读客户数据；所有 fixture 建在系统临时目录，跑完删掉。
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import structure_stats as S  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    print('%s %s%s' % ('PASS' if cond else 'FAIL', name, ('' if cond else '  <- ' + str(detail))))
    if not cond:
        FAILS.append(name)


def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


PARA = '天地玄黄宇宙洪荒日月'          # 10 字，纯占位，避免撞常见词


def body(n=10):
    return '# 第 N 章' + chr(10) + chr(10) + (chr(10) + chr(10)).join([PARA] * n) + chr(10)


def build_project():
    root = tempfile.mkdtemp(prefix='ss-test-')
    proj = os.path.join(root, 'proj')
    w(os.path.join(proj, '设定库', '角色卡.md'), '甲：示例镇樵夫。' + chr(10))
    w(os.path.join(proj, '设定库', '世界地图.md'), '示例镇，往东三百里是示例滩。' + chr(10))
    w(os.path.join(proj, '设定库', '角色状态.md'),
      '# 角色状态' + chr(10) + chr(10) +
      '- **身上物品**：蓝布包（包着两块干粮，塞在床底）、铜铃、四十文' + chr(10))
    w(os.path.join(proj, '章节', '008-第8章.md'), body())
    w(os.path.join(proj, '章节', '007-第7章.md'), body())

    outline = chr(10).join([
        '# 大纲',
        '',
        '| 007 | 一句话的旧式章纲 | 推测 |',
        '| 008 | 一句话的旧式章纲 | 推测 |',
        '| 009 | 一句话的旧式章纲 | 推测 |',
        '',
        '<details>',
        '<summary>009 分场章纲</summary>',
        '',
        '**必须做到的事**',
        '',
        '1. 必须先摸一次白线，再开口说「赎」',
        '2. 牌上必须出现「四十一岁零四个月」',
        '',
        '**本章推进**',
        '',
        '- **P-006 旧草鞋**（推进：找鞋）',
        '</details>',
        '',
        '| 010 | 下一章 | 推测 |',
    ]) + chr(10)
    w(os.path.join(proj, '大纲', '全书大纲.md'), outline)
    return root, proj


def anchors_file(root, payload):
    p = os.path.join(root, 'anchors.json')
    w(p, json.dumps(payload, ensure_ascii=False))
    return p


def run_cli(args, cwd=None):
    p = subprocess.run([sys.executable, os.path.join(HERE, 'structure_stats.py')] + args,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd or HERE)
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def main():
    root, proj = build_project()
    ch8 = os.path.join(proj, '章节', '008-第8章.md')
    ch7 = os.path.join(proj, '章节', '007-第7章.md')
    outlines = os.path.join(proj, '大纲', '全书大纲.md')

    # ---- 1) 没配锚点 -> unconfigured，且必须交代 why + fix
    r = S.conflict_metric(ch8, os.path.join(proj, '章节'), {'chapters': {}})
    check('conflict/unconfigured 状态', r['status'] == 'unconfigured', r.get('status'))
    check('conflict/unconfigured 带 why', bool(r.get('why')), r.get('why'))
    check('conflict/unconfigured 带 fix', len(r.get('fix') or []) >= 2, r.get('fix'))
    check('conflict/unconfigured 不给 0%', 'ratio' not in r and 'first_conflict' not in r, r)

    # ---- 2) 配了锚点 -> 段落位置 / 比例 / 分档
    ap = anchors_file(root, {'chapters': {'008': {'conflict': [
        {'quote': PARA, 'para': 3, 'note': '第 3 段'},
        {'quote': PARA, 'para': 1, 'note': '第 1 段'},
    ]}}})
    anc = S.load_anchors(ap)
    r = S.conflict_metric(ch8, os.path.join(proj, '章节'), anc)
    check('conflict/状态 ok', r['status'] == 'ok', r.get('status'))
    check('conflict/首冲突在第1段=0.0', r['first_conflict']['ratio'] == 0.0, r.get('first_conflict'))
    check('conflict/分档统计', r['distribution'] == {'前20%': 1, '20-50%': 1, '后50%': 0},
          r.get('distribution'))
    check('conflict/前20% 边界(<0.2)', r['anchors'][1]['bucket'] == '前20%', r['anchors'][1])
    check('conflict/20-50% 左边界(0.2)', r['anchors'][0]['bucket'] == '20-50%' and
          r['anchors'][0]['ratio'] == 0.2, r['anchors'][0])

    # ---- 3) 锚点原句失效 -> 不静默算 0
    ap2 = anchors_file(root, {'chapters': {'008': {'conflict': [
        {'quote': '这句正文里根本没有', 'note': 'x'}]}}})
    r = S.conflict_metric(ch8, os.path.join(proj, '章节'), S.load_anchors(ap2))
    check('conflict/锚点失效 -> unconfigured', r['status'] == 'unconfigured', r.get('status'))
    check('conflict/失效锚点进 unplaced', len(r.get('unplaced') or []) == 1, r.get('unplaced'))

    # ---- 4) 008 没有 <details> -> 不偷 009 的块
    p = S.plan_metric(S.read_text(ch8), outlines, '008', os.path.join(proj, '设定库'))
    check('plan/008 无块 -> unconfigured', p['status'] == 'unconfigured', p.get('status'))
    check('plan/给出当前表格行', '| 008 |' in (p.get('current_row') or ''), p.get('current_row'))
    check('plan/指向有块的章 009', (p.get('example') or {}).get('chapter') == '009', p.get('example'))
    check('plan/摘录里有分场块样例', '必须做到的事' in (p.get('example') or {}).get('excerpt', ''),
          (p.get('example') or {}).get('excerpt', '')[:40])

    # ---- 5) 块归属校验：块里写 009，却挂在 008 行 -> mismatch
    bad = S.read_text(outlines).replace('| 008 | 一句话的旧式章纲 | 推测 |',
                                        '| 008 | 一句话的旧式章纲 | 推测 |' + chr(10) +
                                        '<details><summary>009 分场章纲</summary>' + chr(10) +
                                        '**必须做到的事**' + chr(10) + '1. 写「赎」' + chr(10) + '</details>')
    p = S.plan_metric(S.read_text(ch8), anchors_file(root, {}), '008', os.path.join(proj, '设定库'))
    p2 = S.plan_metric(S.read_text(ch8), _w(root, bad, 'outline-mismatch.md'), '008',
                       os.path.join(proj, '设定库'))
    check('plan/块章号不符 -> mismatch', p2['status'] == 'mismatch', p2.get('status'))

    # ---- 6) 必须做到的事：逐条核对，缺的进 missing，顺序要查
    text = '他先摸白线。' + chr(10) + '他说赎。' + chr(10)
    p = S.plan_metric(text, outlines, '009', os.path.join(proj, '设定库'))
    check('plan/条目数', p['items_total'] == 2, p.get('items_total'))
    check('plan/第1条命中', p['items'][0]['status'] == 'hit', p['items'][0])
    check('plan/第1条顺序核对', p['items'][0]['order'] == 'ok', p['items'][0].get('order'))
    check('plan/第2条 missing', p['items'][1]['status'] == 'missing', p['items'][1])
    check('plan/missing 清单', p['missing_list'][0]['literals'] == ['四十一岁零四个月'],
          p.get('missing_list'))

    text_rev = '他说赎。' + chr(10) + '他摸白线。' + chr(10)
    p = S.plan_metric(text_rev, outlines, '009', os.path.join(proj, '设定库'))
    check('plan/顺序反了 -> order_violated', p['items'][0]['status'] == 'order_violated',
          p['items'][0])

    # ---- 7) 引号内一律不查（对话里的新名字不报）
    setting = os.path.join(proj, '设定库')
    t = '叙述一句。' + chr(10) + '“柳三娘走了。”' + chr(10) + '“柳三娘又走了。”' + chr(10)
    ch = _w(root, t, 'quote-only.md')
    r = S.setting_metric(ch, setting)
    check('setting/引号内不取词', r['suspects'] == [], r['suspects'])

    # ---- 8) 叙述里的新名字 -> warn 级疑似
    t = '柳三娘把篮子放下。' + chr(10) + '柳三娘没说话。' + chr(10) + '断魂谷在东边。' + chr(10)
    ch = _w(root, t, 'narr-name.md')
    r = S.setting_metric(ch, setting)
    terms = [x['term'] for x in r['suspects']]
    check('setting/叙述中的新名字被报出', '柳三娘' in terms, terms)
    check('setting/地名后缀被报出', '断魂谷' in terms, terms)
    warn = [i for i in r['issues'] if i['severity'] == 'warn']
    check('setting/强候选是 warn', len(warn) == len(r['suspects']), (warn, r['suspects']))

    # ---- 9) 设定库里已有的不报
    t = '甲挑着担子。' + chr(10) + '甲走回示例镇。' + chr(10)
    ch = _w(root, t, 'known-name.md')
    r = S.setting_metric(ch, setting)
    check('setting/设定库已有的不报', r['suspects'] == [], r['suspects'])

    # ---- 10) 弱候选是 info，不和强候选混级
    t = ('皂荚树在路边。' + chr(10)) * 3
    ch = _w(root, t, 'weak.md')
    r = S.setting_metric(ch, setting)
    weak_terms = [x['term'] for x in r['weak']]
    check('setting/弱候选被报出', any('皂荚树' in x or x in '皂荚树' for x in weak_terms), weak_terms)
    info = [i for i in r['issues'] if i['severity'] == 'info']
    check('setting/弱候选是 info', bool(info), r['issues'])
    check('setting/弱候选不进 suspects', all('皂荚树' not in x['term'] for x in r['suspects']),
          r['suspects'])

    # ---- 10b) 物件轨道：白名单 / 量词 / 持有动作 / 只出现一次 / 时间词不当物件
    known = S.load_known_items(os.path.join(proj, '设定库'))
    check('object/白名单读到 身上物品', '铜铃' in known and '蓝布包' in known, sorted(known))
    check('object/括号里的补充说明不当物件',
          ('包着两块干粮' not in known) and ('床底' not in known), sorted(known))

    t = '他摸出铜铃。' + chr(10) + '铜铃在腰上。' + chr(10)
    ch = _w(root, t, 'obj-known.md')
    r = S.setting_metric(ch, setting)
    check('object/登记过的物件不报', all(x['term'] != '铜铃' for x in r['suspects']), r['suspects'])
    check('object/登记过的物件留在 registered_hits',
          '铜铃' in [x['term'] for x in r['objects']['registered_hits']], r['objects'])

    t = ('他从柜下取出一只铁匣。' + chr(10) + '铁匣上了锁。' + chr(10)) * 2
    ch = _w(root, t, 'obj-quant.md')
    r = S.setting_metric(ch, setting)
    kinds = dict((x['term'], x.get('kind')) for x in r['suspects'])
    check('object/量词轨道抓到铁匣', '铁匣' in kinds, kinds)
    check('object/量词轨道标了来源', kinds.get('铁匣') == '物件·量词+名词', kinds)

    t = ('他把铜镜揣进怀里。' + chr(10) + '铜镜冰凉。' + chr(10)) * 2
    ch = _w(root, t, 'obj-take.md')
    r = S.setting_metric(ch, setting)
    kinds = dict((x['term'], x.get('kind')) for x in r['suspects'])
    check('object/持有动作轨道抓到铜镜', '铜镜' in kinds, kinds)
    check('object/持有动作轨道标了来源', kinds.get('铜镜') == '物件·持有动作', kinds)

    t = '他摸出一只银锁。' + chr(10)
    ch = _w(root, t, 'obj-once.md')
    r = S.setting_metric(ch, setting)
    check('object/只出现一次不进强候选', all(x['term'] != '银锁' for x in r['suspects']),
          r['suspects'])
    check('object/只出现一次进 info 弱信号',
          '银锁' in [x['term'] for x in r['weak']], r['weak'])

    t = '“他把铜镜揣进怀里。”' + chr(10) + '三天过去了。一年又一年。五十文钱。' + chr(10) + \
        '年岁不够。一斗米。一片天。' + chr(10)
    ch = _w(root, t, 'obj-noise.md')
    r = S.setting_metric(ch, setting)
    bad = [x['term'] for x in (r['suspects'] + r['weak'])
           if x['term'] in ('三天', '一年', '五十文', '年岁', '一斗米', '铜镜', '天')]
    check('object/时间词与引号内不报', bad == [], bad)

    # ---- 11) CLI：--json 结构 + 第二遍 no-op
    before = (hashlib.sha256(io.open(ch8, 'rb').read()).hexdigest(), os.stat(ch8).st_mtime)
    rc1, out1, err1 = run_cli([ch8, '--json', '--anchors', ap])
    rc2, out2, err2 = run_cli([ch8, '--json', '--anchors', ap])
    check('cli/退出码 0', rc1 == 0, (rc1, err1[:200]))
    doc = json.loads(out1)
    ch = doc['chapters'][0]
    check('cli/json 三个指标齐', all(k in ch for k in ('conflict', 'plan', 'setting_names')), list(ch))
    check('cli/json issues 有分级', any(i['severity'] == 'warn' for i in ch['issues']) or
          all(i['severity'] in ('warn', 'info') for i in ch['issues']), ch['issues'])
    check('cli/第二遍输出一致', out1 == out2, '两次 stdout 不同')
    after = (hashlib.sha256(io.open(ch8, 'rb').read()).hexdigest(), os.stat(ch8).st_mtime)
    check('cli/未改动章节文件', before == after, (before, after))

    # ---- 12) 人类可读输出里必须能看见 unconfigured 的原因
    rc, out, _ = run_cli([os.path.join(proj, '章节', '007-第7章.md'), '--anchors', ap])
    check('cli/文本输出解释 unconfigured', '为什么' in out and 'structure_anchors.json' in out,
          out[:400])

    # ---- 13) --state-as-of：白名单按章时点取，而不是「此刻」
    proj2 = os.path.join(root, 'proj2')
    st2 = os.path.join(proj2, '设定库')
    w(os.path.join(st2, '角色卡.md'), '甲：示例镇樵夫。' + chr(10))
    w(os.path.join(st2, '角色状态.md'),
      '# 角色状态' + chr(10) + chr(10) +
      '## 甲（主角）' + chr(10) +
      '- **身上物品**：四十文、白线' + chr(10) + chr(10) +
      '## 乙（配角）' + chr(10) +
      '- **身上物品**：（未记录）' + chr(10))

    def snap(n, subject, items):
        w(os.path.join(proj2, '.story', 'state', 'chapter_%s.json' % n),
          json.dumps({'chapter': n, 'state_deltas': [
              {'subject': subject, 'field': '身上物品', 'value': items}]},
              ensure_ascii=False))

    snap('001', '甲', '四十文；柴刀、草鞋均已丢失')
    snap('003', '陆远', '一部手机')
    snap('006', '甲', '四十文、一截白线')
    snap('008', '甲', '四十文、白线')

    ch6 = os.path.join(proj2, '章节', '006-第6章.md')
    w(ch6, '他把白线揣进怀里。' + chr(10) + '白线是新的。' + chr(10))

    meta = S.load_state_asof(proj2, '006', S.state_subjects(st2))
    check('stateasof/只收章号严格小于目标章的快照',
          ('四十文' in meta['items']) and ('一截白线' not in meta['items'])
          and ('白线' not in meta['items']), sorted(meta['items']))
    check('stateasof/「已丢失」整组不登记',
          ('柴刀' not in meta['items']) and ('草鞋' not in meta['items']), sorted(meta['items']))
    check('stateasof/非本书主语的快照被跳过',
          ('一部手机' not in meta['items']) and ('陆远' in meta['foreign']), meta['foreign'])
    check('stateasof/用了哪些快照可追溯', meta['files_used'] == ['chapter_001.json'],
          meta['files_used'])

    r = S.setting_metric(ch6, st2, proj2, '006')
    check('stateasof/basis 标成 state-as-of:006',
          r['known_items_basis'] == 'state-as-of:006', r['known_items_basis'])
    check('stateasof/白线不在时点白名单', '白线' not in r['objects']['known_items'],
          r['objects']['known_items'])
    terms = [x['term'] for x in r['suspects']]
    check('stateasof/白线被报出（不加参数时漏报）', '白线' in terms, terms)
    sus = [x for x in r['suspects'] if x['term'] == '白线']
    check('stateasof/报出时标了几章才登记',
          bool(sus) and sus[0].get('registered_after') == '006', sus)
    check('stateasof/白线不进 registered_hits',
          all(x['term'] != '白线' for x in r['objects']['registered_hits']),
          r['objects']['registered_hits'])

    r_cur = S.setting_metric(ch6, st2, proj2)
    check('stateasof/不传参数 = 当前状态表',
          r_cur['known_items_basis'] == 'current', r_cur['known_items_basis'])
    check('stateasof/当前表下白线被当已登记',
          '白线' in [x['term'] for x in r_cur['objects']['registered_hits']]
          and r_cur['suspects'] == [],
          (r_cur['objects']['registered_hits'], r_cur['suspects']))

    r_fb = S.setting_metric(ch6, setting, proj, '006')
    check('stateasof/没有快照就退回当前表并说明',
          r_fb['known_items_basis'] == 'current'
          and bool(r_fb['known_items_state'].get('fallback')), r_fb['known_items_state'])

    rc, out, err = run_cli([ch6, '--json', '--state-as-of', '6'])
    doc = json.loads(out) if rc == 0 else {}
    sn = (doc.get('chapters') or [{}])[0].get('setting_names') or {}
    check('stateasof/CLI 接受 6 并补成 006',
          rc == 0 and sn.get('known_items_basis') == 'state-as-of:006',
          (rc, err[:200], sn.get('known_items_basis')))
    rc_bad, _, _ = run_cli([ch6, '--state-as-of', 'abc'])
    check('stateasof/非法章号直接报错', rc_bad != 0, rc_bad)

    before6 = (hashlib.sha256(io.open(ch6, 'rb').read()).hexdigest(), os.stat(ch6).st_mtime)
    rc1, o1, _ = run_cli([ch6, '--json', '--state-as-of', '006'])
    rc2, o2, _ = run_cli([ch6, '--json', '--state-as-of', '006'])
    check('stateasof/两遍输出一致', rc1 == 0 and o1 == o2, (rc1, rc2))
    after6 = (hashlib.sha256(io.open(ch6, 'rb').read()).hexdigest(), os.stat(ch6).st_mtime)
    check('stateasof/两遍都没改章节文件', before6 == after6, (before6, after6))

    shutil.rmtree(root, ignore_errors=True)
    print()
    if FAILS:
        print('FAILED %d: %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('ALL PASS')
    return 0


def _w(root, text, name):
    p = os.path.join(root, name)
    w(p, text)
    return p


if __name__ == '__main__':
    sys.exit(main())
