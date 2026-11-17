# -*- coding: utf-8 -*-
"""AI 痕迹检测：判一段文字「有多像 AI 写的」。

只给疑似程度，不判作者身份、不下断论。
为什么单开一个文件：这是「文本特征评估」，和四关机检（precheck，规则判定）
不是一回事；也不属于审稿团（那是多角色投票）。挪进任何一个都会互相污染。

调用口径和 breakdown_ui 的 _run_dim 一致：thinking 层 → CO.chat →
CO._extract_content → CO.sanitize_worker_text（只用于错误兜底展示）。

返回：
    {ok, score, verdict, suspects, tips, model, ms,
     # 附加（前端用得上，不影响上面那套契约）
     chars, truncated, note, raw?, error?}

score 0-100，越高越像人写的；verdict = human | mixed | ai。
"""
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coordinator as CO
from errors import human, report          # v1.0.1 错误普通话化：界面只显示中文，原文进日志

MAX_CHARS = 6000          # 只判前 6000 字（单次调用成本很低，再长没有收益）
MIN_CHARS = 80            # 短于这个长度，特征不够，判了也是猜
MAX_SUSPECTS = 4
TIPS_MAX = 5


_SYS = (
    '你是中文小说的文本风格分析器。任务是估一段文字「有多像 AI 生成」的疑似程度，'
    '只依据文本特征下判断，不推测作者身份，不下断定结论。\n\n'
    '只看这些特征（命中越多，越像 AI）：\n'
    '1. 套话与空泛概括：「在这个……的时代」「首先/其次/综上所述」「不仅……而且」'
    '「让人不禁」「仿佛整个世界都……」\n'
    '2. 结构过于整齐：段落等长、三点排比、总分总模板、每段都收在一句总结上\n'
    '3. 比喻多但不具体，几个比喻彼此同类（都在写"潮水""光芒""巨浪"）\n'
    '4. 缺具体动作与器物，靠抽象情绪词撑场面（震撼、复杂、难以言喻、五味杂陈）\n'
    '5. 对话像在互相解释设定，谁说话都一样，没有口癖\n'
    '6. 句子节奏单一：每句都完整，没有省略、没有半截话、没有废话\n'
    '7. 结尾爱升华、爱总结意义\n\n'
    '反过来，人写的常见特征：句子长短不齐、有岔开的废话、具体到器物/价钱/天气、'
    '口语和半截话、比喻土但准、段落忽然跳到别处。\n\n'
    '评分口径（score 为整数 0-100，越高越像人写的）：\n'
    '- 75-100：明显人写（具体细节、口语、结构不整齐）\n'
    '- 40-74：混合（有真人痕迹，也有整段模板腔）\n'
    '- 0-39：明显 AI 腔（套话、排比、空泛情绪总结占主导）\n'
    'verdict 只能是 "human" / "mixed" / "ai"，与上面三个区间对应。\n\n'
    '直接给结论：不要逐条分析文本，不要在输出前写推理过程。\n'
    '输出：只输出一个 JSON 对象，不要代码块标记，不要任何解释文字。字段固定：\n'
    '{"score": 0到100的整数,\n'
    ' "verdict": "human|mixed|ai",\n'
    ' "suspects": [{"quote": "原文原句，最多40字", "reason": "为什么可疑，20字内"}],\n'
    ' "tips": ["具体怎么改，一句话一条"]}\n\n'
    '硬要求：\n'
    '- suspects 只放真正可疑的句子，0-4 条；quote 必须逐字来自原文，不许改写或拼接\n'
    '- tips 3-5 条，给可执行的改法（补什么细节、砍哪句、换成什么说法），'
    '不要写「增加人味」「更自然」这种空话\n'
    '- 不许写「这是 AI 写的」「作者是 AI」这类断定；你给的是疑似程度'
)


def _user(title, body, truncated, total):
    head = []
    if title:
        head.append('标题：%s' % title)
    if truncated:
        head.append('注意：原文共 %d 字，这里只有前 %d 字（截断），判断只针对这段。'
                    % (total, MAX_CHARS))
    head.append('=== 正文（%d 字）===\n%s' % (len(body), body))
    return '\n'.join(head)


def _thinking_cfg(think=False):
    """thinking 层配置。**默认关思考**，只有显式 think=True 才开。

    踩过两次坑，第二次更隐蔽：
    ① 上限卡 4000 → 长章（3500 字以上）返回空；
    ② 上限提到 8000 仍然在**真人稿 4198 字 + 6 条改写**时返回空 ——
       因为 layers.yaml 的 thinking 层写着 `thinking: true`，v4-pro 拿 8000 预算
       先思考再输出，reasoning 吃光后剩不下 6 条改写的量。
    结论：判风格和给改法都是模式识别，不需要长推理。一律关掉，
    预算给到 12000 兜住长输入；真要开就传 think=True。
    """
    layer = CO.resolve_layer('thinking') or {}
    budget = int(layer.get('max_tokens') or 4000)
    cfg = {'model': layer.get('model') or 'deepseek-v4-pro',
           'temperature': layer.get('temperature', 0.3),
           'max_tokens': max(2000, min(budget, 12000))}
    if think:
        cfg['extra_body'] = {'thinking': {'type': 'enabled'}}
    return cfg


def _strip_fence(text):
    t = (text or '').strip()
    t = re.sub(r'^\x60\x60\x60[a-zA-Z]*\s*', '', t)
    t = re.sub(r'\s*\x60\x60\x60\s*$', '', t)
    return t.strip()


def _parse_json_obj(text):
    """从模型输出里抠出第一个 JSON 对象；抠不出返回 None。"""
    t = _strip_fence(text)
    if not t:
        return None
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else None
    except ValueError:
        pass
    start = t.find('{')
    end = t.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        v = json.loads(t[start:end + 1])
        return v if isinstance(v, dict) else None
    except ValueError:
        return None


_VERDICT_WORDS = {'human': 'human', '人': 'human', '人工': 'human', '人写': 'human',
                  'mixed': 'mixed', '混合': 'mixed', '参半': 'mixed',
                  'ai': 'ai', '像 ai': 'ai', '机器': 'ai', '模型': 'ai'}


def _norm_score(v):
    """分数归一：兼容 0-1、字符串、带百分号；夹到 0-100。"""
    if isinstance(v, str):
        s = v.strip().replace('％', '%').replace('%', '')
        try:
            v = float(s)
        except ValueError:
            return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    n = float(v)
    if 0 < n <= 1:
        n = n * 100
    return int(max(0, min(100, round(n))))


def _verdict_of(score, raw):
    key = str(raw or '').strip().lower()
    if key in _VERDICT_WORDS:
        return _VERDICT_WORDS[key]
    if score is None:
        return ''
    if score >= 70:
        return 'human'
    if score >= 40:
        return 'mixed'
    return 'ai'


def _clip_quote(s):
    q = re.sub(r'\s+', ' ', str(s or '')).strip().strip('“”"\'')
    return q[:40]


def _norm_suspects(v):
    out = []
    if not isinstance(v, list):
        return out
    for it in v:
        if isinstance(it, str):
            q, why = it, ''
        elif isinstance(it, dict):
            q = it.get('quote') or it.get('text') or it.get('句') or ''
            why = it.get('reason') or it.get('why') or it.get('reason_text') or ''
        else:
            continue
        q = _clip_quote(q)
        if not q:
            continue
        why = re.sub(r'\s+', ' ', str(why or '')).strip()[:60]
        out.append({'quote': q, 'reason': why})
        if len(out) >= MAX_SUSPECTS:
            break
    return out


def _norm_tips(v):
    out = []
    if not isinstance(v, list):
        return out
    for it in v:
        if isinstance(it, dict):
            it = it.get('tip') or it.get('text') or ''
        s = re.sub(r'\s+', ' ', str(it or '')).strip()
        if not s:
            continue
        if s.startswith(('1.', '2.', '3.', '4.', '5.', '-', '·')):
            s = s.lstrip('12345.-· ').strip()
        if s:
            out.append(s[:120])
        if len(out) >= TIPS_MAX:
            break
    return out


def detect(text, title=''):
    """判一段文字有多像 AI 写的。

    返回 {ok, score, verdict, suspects, tips, model, ms}
    score 0-100（越高越像人写），verdict = human | mixed | ai。
    模型没按 JSON 回、或调用失败时 ok=False，并带 raw（原始输出前 200 字）/ error。
    """
    t0 = time.time()
    raw_text = text if isinstance(text, str) else ''
    total = len(raw_text)
    body = raw_text[:MAX_CHARS]
    truncated = total > MAX_CHARS
    cfg = _thinking_cfg()
    model = cfg.get('model') or ''

    def _fail(msg, raw=''):
        out = {'ok': False, 'error': msg, 'model': model,
               'ms': int((time.time() - t0) * 1000),
               'chars': len(body), 'truncated': truncated}
        if raw:
            out['raw'] = CO.sanitize_worker_text(raw, 200)
        return out

    if len(body.strip()) < MIN_CHARS:
        return _fail('文本太短（%d 字，至少 %d 字才判得出特征）'
                     % (len(body.strip()), MIN_CHARS))

    messages = [{'role': 'system', 'content': _SYS},
                {'role': 'user', 'content': _user(title, body, truncated, total)}]
    try:
        resp = CO.chat(cfg, messages)
    except Exception as e:
        if cfg.get('extra_body'):
            # 有的通道不认 thinking 扩展参数：去掉再试一次（thinking 层本来就默认思考）
            cfg2 = dict(cfg)
            cfg2.pop('extra_body', None)
            try:
                resp = CO.chat(cfg2, messages)
                model = model or cfg2.get('model') or ''
            except Exception as e2:
                return _fail(report(e2))
        else:
            return _fail(report(e))
    try:
        model = str(resp.get('model') or model)
        out_text = CO._extract_content(resp) or ''
    except Exception as e:
        return _fail(report(e))
    if not out_text.strip():
        return _fail('模型没有输出（可能是 max_tokens 被思考吃光）')

    obj = _parse_json_obj(out_text)
    if obj is None:
        return _fail('模型没有返回可解析的 JSON', out_text)

    score = _norm_score(obj.get('score', obj.get('分数')))
    verdict = _verdict_of(score, obj.get('verdict') or obj.get('判定'))
    if score is None:
        return _fail('模型给了 JSON 但没有有效 score', out_text)
    suspects = _norm_suspects(obj.get('suspects') or obj.get('可疑句'))
    tips = _norm_tips(obj.get('tips') or obj.get('建议'))
    if not tips:
        # 一条建议都没有等于没给改法：补一条最保守的，不假装是模型分析
        tips = ['挑 suspects 里第一条，补一个具体动作或器物细节，再读一遍']

    res = {'ok': True, 'score': score, 'verdict': verdict,
           'suspects': suspects, 'tips': tips[:TIPS_MAX],
           'model': model, 'ms': int((time.time() - t0) * 1000),
           'chars': len(body), 'truncated': truncated}
    if truncated:
        res['note'] = '原文 %d 字，只判了前 %d 字' % (total, MAX_CHARS)
    return res

# ======================================================================
# 去痕改写建议（suggest）
#
# 和 detect 分开的原因：detect 判「像不像 AI」，suggest 给「这一处怎么改」。
# 这里只给**局部**建议，绝不整篇重写 —— 整篇重写会把作者自己的腔调洗掉，
# 那比 AI 味更难救。调用方（server / 前端）只展示、只进剪贴板，不落盘。
# ======================================================================

MAX_REWRITES = 6          # 最多给 6 处；再多就不像人改的，是重写了
QUOTE_MAX = 120           # before 上限（字）
LEN_TOL = 0.30            # after 与 before 长度允许偏离 ±30%
_BOUNDARY_END = '。！？…'
_BOUNDARY_MID = '；，、,.!?;'


_REWRITE_SYS = (
    '你是中文小说的改稿助手。任务：挑出这段里**最像 AI 写的几处**，'
    '每处给一个局部改写建议。作者自己决定用不用，你只给建议。\n\n'
    '先看哪里像 AI：套话（「在这个……的时代」「让人不禁」「仿佛整个世界」）、'
    '三点排比、总分总模板、抽象情绪词（震撼、复杂、五味杂陈、难以言喻）、'
    '比喻多但不具体、对话像在互相解释设定、每句都完整没有半截话、结尾升华总结。\n\n'
    '先给一个总体判断 ai_flavor（这段整体有多像 AI）：\n'
    '- "heavy"：套话、排比、空泛情绪、结尾升华占主导 → 给 3-6 处\n'
    '- "light"：整体是人的写法，只有个别句子带腔调 → 给 0-2 处\n'
    '- "none"：句子具体、长短不齐、有口语 → 给 0 处（rewrites 用空数组）\n\n'
    '判 light / none 时特别注意：下面这些是**人写的好东西，不算 AI 味，不许动**——\n'
    '- 带具体价物、器物、天气的对偶：「柴价贱，贱到一担柴换不回半双草鞋」\n'
    '- 短句点题、说一半就收住：「他算过一回，算完就不算了。」\n'
    '- 土词、口语、半截话、故意重复的句式（那是节奏）\n'
    '工整本身不是罪，空泛才是。只有一句里**没有具体东西、只剩情绪和总结**时，才算 AI 腔。\n'
    '**不许为了凑数去动好句子**；宁少勿多。\n\n'
    '改写方向（每处选一种，不要每条都用同一招）：\n'
    '1. 补具体：动作、器物、价钱、天气、气味、声音\n'
    '2. 拆排比：三个并列砍成一个，或让其中两个故意不对齐\n'
    '3. 去升华：删掉总结句，让场景自己停住\n'
    '4. 加口语：半截话、口头语、语序颠倒、一句废话\n'
    '5. 换土比喻：用本地、具体、有点脏的比喻替掉空泛的\n\n'
    '硬要求（违反任一条这次就白改）：\n'
    '- 保留原意、人物口吻、时代背景；不要换成另一种文风（不要突然文艺，不要网络腔）\n'
    '- 人名、地名、称谓、数字、价钱、专有名词照抄，一个都不许换，也不许新加\n'
    '- 只改一处，不许整段重写，不许调整段落顺序，不许合并或拆分段落\n'
    '- before 必须**逐字抄原文**：一个字都不许改，不许拼接、不许用省略号代替、'
    '不许补标点，最长 120 字（挑一句或半句就够）\n'
    '- after 字数和 before 接近，控制在 ±30% 以内（before 30 字 → after 21-39 字）\n'
    '- 不要写分析过程，不要解释你怎么想的\n\n'
    '输出：只输出一个 JSON 对象，不要代码块标记，不要任何解释文字。字段固定：\n'
    '{"ai_flavor": "heavy|light|none",\n'
    ' "rewrites": [{"before": "原文那一句（逐字）", "after": "改后的同位置文字", '
    '"why": "为什么这么改，20字内"}]}\n'
    'rewrites 是数组，条数按 ai_flavor 走（heavy 3-6 / light 0-2 / none 0），'
    '按「最像 AI」的程度从高到低排。'
)


def _rewrite_user(title, body, truncated, total, focus):
    head = []
    if title:
        head.append('标题：%s' % title)
    if truncated:
        head.append('注意：原文共 %d 字，这里只有前 %d 字（截断），只改这一段里的地方。'
                    % (total, MAX_CHARS))
    if focus:
        head.append('这次特别看：%s' % focus)
    head.append('=== 正文（%d 字）===\n%s' % (len(body), body))
    return '\n'.join(head)


def _squash_map(s):
    """压掉空白，同时记住每个字在原文里的下标。"""
    out = []
    idx = []
    for i, ch in enumerate(s):
        if ch.isspace():
            continue
        out.append(ch)
        idx.append(i)
    return ''.join(out), idx


def _locate(body, quote):
    """在 body 里找 quote，返回 (start, end)；找不到返回 None。

    先按原样找；找不到再把空白压掉找一遍 —— 模型常把换行吃掉、或往中间塞空格。
    返回的 end 是**原文坐标**，所以 body[start:end] 一定逐字等于原文。
    """
    q = str(quote or '').strip()
    if not q:
        return None
    i = body.find(q)
    if i >= 0:
        return (i, i + len(q))
    sq, idx = _squash_map(body)
    qn = re.sub(r'\s+', '', q)
    if not qn:
        return None
    k = sq.find(qn)
    if k < 0:
        return None
    return (idx[k], idx[k + len(qn) - 1] + 1)


def _cut_len(s, limit):
    """把 s 截到不超过 limit 字，尽量切在标点上（返回截断后的长度）。"""
    if len(s) <= limit:
        return len(s)
    head = s[:limit]
    for group in (_BOUNDARY_END, _BOUNDARY_MID):
        pos = -1
        for ch in group:
            p = head.rfind(ch)
            if p > pos:
                pos = p
        # 太靠前切了会把整句砍没，退化成硬截
        if pos >= max(8, int(limit * 0.5)):
            return pos + 1
    return limit


_TOKEN_NUM = re.compile(r'\d+(?:\.\d+)?')
_TOKEN_QUOTED = re.compile(r'[\u300c\u201c"\u300a]([^\u300d\u201d"\u300b]{1,10})[\u300d\u201d"\u300b]')


def _lost_bits(before, after):
    """改后丢掉的数字/引号里的专名：人名地名价钱最容易被模型顺手换掉。"""
    lost = []
    for m in _TOKEN_NUM.finditer(before):
        if m.group(0) not in after:
            lost.append(m.group(0))
    for m in _TOKEN_QUOTED.finditer(before):
        if m.group(1) not in after:
            lost.append(m.group(1))
    return lost[:3]


_LEVEL_WORDS = {'heavy': 'heavy', '重': 'heavy', '明显': 'heavy', '严重': 'heavy',
                'light': 'light', '轻': 'light', '轻微': 'light', '略': 'light',
                'none': 'none', '无': 'none', '没有': 'none', '不像': 'none'}


def _norm_level(v):
    """模型的总体判断：heavy / light / none；认不出返回空串（按重处理）。"""
    return _LEVEL_WORDS.get(str(v or '').strip().lower(), '')


def _norm_rewrites(obj, body):
    """把模型给的 rewrites 过一遍：逐字定位、限长、查长度、去重叠。

    返回 (items, dropped, reason_counts)。items 里的 before 全部取自 body 切片，
    所以「逐字来自原文」是构造出来的，不是靠模型自觉。
    """
    raw = None
    for key in ('rewrites', 'rewrite', 'items', '改写', '建议'):
        v = obj.get(key)
        if isinstance(v, list):
            raw = v
            break
    if raw is None:
        return None, 0, {}
    items = []
    spans = []
    dropped = 0
    reasons = {}
    for it in raw:
        if not isinstance(it, dict):
            dropped += 1
            reasons['格式不对'] = reasons.get('格式不对', 0) + 1
            continue
        bq = it.get('before') or it.get('原') or it.get('原句') or it.get('quote') or ''
        aq = it.get('after') or it.get('改') or it.get('改后') or it.get('rewrite') or ''
        why = it.get('why') or it.get('reason') or it.get('为什么') or ''
        span = _locate(body, bq)
        if not span:
            dropped += 1
            reasons['对不上原文'] = reasons.get('对不上原文', 0) + 1
            continue
        a, b = span
        before = body[a:b]
        after = re.sub(r'\r', '', str(aq or '')).strip()
        if not after:
            dropped += 1
            reasons['改后为空'] = reasons.get('改后为空', 0) + 1
            continue
        # before 超长：切在标点上，after 按同比例收，保住长度关系。
        # 注意 after 的收尾只在这里做：顺手砍掉句子后半截会把语义改坏，
        # 「after 太长」一律走下面的长度校验直接丢，不硬截。
        if len(before) > QUOTE_MAX:
            if len(before) > QUOTE_MAX * 1.5:
                dropped += 1
                reasons['before 太长'] = reasons.get('before 太长', 0) + 1
                continue
            cut = _cut_len(before, QUOTE_MAX)
            ratio = cut / float(len(before))
            b = a + cut
            before = body[a:b]
            if ratio < 1:
                after = after[:max(1, int(round(len(after) * ratio)))]
                after = after.rstrip().rstrip('，、；：,;:')
                if not after:
                    dropped += 1
                    reasons['改后为空'] = reasons.get('改后为空', 0) + 1
                    continue
        bl, al = len(before), len(after)
        if bl < 6:
            dropped += 1
            reasons['太短'] = reasons.get('太短', 0) + 1
            continue
        if after == before:
            dropped += 1
            reasons['没改'] = reasons.get('没改', 0) + 1
            continue
        if al < bl * (1 - LEN_TOL) or al > bl * (1 + LEN_TOL):
            dropped += 1
            reasons['长度差太多'] = reasons.get('长度差太多', 0) + 1
            continue
        if any(not (b <= s or a >= e) for (s, e) in spans):
            dropped += 1
            reasons['重叠'] = reasons.get('重叠', 0) + 1
            continue
        item = {'before': before, 'after': after,
                'why': re.sub(r'\s+', ' ', str(why or '')).strip()[:40]}
        lost = _lost_bits(before, after)
        if lost:
            item['warn'] = '改后少了「%s」，粘之前对一眼' % '、'.join(lost)
        items.append((a, item))
        spans.append((a, b))
        if len(items) >= MAX_REWRITES:
            break
    items.sort(key=lambda x: x[0])
    return [x[1] for x in items], dropped, reasons


def suggest(text, title='', focus=None):
    """给「去痕改写建议」：只挑 3-6 处最像 AI 的地方，给局部改写。

    返回 {ok, rewrites: [{before, after, why}], model, ms, chars, truncated}
    before 逐字来自原文（构造保证）；after 长度在 before ±30% 内。
    调用/解析失败时 ok=False，并带 raw（原始输出前 200 字）/ error —— 和 detect 同一套降级。
    **只读**：不改正文、不落盘，用不用由作者自己粘。
    """
    t0 = time.time()
    raw_text = text if isinstance(text, str) else ''
    total = len(raw_text)
    body = raw_text[:MAX_CHARS]
    truncated = total > MAX_CHARS
    cfg = _thinking_cfg()
    model = cfg.get('model') or ''
    focus_s = str(focus or '').strip()[:60]

    def _fail(msg, raw=''):
        out = {'ok': False, 'error': msg, 'rewrites': [], 'model': model,
               'ms': int((time.time() - t0) * 1000),
               'chars': len(body), 'truncated': truncated}
        if raw:
            out['raw'] = CO.sanitize_worker_text(raw, 200)
        return out

    if len(body.strip()) < MIN_CHARS:
        return _fail('文本太短（%d 字，至少 %d 字才给得出改写建议）'
                     % (len(body.strip()), MIN_CHARS))

    messages = [{'role': 'system', 'content': _REWRITE_SYS},
                {'role': 'user', 'content': _rewrite_user(title, body, truncated, total, focus_s)}]
    try:
        resp = CO.chat(cfg, messages)
    except Exception as e:
        if cfg.get('extra_body'):
            cfg2 = dict(cfg)
            cfg2.pop('extra_body', None)
            try:
                resp = CO.chat(cfg2, messages)
                model = model or cfg2.get('model') or ''
            except Exception as e2:
                return _fail(report(e2))
        else:
            return _fail(report(e))
    try:
        model = str(resp.get('model') or model)
        out_text = CO._extract_content(resp) or ''
    except Exception as e:
        return _fail(report(e))
    if not out_text.strip():
        return _fail('模型没有输出（可能是 max_tokens 被思考吃光）')

    obj = _parse_json_obj(out_text)
    if obj is None:
        return _fail('模型没有返回可解析的 JSON', out_text)

    rewrites, dropped, reasons = _norm_rewrites(obj, body)
    if rewrites is None:
        return _fail('模型给了 JSON 但没有 rewrites 数组', out_text)
    # 模型自报的整体判断决定条数上限：说「没什么 AI 味」就不许硬凑几处
    level = _norm_level(obj.get('ai_flavor') or obj.get('flavor') or obj.get('判断'))
    cap = {'none': 0, 'light': 2}.get(level, MAX_REWRITES)
    cut_by_cap = max(0, len(rewrites) - cap)
    if cut_by_cap:
        rewrites = rewrites[:cap]
    if not rewrites:
        if cap == 0 or (dropped == 0 and cut_by_cap == 0):
            # 模型自己说「没什么 AI 味」/ 给了空数组：合法结论，不当失败
            note = '模型判断这段没有明显 AI 味' if cap == 0 else '模型认为这段没有明显需要去痕的地方'
            if cut_by_cap:
                note += '（另给了 %d 处较轻的，按「轻」的上限没收）' % cut_by_cap
            if truncated:
                note += '；原文 %d 字，只看了前 %d 字' % (total, MAX_CHARS)
            return {'ok': True, 'rewrites': [], 'model': model,
                    'ms': int((time.time() - t0) * 1000),
                    'chars': len(body), 'truncated': truncated, 'note': note}
        # 给了几处但一处都对不上原文：不能假装成功，把原始输出带回去好排查
        return _fail('模型给了 %d 处，但都对不上原文或长度差太多' % dropped, out_text)

    res = {'ok': True, 'rewrites': rewrites, 'model': model,
           'ms': int((time.time() - t0) * 1000),
           'chars': len(body), 'truncated': truncated}
    notes = []
    if cut_by_cap:
        notes.append('模型判「%s」，只留前 %d 处（另有 %d 处较轻的没收，宁少勿多）'
                     % (level, cap, cut_by_cap))
    if dropped:
        detail = '、'.join('%s %d' % (k, v) for k, v in reasons.items())
        notes.append('%d 处没过校验已丢掉（%s）' % (dropped, detail))
    if truncated:
        notes.append('原文 %d 字，只看了前 %d 字' % (total, MAX_CHARS))
    if notes:
        res['note'] = '；'.join(notes)
    return res

