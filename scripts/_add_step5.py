# -*- coding: utf-8 -*-
import io, os, sys
P = r"D:\NovelApp\core\server.py"
TMP = P + ".tmp"
s = io.open(P, encoding="utf-8").read()
if "step 5 审稿团" in s:
    print("ALREADY"); sys.exit(0)

ANCHOR = """        # 承诺自动 touch\uff1a\u53ea\u6709\u7ae0\u7eb2\u660e\u786e\u6307\u5b9a\uff08plan\uff09\u624d\u767b\u8bb0\uff1bauto \u53ea\u63d0\u793a\u4e0d\u731c"""
if ANCHOR not in s:
    print("anchor missing"); sys.exit(1)

SIDE = """        # step 5 \u5ba1\u7a3f\u56e2\uff08\u53ea\u5728 pipeline=true \u65f6\u8dd1\uff09\u3002\u8bfb\u53d6\u914d\u7f6e\u7684\u5ba1\u7a3f\u4eba\uff0c\u5e76\u884c\u5404\u51fa\u4e00\u4efd\u610f\u89c1\uff0c
        # \u7136\u540e\u7528 extract_consensus \u88c1\u51b3\u6210 \u5fc5\u6539/\u5f85\u5b9a/\u5ffd\u7565\uff08\u89c4\u8303\u7b2c\u56db\u8282\uff09\u3002
        # \u89c4\u8303\u8bf4\u300c\u7b2c 5 \u6b65\u5fc5\u987b\u4eba\u5de5\u300d\uff0c\u6240\u4ee5\u8fd9\u91cc\u53ea\u51fa\u6e05\u5355\uff0c\u4e0d\u66ff\u5ba2\u6237\u6539\u7a3f\u3002
        if data.get('pipeline'):
            try:
                import reviewers as RV
                send({'type': 'step', 'step': 5, 'name': '\u5ba1\u7a3f\u56e2', 'status': 'running'})
                _team = RV.run_team(body, abs_rel, write=False)
                _cons = RV.extract_consensus(_team.get('reviewers') or [])
                send({'type': 'step', 'step': 5, 'name': '\u5ba1\u7a3f\u56e2', 'status': 'done',
                      'detail': {'verdict': (_team.get('merged') or {}).get('verdict'),
                                 'reviewers': len(_team.get('reviewers') or []),
                                 'must_fix': _cons.get('must_fix') or [],
                                 'pending': _cons.get('pending') or [],
                                 'ignored_count': len(_cons.get('ignored') or []),
                                 'consensus_error': _cons.get('error')}})
            except Exception as e:
                send({'type': 'step', 'step': 5, 'name': '\u5ba1\u7a3f\u56e2', 'status': 'failed',
                      'detail': {'error': '%s: %s' % (type(e).__name__, e)}})

""" + ANCHOR
s = s.replace(ANCHOR, SIDE, 1)

io.open(TMP, "w", encoding="utf-8", newline="").write(s)
os.replace(TMP, P)
print("step5 added")