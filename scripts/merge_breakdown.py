# -*- coding: utf-8 -*-
"""拆书库去私人化 v2：改写而不是删除

v1 删了 23 行，但还剩 100+ 处「本项目 / 沈修 / 我通关」。

这些句子分三类：
  ① 有价值但带私人引用 → 改写成通用表述
  ② 纯私人记录 → 删掉
  ③ 章节标题「## 迁移到本项目（这个修仙游戏我通关过）的要点」→ 改成「## 迁移要点」
"""
import os
import re
import shutil

SRC = r"D:\OpenClaw\state\workspace\拆书库"
DST = r"D:\NovelApp\assets\拆书库"

# 改写规则：按顺序应用
REWRITES = [
    # v3 补充：修剩余 6 处 + 病句
    (re.compile(r"迁移到迁移时时要结合沈修的「稳健流」人设"), "迁移时要结合稳健流主角的人设"),
    (re.compile(r"已迁移为主角沈修「([^」]+)」的稳健流底色"), r"对应「\1」型主角的稳健流底色"),
    (re.compile(r"已迁移为主角沈修「([^」]+)」的稳健流内核"), r"对应「\1」型主角的稳健流内核"),
    (re.compile(r"本书主角沈修是个人视角"), "主角是个人视角"),
    (re.compile(r"本书以主角沈修为核心"), "本书以主角为核心"),
    (re.compile(r"迁移为迁移时"), "迁移为"),
    (re.compile(r"迁移到迁移时"), "迁移到"),
    (re.compile(r"沈修"), "主角"),
    # 章节标题
    (re.compile(r"##\s*迁移到本项目（这个修仙游戏我通关过）的要点"), "## 迁移要点"),
    (re.compile(r"##\s*迁移到本项目.*?的要点"), "## 迁移要点"),
    # 角色名 + 人设括号 → 通用描述
    (re.compile(r"迁移到本项目沈修（([^）]+)）"), r"迁移到\1型主角时"),
    (re.compile(r"已迁移为本项目沈修（([^）]+)）"), r"对应\1型主角"),
    (re.compile(r"可迁移到本项目沈修（([^）]+)）"), r"可迁移到\1型主角"),
    (re.compile(r"本项目沈修的稳健流内核"), "稳健流主角的核心"),
    (re.compile(r"本项目主角「沈修」"), "稳健流主角"),
    (re.compile(r"本项目沈修"), "稳健流主角"),
    # 「本项目《这个修仙游戏我通关过》的 X」
    (re.compile(r"本项目《这个修仙游戏我通关过》的「([^」]+)」"), r"「\1」类"),
    (re.compile(r"本项目《这个修仙游戏我通关过》的主角"), "稳健流主角"),
    (re.compile(r"本项目《这个修仙游戏我通关过》"), "同类作品"),
    (re.compile(r"本项目主角正是「通关过游戏」的穿越者"), "主角是「通关过游戏」的穿越者"),
    (re.compile(r"本项目是稳健流清冷主角"), "主角是清冷型稳健流"),
    (re.compile(r"本项目主角"), "主角"),
    # 剩下的「本项目」通用化
    (re.compile(r"本项目"), "迁移时"),
    # 「我通关过」
    (re.compile(r"这个修仙游戏我通关过"), "同类作品"),
    (re.compile(r"我通关过"), "常见设定"),
]


def transform(text):
    for pat, repl in REWRITES:
        text = pat.sub(repl, text)
    # 最后清理病句（多轮替换产生的重复词）
    fixes = [
        ("迁移为迁移时", "迁移为"),
        ("迁移到迁移时", "迁移到"),
        ("迁移时时不", "迁移时不"),
        ("迁移为迁移", "迁移为"),
        ("迁移到迁移", "迁移到"),
        ("时要结合主角的人设", "时要结合主角人设"),
        ("迁移时要结合稳健流主角的人设（", "迁移时结合稳健流主角的人设（"),
    ]
    for a, b in fixes:
        text = text.replace(a, b)
    return text


def process_file(src, dst):
    with open(src, "r", encoding="utf-8") as f:
        text = f.read()
    new = transform(text)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(new)
    return text != new


def main():
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    os.makedirs(DST, exist_ok=True)

    n_files = 0
    n_changed = 0

    # 作者文笔
    src_style = os.path.join(SRC, "文笔风格")
    if os.path.isdir(src_style):
        for fn in os.listdir(src_style):
            if not fn.endswith(".md"):
                continue
            if process_file(os.path.join(src_style, fn), os.path.join(DST, "作者文笔", fn)):
                n_changed += 1
            n_files += 1

    # 书籍拆解
    src_books = os.path.join(SRC, "蒸馏库")
    books = 0
    if os.path.isdir(src_books):
        for book in os.listdir(src_books):
            bd = os.path.join(src_books, book)
            if not os.path.isdir(bd):
                continue
            books += 1
            for fn in os.listdir(bd):
                if not fn.endswith(".md"):
                    continue
                if process_file(os.path.join(bd, fn), os.path.join(DST, "书籍拆解", book, fn)):
                    n_changed += 1
                n_files += 1

    # README
    r = os.path.join(src_books, "README.md")
    if os.path.isfile(r):
        process_file(r, os.path.join(DST, "README.md"))
        n_files += 1

    print("文件: %d，改写的: %d，书: %d 本" % (n_files, n_changed, books))
    print("输出: %s" % DST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())