# -*- coding: utf-8 -*-
"""
seeds.py — KOL 种子列表加载辅助模块

统一入口：load_seeds() 从 config/seeds.json 读取并返回 KOL 列表。
供 main.py 和任何需要访问种子列表的模块直接 import，
避免各模块硬编码 seeds.json 路径。
"""

import json
from pathlib import Path
from typing import Any

_SEEDS_PATH = Path(__file__).parent / "seeds.json"


def load_seeds() -> list[dict[str, Any]]:
    """
    从 config/seeds.json 加载并返回 KOL 种子列表。

    Returns:
        KOL dict 列表，每项含 id、name、handle、platforms、sector 等字段。

    Raises:
        FileNotFoundError: seeds.json 不存在。
        json.JSONDecodeError: seeds.json 格式不合法。
    """
    with open(_SEEDS_PATH, encoding="utf-8") as f:
        return json.load(f)
