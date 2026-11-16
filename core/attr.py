# -*- coding: utf-8 -*-
"""生成失败归因：把异常映射成可统计的归因码（模板 attribution 的裁剪版）。

归因码（对应本项目真实踩过的坑）：
- http_status     非 200（401 = key 失效 / 402 = 旧付费闸 / 429 = 限流）
- network         DNS/超时/连接重置
- empty_output    回包正文为空（实测：thinking 吃满 max_tokens → 0 字）
- parse           结构化解析失败
- missing_field   回包缺必需字段
- unknown         兜底
"""
import json


def classify(exc):
    msg = str(exc)[:200]
    status = getattr(exc, 'status', None) or getattr(exc, 'code', None)
    if isinstance(status, int):
        return {'code': 'http_status', 'status': status, 'message': msg}
    low = msg.lower()
    if isinstance(exc, TimeoutError) or 'timeout' in low or 'timed out' in low:
        return {'code': 'network', 'message': msg}
    if isinstance(exc, OSError) or 'connection' in low or 'urlopen error' in low:
        return {'code': 'network', 'message': msg}
    if isinstance(exc, json.JSONDecodeError):
        return {'code': 'parse', 'message': msg}
    if isinstance(exc, KeyError):
        return {'code': 'missing_field', 'message': msg}
    return {'code': 'unknown', 'message': msg}


def classify_empty(text, usage=None):
    """正文为空时归因：区分「thinking 吃满」与「模型返回空」。"""
    if (text or '').strip():
        return None
    u = usage or {}
    if u.get('completion_tokens') and (u.get('completion_tokens_details') or {}).get('reasoning_tokens'):
        return {'code': 'empty_output', 'message': 'reasoning 吃满 max_tokens，正文为空',
                'reasoning_tokens': u['completion_tokens_details']['reasoning_tokens']}
    return {'code': 'empty_output', 'message': '回包正文为空'}
