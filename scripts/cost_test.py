# -*- coding: utf-8 -*-
"""四层流水线写一章的真实成本测试

研究层 glm-5.3 / 思维层 deepseek-flash / 写作层 kimi-k3 / 质检层 deepseek-flash
统计每层 token 与实际花费。
"""
import json, os, sqlite3, sys, time
from urllib import request

ROOT = r'D:\NovelApp'
DB = 'D:/relay/data/new-api.db'


def keys():
    con = sqlite3.connect('file:' + DB + '?mode=ro', uri=True)
    d = {}
    for name, base, key in con.execute('select name,base_url,key from channels'):
        d[name] = (base.rstrip('/'), key)
    return d


K = keys()


PATHS = {
    'zhipu-glm': '/api/paas/v4/chat/completions',
    'deepseek': '/v1/chat/completions',
    'moonshot-kimi': '/v1/chat/completions',
}


def call(channel, model, messages, max_tokens=2000, timeout=180, temp=True, no_think=True):
    base, key = K[channel]
    url = base + PATHS.get(channel, '/v1/chat/completions')
    payload = {'model': model, 'messages': messages, 'max_tokens': max_tokens}
    if temp:
        payload['temperature'] = 0.7
    # 关闭思考：实测 Kimi 446→69 token、速度快 2 倍、正文更多
    if no_think and channel != 'zhipu-glm':   # 智谱不接受该参数（400）
        payload['thinking'] = {'type': 'disabled'}
    body = json.dumps(payload).encode()
    req = request.Request(url, data=body, headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + key})
    t0 = time.time()
    last = None
    for attempt in range(3):
        try:
            with request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read().decode())
            break
        except Exception as e:
            last = e
            time.sleep(3)
    else:
        raise last
    u = j.get('usage') or {}
    return (j['choices'][0]['message'].get('content') or ''), u, time.time() - t0


def main():
    ch1 = open(os.path.join(ROOT, 'projects/<书名>/章节/001-第一章-柴没砍完.md'), encoding='utf-8').read()
    ctx = ch1[:6000]   # 用第一章前 6000 字当上下文

    stages = []

    # ---------- 1. 研究层 ----------
    print('【1/4】研究层 glm-5.3 ...', flush=True)
    p1 = [{'role': 'user', 'content':
           '你是研究层。下面是一章正文，请整理出：出场人物、地点、可用物件、埋下的线索。\n'
           '每条一行，不要解释，不要写正文。\n\n' + ctx}]
    out1, u1, t1 = call('zhipu-glm', 'glm-5.3', p1, 2500)
    stages.append(('研究层', 'glm-5.3', u1, t1, out1))
    print(f'    token {u1.get("prompt_tokens")}+{u1.get("completion_tokens")}  {t1:.1f}s', flush=True)

    # ---------- 2. 思维层 ----------
    print('【2/4】思维层 deepseek-flash ...', flush=True)
    p2 = [{'role': 'user', 'content':
           '你是思维层。根据素材，规划第二章：3 个场景、每场一句话要点、结尾留什么钩子。\n'
           '不要写正文。\n\n素材：\n' + out1[:2500]}]
    out2, u2, t2 = call('deepseek', 'deepseek-flash', p2, 2500)
    stages.append(('思维层', 'deepseek-flash', u2, t2, out2))
    print(f'    token {u2.get("prompt_tokens")}+{u2.get("completion_tokens")}  {t2:.1f}s', flush=True)

    # ---------- 3. 写作层 ----------
    print('【3/4】写作层 kimi-k3 ...', flush=True)
    p3 = [{'role': 'user', 'content':
           '你是写作层。按下面的规划写第二章正文，2000 字左右。\n'
           '文风：短句、白描、不解释、不总结、不用「不是…而是…」句式。只输出正文。\n\n'
           '上一章结尾：\n' + ctx[-800:] + '\n\n本章规划：\n' + out2[:2000]}]
    out3, u3, t3 = call('moonshot-kimi', 'kimi-k3', p3, 4000, timeout=600, temp=False, no_think=True)
    stages.append(('写作层', 'kimi-k3', u3, t3, out3))
    print(f'    token {u3.get("prompt_tokens")}+{u3.get("completion_tokens")}  {t3:.1f}s', flush=True)

    # ---------- 4. 质检层 ----------
    print('【4/4】质检层 deepseek-flash ...', flush=True)
    p4 = [{'role': 'user', 'content':
           '你是质检层。只挑错：节奏、重复、人物是否走样、有没有 AI 味。\n'
           '最多 5 条，每条一行，指出问题即可，不要改稿。\n\n' + out3[:4000]}]
    out4, u4, t4 = call('deepseek', 'deepseek-flash', p4, 2000)
    stages.append(('质检层', 'deepseek-flash', u4, t4, out4))
    print(f'    token {u4.get("prompt_tokens")}+{u4.get("completion_tokens")}  {t4:.1f}s', flush=True)

    # 各层输出落盘便于检查
    for nm, _, _, _, txt in stages:
        open(os.path.join(ROOT, 'reports', f'cost_{nm}.txt'), 'w', encoding='utf-8').write(txt or '(空)')

    # ---------- 汇总 ----------
    PRICE = {  # 元/百万 token (输入, 输出)
        'glm-5.3': (4.0, 16.0),
        'glm-5.3-flash': (0.5, 2.0),
        'glm-4.5-air': (0.5, 2.0),
        'deepseek-v4-pro': (4.0, 12.0),
        'deepseek-flash': (1.0, 2.0),
        'kimi-k3': (4.0, 16.0),
    }
    print('\n' + '=' * 74)
    print(f'{"层":<8}{"模型":<18}{"输入":>9}{"输出":>8}{"其中思考":>10}{"耗时":>8}{"成本(元)":>11}')
    print('-' * 74)
    tp = tc = 0
    tt = 0.0
    total_cost = 0.0
    for name, model, u, t, _ in stages:
        pi = u.get('prompt_tokens', 0)
        po = u.get('completion_tokens', 0)
        pr = PRICE.get(model, (1.0, 2.0))
        c = pi / 1e6 * pr[0] + po / 1e6 * pr[1]
        total_cost += c
        tp += pi; tc += po; tt += t
        rt = (u.get('completion_tokens_details') or {}).get('reasoning_tokens', 0)
        print(f'{name:<8}{model:<18}{pi:>9}{po:>8}{rt:>10}{t:>7.1f}s{c:>11.4f}')
    print('-' * 74)
    print(f'{"合计":<8}{"":<18}{tp:>9}{tc:>8}{"":>10}{tt:>7.1f}s{total_cost:>11.4f}')
    print('=' * 74)
    print(f'输出字数: {len(out3)}   每千字成本: {total_cost / max(len(out3),1) * 1000:.4f} 元')

    json.dump({'stages': [{'name': n, 'model': m, 'usage': u, 'sec': round(t,1)} for n, m, u, t, _ in stages],
               'total': {'prompt_tokens': tp, 'completion_tokens': tc, 'cost_cny': round(total_cost, 4),
                         'output_chars': len(out3)}},
              open(os.path.join(ROOT, 'reports', 'cost_test.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)

    # 保存产出，方便看质量
    open(os.path.join(ROOT, 'reports', 'cost_test_ch2.md'), 'w', encoding='utf-8').write(out3)
    open(os.path.join(ROOT, 'reports', 'cost_test_review.md'), 'w', encoding='utf-8').write(out4)
    print('\n产出: reports/cost_test_ch2.md, reports/cost_test_review.md')


if __name__ == '__main__':
    main()
