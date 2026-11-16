# -*- coding: utf-8 -*-
"""从正文提取结构化事实（artifact），供 commit 用

严格按 JSON 返回三个数组；不包 data；不编造正文没有的内容。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO

PROMPT = """从下面这一章正文里提取结构化事实。只输出一个 JSON 对象，不要解释、不要代码块围栏。

{
  "accepted_events": [
    {"type": "promise_created|promise_advanced|promise_closed|state_change|entity_change",
     "subject": "受影响的对象（人物/物品/伏笔编号/地点）",
     "content": "一句话事实，必须是正文里真的写了的事"}
  ],
  "state_deltas": [
    {"subject": "人物名", "field": "当前位置|身上物品|身体状况|钱|年岁|境界", "value": "正文里的新值"}
  ],
  "entity_deltas": [
    {"name": "新出现的专名（人物/地点/物品/组织）", "kind": "person|place|item|org",
     "first_chapter": "%(chapter)s"}
  ]
}

硬约束：
1. 三个字段都必须有；没有内容就给空数组 []。
2. 绝对不要包一层 {"data": {...}}，字段直接放在顶层。
3. 不要编造正文没写的东西；正文没交代的不要猜。
4. accepted_events 最多 12 条，state_deltas 最多 12 条，entity_deltas 最多 8 条。
5. 只提取「事实」，不要评价文笔、不要写建议。

本章正文：
---
%(text)s
---
"""


class ExtractError(ValueError):
    pass


def _parse_json(text):
    s = (text or '').strip()
    i, j = s.find('{'), s.rfind('}')
    if i < 0 or j <= i:
        raise ExtractError('模型没有返回 JSON')
    try:
        return json.loads(s[i:j + 1])
    except ValueError as e:
        raise ExtractError('JSON 解析失败：%s' % e)


def extract_artifacts(book, chapter, text, model='deepseek-flash'):
    """调模型提取 artifact。返回 {accepted_events, state_deltas, entity_deltas}。"""
    body = (text or '').strip()
    if len(body) < 50:
        raise ExtractError('正文太短（%d 字），跳过提取' % len(body))
    prompt = PROMPT % {'chapter': str(chapter).zfill(3), 'text': body[:12000]}
    resp = CO.chat({'model': model, 'temperature': 0.0, 'max_tokens': 1500,
                    'extra_body': {'thinking': {'type': 'disabled'}}},
                   [{'role': 'user', 'content': prompt}])
    data = _parse_json(CO._extract_content(resp))
    if 'data' in data and isinstance(data.get('data'), dict) and 'accepted_events' not in data:
        raise ExtractError('模型包了一层 {"data": {...}}（不合法）')
    out = {}
    for k in ('accepted_events', 'state_deltas', 'entity_deltas'):
        v = data.get(k)
        if v is None:
            raise ExtractError('缺少字段 %s（模型漏了，返回：%s）'
                               % (k, json.dumps(data, ensure_ascii=False)[:120]))
        if not isinstance(v, list):
            raise ExtractError('%s 不是数组，收到 %s' % (k, type(v).__name__))
        out[k] = v
    return out
