# -*- coding: utf-8 -*-
"""计费费率。只做费率取值，不含任何展示文案。

优先级：环境变量 > config 下的分档文件 > 默认费率。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "config", "edition.json")

RATES = {"std": 0.05, "self": 0.0, "internal": 0.05}  # 2026-11-17：internal 显式化，避免回落 DEFAULT
DEFAULT = "std"
ENV_KEY = "NOVELAPP_EDITION"


def load():
    name = (os.environ.get(ENV_KEY) or "").strip().lower()
    if name not in RATES:
        try:
            with open(CFG, "r", encoding="utf-8") as f:
                name = (json.load(f).get("edition") or "").strip().lower()
        except Exception:
            name = ""
    key = name if name in RATES else DEFAULT
    return {"edition": key, "fee_rate": RATES[key]}
