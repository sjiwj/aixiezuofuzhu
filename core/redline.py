# -*- coding: utf-8 -*-
"""第 3 保险：红线前置判定（模板 core/redline.py 的小说工作台版）。

模板原意是命令级 hook：触达密钥 / 危险动作就停手，只判不执行。
这里是它在「写盘动作」上的落地——Web 写接口不是 shell，所以红线落在
"哪些路径不能改、哪些状态不能覆盖"上。

三条：
  R1 隐藏路径      任一路径段以 . 开头（.stages.json / .layers/ / .trash/ / .history/）
                   → 一律拒。这些是内部状态，绕过它等于绕过状态机与回收站。
  R2 定稿被覆盖    stage=done 且 mode 是覆盖，且没带 force → 拒
  R3 定稿被删除    stage=done 且没带 force → 拒（有 .trash，但定稿不该一键删）

用法（server.py 在 safe_rel 之后、动手之前调）：
  r = redline.check_write(norm, force=force, stage=stage)
  if not r['ok']:
      return {'ok': False, 'error': r['blocked'][0]['reason'], 'redline': r}

设计约束：
- 只判不执行：本模块不写盘、不删盘、不改状态。
- 拒绝必须带 force 的逃生口（R2/R3），否则用户会遇到"改不动自己的稿"。
- R1 没有逃生口：内部状态文件永远不该从 Web 写接口进。
"""
import re

HIDDEN_TOP = ('.stages.json', '.layers', '.trash', '.history', '.cache', '.session',
              '.snapshots', '.backup')


def _segments(norm):
    return [s for s in str(norm or '').replace('\\', '/').split('/') if s]


def is_hidden_path(norm):
    """任一段以 . 开头即视为内部路径。"""
    return any(s.startswith('.') for s in _segments(norm))


def check_write(norm, force=False, stage='', action='write'):
    """action: write / delete。返回 {'ok','blocked':[{code,reason,need_force?}]}。"""
    blocked = []
    segs = _segments(norm)

    hidden = [s for s in segs if s.startswith('.')]
    if hidden:
        blocked.append({
            'code': 'redline.hidden_path',
            'reason': '不能通过写接口改内部状态：%s（这类文件由程序自己维护）' % hidden[0],
        })
        return {'ok': False, 'blocked': blocked, 'action': action}

    if stage == 'done' and not force:
        if action == 'delete':
            blocked.append({
                'code': 'redline.final_chapter_delete',
                'reason': '该章已定稿，删除要先改回 draft 或带 force=true',
                'need_force': True,
            })
        else:
            blocked.append({
                'code': 'redline.final_chapter_overwrite',
                'reason': '该章已定稿，覆盖要带 force=true（会先写版本历史）',
                'need_force': True,
            })

    return {'ok': not blocked, 'blocked': blocked, 'action': action}


def check_command(argv, context=None):
    """命令级红线（模板原版语义）：给将来的 hook 用。

    只判不执行。默认危险清单覆盖影响发版/删库的操作；
    context={'publish_flow': True} 时对 git push 类放行（发版是正常流程）。
    """
    ctx = context or {}
    joined = ' '.join(argv or [])
    hits = []
    if re.search(r'git\s+push', joined):
        if not ctx.get('publish_flow'):
            hits.append({'code': 'redline.git_push', 'reason': 'git push 需要显式 context={"publish_flow": True}'})
    if re.search(r'\brm\s+-rf\b|\brmdir\s+/s\b|Remove-Item.*-Recurse.*-Force', joined, re.I):
        hits.append({'code': 'redline.destructive_rm', 'reason': '递归强删'})
    if re.search(r'DROP\s+TABLE|DELETE\s+FROM\s+\w+\s*(;|$)', joined, re.I):
        hits.append({'code': 'redline.sql_destructive', 'reason': '破坏性 SQL'})
    return {'ok': not hits, 'blocked': hits}
