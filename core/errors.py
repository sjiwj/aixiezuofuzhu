# -*- coding: utf-8 -*-
"""错误普通话化：把异常翻成用户看得懂的一句话。

原则：
  - 界面只显示 human()/report() 返回的中文，不出现 KeyError、TypeError 这类英文异常名；
  - 英文原文 + 堆栈只进 <data_dir>/logs/errors.log，供排障；
  - 映射按「用户下一步能做什么」组织，不按 Python 异常分类学。

用法：
  from errors import human, report
  self._json({'ok': False, 'error': report(e)}, 500)      # 写日志 + 中文
  self._json({'ok': False, 'error': '读不了：' + human(e)}, 500)
"""
import json
import os
import re
import time
import traceback
from urllib.error import HTTPError, URLError

_TXT = 80
_CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]')


def _data_dir():
    d = os.environ.get('NOVELAPP_DATA')
    if d:
        return d
    if os.environ.get('APPDATA'):
        return os.path.join(os.environ['APPDATA'], 'novelapp-desktop', 'data')
    return os.path.join(os.path.expanduser('~'), 'novelapp-desktop')


def _short(s, n=_TXT):
    s = str(s or '').replace('\r', ' ').replace('\n', ' ').strip()
    return s[:n] + ('…' if len(s) > n else '')


def _is_cjk(s):
    return bool(_CJK.search(s or ''))


def _hint(e):
    """异常 -> 一句中文原因。判定顺序有讲究：子类必须排在父类前面。"""
    # JSONDecodeError 是 ValueError 子类，先判
    if isinstance(e, json.JSONDecodeError):
        if (e.doc or '').lstrip()[:1] == '<':
            return '对方返回的是网页而不是数据（可能被登录页或错误页挡了）'
        return '返回内容不是合法 JSON（第 %d 行第 %d 列）' % (e.lineno, e.colno)

    if isinstance(e, KeyError):
        key = e.args[0] if e.args else ''
        return '数据里缺字段「%s」，可能是文件格式和当前版本对不上' % _short(key, 30)

    if isinstance(e, IndexError):
        return '数据条数对不上（取到了不存在的第几条）'

    if isinstance(e, FileNotFoundError):
        name = os.path.basename(getattr(e, 'filename', '') or '') or '目标文件'
        return '文件不存在：%s' % _short(name, 40)

    if isinstance(e, IsADirectoryError):
        return '这里是个目录，不是文件'
    if isinstance(e, NotADirectoryError):
        return '路径中间有一段不是目录'
    if isinstance(e, PermissionError):
        return '没有权限读写（文件可能正被别的程序占用）'
    if isinstance(e, UnicodeDecodeError):
        return '文件不是 UTF-8 编码，读出来会乱码'

    if isinstance(e, ConnectionResetError) or isinstance(e, ConnectionAbortedError):
        return '连接被对方断开（模型服务或网关中途退出）'

    # TimeoutError 是 OSError 子类，必须排在 OSError 前
    if isinstance(e, TimeoutError):
        return '等待超时，对方一直没有回应'

    # HTTPError 是 URLError 子类；URLError 是 OSError 子类
    if isinstance(e, HTTPError):
        code = getattr(e, 'code', None)
        if code in (401, 403):
            return '模型服务拒绝了这个 key（HTTP %s），去设置页换一个' % code
        if code == 429:
            return '模型服务限流了（HTTP 429），等一会儿再试'
        if isinstance(code, int) and code >= 500:
            return '模型服务自己出错了（HTTP %s），不是你这边的问题' % code
        return '模型服务返回 HTTP %s' % code

    if isinstance(e, URLError):
        return '网络不通，检查模型网关是否在跑（默认 http://127.0.0.1:3000）'

    if isinstance(e, OSError):
        err = _short(getattr(e, 'strerror', '') or '', 40)
        if err and _is_cjk(err):
            return '磁盘或系统调用出错：%s' % err
        return '磁盘或系统调用出错（可能磁盘满、路径被占用或不存在）'

    if isinstance(e, MemoryError):
        return '内存不够，关掉别的程序后再试'

    if isinstance(e, AttributeError):
        return '程序内部取错了对象（数据结构和当前版本不匹配）'

    if isinstance(e, ImportError):
        return '缺少运行组件，安装不完整：%s' % _short(e, 60)

    if isinstance(e, ValueError):
        t = _short(e)
        if t and _is_cjk(t):
            return t                      # 自己抛的中文提示，直接用
        return '参数不合法或数据格式不对'

    if isinstance(e, TypeError):
        return '数据类型对不上（内部取错了字段）'

    if isinstance(e, RecursionError):
        return '数据嵌套太深，处理不了'

    if isinstance(e, KeyboardInterrupt):
        return '已取消'

    return '未知错误（已记录，日志里有详细原因）'


# urlopen 相关异常已在顶部从 urllib.error 导入


def human(e, action=''):
    """界面可直接显示的一句话。action 形如 '保存'、'读取章节'；为空时只给原因。"""
    hint = _hint(e)
    act = str(action or '').strip()
    return ('%s失败：%s' % (act, hint)) if act else hint


def trace(e):
    """英文原文 + 堆栈，只给日志看。"""
    try:
        return ''.join(traceback.format_exception(type(e), e, e.__traceback__)).rstrip()
    except Exception:
        return '%s: %s' % (type(e).__name__, e)


def log(e, where=''):
    """把原文与堆栈写进 <data_dir>/logs/errors.log；写不进去就静默（错误路径不能再抛）。"""
    try:
        d = os.path.join(_data_dir(), 'logs')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'errors.log'), 'a', encoding='utf-8') as f:
            f.write('\n=== %s | %s ===\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), where or '-'))
            f.write(trace(e) + '\n')
    except Exception:
        pass
    return e


def report(e, action='', where=''):
    """一次到位：写日志 + 返回中文文案。"""
    log(e, where or action)
    return human(e, action)
