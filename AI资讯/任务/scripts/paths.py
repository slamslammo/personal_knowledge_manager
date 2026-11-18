"""板块产出路径：相对仓库根目录的单一真相源。

脚本与测试不要各自拼 "AI资讯/..." 字符串，一律从本模块取。
2026-11 目录迁移（AI资讯/ → 资讯/AI/）时只改本文件的两行常量，
weeks.py / coord.py / feishu_sync.py / trace_view.py / 测试均无需改动：

    BOARD_REL  = "资讯/AI"
    OUTPUT_REL = DATA_REL

旧结构把周报、月报、季报直接放在板块根下，榜单数据与运行记录放在
板块根的「数据/」下；迁移后四类产出统一收进「资讯/AI/数据/」。
OUTPUT_REL 专门承载这个差异，使迁移前 behaviour 保持完全一致。
"""
from __future__ import annotations

import re

# 板块根目录（相对仓库根）。旧结构为一级目录 AI资讯；迁移后为 资讯/AI。
BOARD_REL = "AI资讯"

# 榜单数据与运行记录所在目录。
DATA_REL = f"{BOARD_REL}/数据"

# 周报 / 月报 / 季报的父目录。旧结构等于板块根；迁移后改为 DATA_REL。
OUTPUT_REL = BOARD_REL


def report(iso_year: int | str, week: str) -> str:
    return f"{OUTPUT_REL}/周报/{iso_year}/{week}.md"


def data(week: str) -> str:
    return f"{DATA_REL}/github-weekly/{week}.json"


def state(week: str) -> str:
    return f"{DATA_REL}/运行记录/{week}.json"


def monthly(year: int, month: int) -> str:
    return f"{OUTPUT_REL}/月报/{year}/{year}-{month:02d}.md"


def quarterly(year: int, quarter: int) -> str:
    return f"{OUTPUT_REL}/季报/{year}/{year}-Q{quarter}.md"


# coord.py 的写入白名单正则；迁移时随 OUTPUT_REL 自动更新。
MONTHLY_RE = re.escape(OUTPUT_REL) + r"/月报/\d{4}/\d{4}-\d{2}\.md$"
QUARTERLY_RE = re.escape(OUTPUT_REL) + r"/季报/\d{4}/\d{4}-Q[1-4]\.md$"
