# -*- coding: utf-8 -*-
"""计费异常检测（读 new-api 的 logs 表，只读副本，不碰线上库）

检测四条（阈值可在 config/charge_guard.json 覆盖）：
  1. 单令牌 1 小时调用次数 > 100        -> 疑似脚本/共享
  2. 单令牌 1 小时消耗 > 5 元            -> 异常烧额度
  3. 同一令牌出现 3 个以上不同 IP        -> 疑似分享令牌
  4. 某模型调用量比上一小时突增 10 倍    -> 疑似刷量或渠道异常

用法:
    python core/charge_guard.py                 # 看最近 1 小时
    python core/charge_guard.py --hours 6 --json
    python core/charge_guard.py --selftest      # 用合成数据自检四条规则
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO
from errors import human, report          # v1.0.1 错误普通话化：界面只显示中文，原文进日志

DEFAULTS = {
    'calls_per_hour': 100,
    'cny_per_hour': 5.0,
    'distinct_ips': 3,
    'spike_ratio': 10,
    'spike_min_calls': 10,
}
CFG_PATH = os.path.join(CO.ROOT, 'config', 'charge_guard.json')


def load_thresholds():
    th = dict(DEFAULTS)
    try:
        with open(CFG_PATH, encoding='utf-8-sig') as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in DEFAULTS:
                if isinstance(data.get(k), (int, float)):
                    th[k] = data[k]
    except (OSError, ValueError):
        pass
    return th


def db_path():
    g = CO.gateway_cfg()
    return g.get('db_path') or os.path.join('D:' + os.sep, 'relay', 'data', 'new-api.db')


def price_info():
    p = CO.gateway_pricing()
    return float(p.get('quota_per_unit') or 500000), float(p.get('price') or 7.3)


def quota_to_cny(quota, qpu, price):
    return round(float(quota or 0) / qpu * price, 6)


def fetch_rows(since_ts, dbp=None):
    """从 logs 表读计费行（type=2 是消费记录）。用副本读，避免锁线上库。"""
    src = dbp or db_path()
    if not os.path.isfile(src):
        return None, 'db_missing: %s' % src
    tmp = tempfile.mkdtemp(prefix='novelapp_guard_')
    try:
        dst = os.path.join(tmp, 'na.db')
        shutil.copy2(src, dst)
        for suf in ('-wal', '-shm'):
            if os.path.exists(src + suf):
                try:
                    shutil.copy2(src + suf, dst + suf)
                except OSError:
                    pass
        con = sqlite3.connect(dst, timeout=5)
        try:
            cur = con.cursor()
            rows = cur.execute(
                'select token_id, token_name, user_id, ip, model_name, quota, created_at '
                'from logs where type=2 and created_at >= ? order by id', (int(since_ts),)).fetchall()
        finally:
            con.close()
    except Exception as e:
        return None, report(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rows, None


def analyze(rows, now=None, thresholds=None):
    """rows: [(token_id, token_name, user_id, ip, model, quota, created_at)]"""
    th = thresholds or load_thresholds()
    qpu, price = price_info()
    now = now or time.time()
    hour_ago = now - 3600
    prev_ago = now - 7200

    cur_tokens, prev_tokens = {}, {}
    cur_models, prev_models = {}, {}
    for token_id, token_name, user_id, ip, model, quota, ts in rows:
        key = (token_id, token_name or '')
        if ts >= hour_ago:
            rec = cur_tokens.setdefault(key, {'calls': 0, 'quota': 0.0, 'ips': set(),
                                              'user_id': user_id, 'models': {}})
            rec['calls'] += 1
            rec['quota'] += float(quota or 0)
            if ip:
                rec['ips'].add(str(ip))
            rec['models'][model] = rec['models'].get(model, 0) + 1
            cur_models[model] = cur_models.get(model, 0) + 1
        elif ts >= prev_ago:
            prev_tokens[key] = prev_tokens.get(key, 0) + 1
            prev_models[model] = prev_models.get(model, 0) + 1

    alerts = []
    for (token_id, token_name), rec in cur_tokens.items():
        cny = quota_to_cny(rec['quota'], qpu, price)
        if rec['calls'] > th['calls_per_hour']:
            alerts.append({'rule': 'token_calls_per_hour', 'severity': 'warn',
                           'token_id': token_id, 'token_name': token_name,
                           'value': rec['calls'], 'threshold': th['calls_per_hour'],
                           'message': '单令牌 1 小时调用 %d 次（阈值 %d），疑似脚本或令牌共享'
                                      % (rec['calls'], th['calls_per_hour'])})
        if cny > th['cny_per_hour']:
            alerts.append({'rule': 'token_cny_per_hour', 'severity': 'warn',
                           'token_id': token_id, 'token_name': token_name,
                           'value': cny, 'threshold': th['cny_per_hour'],
                           'message': '单令牌 1 小时消耗 %.4f（阈值 %.2f）'
                                      % (cny, th['cny_per_hour'])})
        if len(rec['ips']) > th['distinct_ips']:
            alerts.append({'rule': 'token_multi_ip', 'severity': 'high',
                           'token_id': token_id, 'token_name': token_name,
                           'value': len(rec['ips']), 'threshold': th['distinct_ips'],
                           'ips': sorted(rec['ips'])[:10],
                           'message': '同一令牌出现 %d 个不同 IP（阈值 %d），疑似令牌被分享'
                                      % (len(rec['ips']), th['distinct_ips'])})

    for model, n in cur_models.items():
        prev_n = prev_models.get(model, 0)
        if n >= th['spike_min_calls'] and (prev_n == 0 or n / max(prev_n, 1) >= th['spike_ratio']):
            alerts.append({'rule': 'model_spike', 'severity': 'info', 'model': model,
                           'value': n, 'prev': prev_n,
                           'message': '模型 %s 本小时 %d 次，上小时 %d 次，突增超 %s 倍'
                                      % (model, n, prev_n, th['spike_ratio'])})

    summary = {
        'window_hours': 1,
        'tokens_active': len(cur_tokens),
        'calls': sum(r['calls'] for r in cur_tokens.values()),
        'cny': round(sum(quota_to_cny(r['quota'], qpu, price) for r in cur_tokens.values()), 4),
        'tokens': [{'token_id': t[0], 'token_name': t[1], 'user_id': r['user_id'],
                    'calls': r['calls'], 'cny': quota_to_cny(r['quota'], qpu, price),
                    'ips': len(r['ips']), 'models': r['models']}
                   for t, r in sorted(cur_tokens.items(), key=lambda kv: -kv[1]['calls'])],
        'thresholds': th, 'quota_per_unit': qpu, 'price': price,
    }
    return {'alerts': alerts, 'summary': summary, 'ok': True}


def selftest():
    """合成数据，验证四条规则都能触发。"""
    now = time.time()
    base = dict(user_id=3, token_name='novelapp-client', token_id=6, model_name='deepseek-flash')
    rows = []
    for i in range(120):                       # 120 次调用 + 多 IP + 大额度
        rows.append((6, 'novelapp-client', 3, '10.0.0.%d' % (i % 5), 'deepseek-flash',
                     400000 if i == 0 else 1, now - 60 * (i % 50)))
    for i in range(20):                        # 上小时 20 次 deepseek-flash，本小时 120 -> 6x，不触发 spike
        rows.append((7, 'other', 4, '10.0.1.1', 'glm-5.3', 1, now - 3700 - i))
    for i in range(40):                        # 本小时 glm-5.3 40 次，上小时 1 次 -> 触发 spike
        rows.append((8, 'third', 5, '10.0.2.2', 'glm-5.3', 1, now - 60 * (i % 30)))
    res = analyze(rows, now=now)
    rules = {a['rule'] for a in res['alerts']}
    want = {'token_calls_per_hour', 'token_cny_per_hour', 'token_multi_ip', 'model_spike'}
    missing = want - rules
    print('自检：命中规则 %s' % sorted(rules))
    for a in res['alerts']:
        print('  [%s] %s' % (a['severity'], a['message']))
    if missing:
        print('缺失规则：%s' % sorted(missing))
        return 1
    print('四条规则全部命中 ✅')
    return 0


def main():
    ap = argparse.ArgumentParser(description='计费异常检测（只读 new-api logs 表）')
    ap.add_argument('--hours', type=float, default=1.0, help='回看小时数（默认 1）')
    ap.add_argument('--db', default=None, help='new-api.db 路径（默认取网关配置）')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--selftest', action='store_true', help='用合成数据自检四条规则')
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    since = time.time() - args.hours * 3600
    rows, err = fetch_rows(since, args.db)
    if err:
        print('[错误] %s' % err, file=sys.stderr)
        return 2
    res = analyze(rows)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if not res['alerts'] else 1

    s = res['summary']
    print('窗口：最近 %g 小时   活跃令牌 %d   调用 %d 次   消耗 %.4f' % (
        args.hours, s['tokens_active'], s['calls'], s['cny']))
    if s['tokens']:
        print('%-6s %-18s %-6s %6s %10s %5s' % ('token', 'name', 'user', 'calls', 'CNY', 'ips'))
        for t in s['tokens'][:12]:
            print('%-6s %-18s %-6s %6d %10.4f %5d' % (
                t['token_id'], t['token_name'][:18], t['user_id'], t['calls'], t['cny'], t['ips']))
    if not res['alerts']:
        print('无异常（阈值：%s 次/时，%s/时，%s 个 IP，%sx 突增）' % (
            s['thresholds']['calls_per_hour'], s['thresholds']['cny_per_hour'],
            s['thresholds']['distinct_ips'], s['thresholds']['spike_ratio']))
        return 0
    print('')
    for a in res['alerts']:
        print('[%s] %s' % (a['severity'].upper(), a['message']))
    return 1


if __name__ == '__main__':
    sys.exit(main())
