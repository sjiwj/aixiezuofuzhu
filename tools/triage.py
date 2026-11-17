# -*- coding: utf-8 -*-
"""用户反馈分诊：把 issue / 质量反馈归到四类，判「能不能自动修」。

输出 JSON：{category, repro_ready, missing, gate, action}
- category: env（装不上/网关/key）| bug（有报错有复现）| quality（读不下去/AI味）| feature（功能请求）
- repro_ready: 是否具备"可自动复现"的最低要素（命令 + 报错/日志 + 版本）
- action: auto-patch（可自动起草补丁）| auto-propose（只能出规则/提示词提案）| human（必须人看）
"""
import json, re, sys

ENV = ('ModuleNotFoundError', 'No module named', 'webview', 'WebView2', 'URLError',
       '10061', '连接', '网关', 'key', '401', '403', '装不上', '起不来', '白屏')
BUG = ('Traceback', 'HTTP', 'error', '报错', '异常', '崩溃', '复现', 'steps', 'expected', 'actual')
QUALITY = ('读不下去', 'AI味', 'AI 味', '人物', '节奏', '对话', '解释句', '像在解释', '弃读', '不好看')
FEATURE = ('希望', '能不能', '建议加', 'feature', '支持一下', '可不可以')

REPRO_KEYS = ('命令', 'cmd', 'python ', 'curl', '步骤', 'steps', '日志', 'log', 'traceback')


def _strip_env_section(text):
    """去掉「## 环境」小节：那里必然写网关、版本、Python 等词，
    不剔除的话任何带环境信息的 bug 都会被误判成 env。"""
    out, skip = [], False
    for line in (text or '').splitlines():
        m = re.match(r'^#{1,3}\s*(.+)$', line.strip())
        if m:
            skip = bool(re.match(r'^(环境|environment)', m.group(1).strip(), re.I))
            if skip:
                continue
        if not skip:
            out.append(line)
    return '\n'.join(out)


def classify(text):
    t = _strip_env_section(text)
    low = t.lower()
    score = {
        'env': sum(1 for k in ENV if k.lower() in low),
        'bug': sum(1 for k in BUG if k.lower() in low),
        'quality': sum(1 for k in QUALITY if k in t),
        'feature': sum(1 for k in FEATURE if k in t),
    }
    cat = max(score, key=score.get)
    if score[cat] == 0:
        cat = 'bug'
    return cat, score


def repro_ready(text):
    low = (text or '').lower()
    has_cmd = any(k in low for k in REPRO_KEYS)
    has_err = bool(re.search(r'(traceback|http\s*\d{3}|error|异常|报错)', low))
    has_ver = bool(re.search(r'(python\s*3|version|版本|windows\s*\d+|win10|win11)', low))
    missing = []
    if not has_cmd:
        missing.append('复现命令/步骤')
    if not has_err:
        missing.append('报错或日志原文')
    if not has_ver:
        missing.append('环境版本')
    return (not missing), missing


def triage(text):
    cat, score = classify(text)
    ready, missing = repro_ready(text)
    if cat == 'quality':
        action, gate = 'auto-propose', 'quality'
    elif cat == 'feature':
        action, gate = 'human', 'scope'
    elif cat == 'env':
        action, gate = ('auto-patch' if ready else 'human'), 'env'
    else:
        action, gate = ('auto-patch' if ready else 'human'), 'bug'
    return {'category': cat, 'scores': score, 'repro_ready': ready,
            'missing': missing, 'action': action, 'gate': gate}


if __name__ == '__main__':
    data = sys.stdin.read() if not sys.argv[1:] else ' '.join(sys.argv[1:])
    print(json.dumps(triage(data), ensure_ascii=False, indent=1))
