"""板块产出路径：相对仓库根目录的单一真相源。

脚本与测试不要各自拼路径字符串，一律从本模块取。
2026-11-18 目录迁移已完成：AI资讯/ → 资讯/AI/，四类产出统一收进 数据/。
以后再调整板块位置，只改 BOARD_REL 一行即可；
weeks.py / coord.py / feishu_sync.py / trace_view.py / 测试均无需改动。
"""
from __future__ import annotations

import re

# 板块根目录（相对仓库根）：资讯/{板块名}
BOARD_REL = "资讯/AI"

# 榜单数据与运行记录所在目录。
DATA_REL = f"{BOARD_REL}/数据"

# 周报 / 月报 / 季报同样收在 数据/ 下。
OUTPUT_REL = DATA_REL


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
