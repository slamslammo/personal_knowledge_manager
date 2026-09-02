#!/usr/bin/env python
"""Generate deterministic fixtures and P2 notebooks for lessons 31–36."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import nbformat as nbf
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"
LABS = ROOT / "labs"
FIXTURES = ROOT / "data" / "fixtures"
OUTPUTS = ROOT / "outputs"
RANDOM_SEED = 365
COURSE_ROOT = Path(
    "/Users/mojiawen/Documents/"
    "pam-video-captures/365-days-quant-finance"
)

for directory in [NOTEBOOKS, LABS, FIXTURES, OUTPUTS]:
    directory.mkdir(parents=True, exist_ok=True)


def md(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


def source_note(number: int, title: str, package: str) -> str:
    package_path = COURSE_ROOT / package / "index.html"
    return f"""
# 第 {number} 课｜{title}

本 Notebook 对应「365 天量化金融」第 {number} 课。课程代码主线来自本地视频、课件截图和 Whisper 口播整理；在此基础上补充量化数据语义、断言、性能验证和方法边界。

- 图文口播：`{package_path}`
- 环境：`pkm-quant`
- 数据：固定随机种子生成的离线模拟行情（**非真实股票数据**）
- 状态：可运行学习稿；不代表策略收益承诺

> **数据声明**：本 Notebook 的证券名称、价格和成交量均为教学模拟数据。它用于稳定复现计算方法，不能用于评价真实证券、市场规律或策略收益。
"""


COMMON_SETUP = r"""
from pathlib import Path
import json
import os
import platform
import sys
import tempfile
import timeit

# Matplotlib 首次运行需要写字体缓存；放到可写临时目录，避免污染用户目录。
MPL_CACHE_DIR = Path(tempfile.gettempdir()) / "pkm-quant-matplotlib"
MPL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
import seaborn as sns

# 从本机字体中选择支持中文的字体，避免标题显示成方框。
preferred_chinese_fonts = [
    "PingFang SC",
    "Arial Unicode MS",
    "Hiragino Sans GB",
    "Heiti SC",
]
available_font_names = {font.name for font in font_manager.fontManager.ttflist}
chinese_font = next(
    (name for name in preferred_chinese_fonts if name in available_font_names),
    "DejaVu Sans",
)
plt.rcParams["font.sans-serif"] = [chinese_font, "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

def find_project_root():
    cwd = Path.cwd().resolve()
    candidates = [
        cwd,
        cwd / "实验" / "p2-python-toolchain",
        cwd / "p2-python-toolchain",
        *cwd.parents,
    ]
    for candidate in candidates:
        if (candidate / "课程辅助设计.md").exists():
            return candidate
    raise FileNotFoundError("请从 p2-python-toolchain 或量化交易项目目录启动 JupyterLab")

PROJECT_ROOT = find_project_root()
DATA_DIR = PROJECT_ROOT / "data" / "fixtures"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)
RANDOM_SEED = 365

print("Python:", sys.version.split()[0])
print("解释器:", sys.executable)
print("项目:", PROJECT_ROOT)
print("绘图字体:", chinese_font)
"""


def notebook(cells):
    nb = nbf.v4.new_notebook(cells=cells)
    nb.metadata = {
        "kernelspec": {
            "display_name": "Python (pkm-quant)",
            "language": "python",
            "name": "pkm-quant",
        },
        "language_info": {"name": "python", "version": "3.11"},
        "p2_course_assistance": {
            "design": "课程辅助设计.md",
            "default_offline": True,
            "review_status": "executable-learning-draft",
        },
    }
    return nb


def write_notebook(path: Path, cells):
    nbf.write(notebook(cells), path)
    print(f"wrote {path.relative_to(ROOT)}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_daily_fixture() -> Path:
    rng = np.random.default_rng(RANDOM_SEED)
    dates = pd.bdate_range("2023-01-03", periods=756)
    symbols = ["BANK_A", "INSURE_A", "EV_A", "POWER_A", "ENERGY_A", "TECH_A"]
    sectors = {
        "BANK_A": "金融",
        "INSURE_A": "金融",
        "EV_A": "新能源",
        "POWER_A": "公用事业",
        "ENERGY_A": "能源",
        "TECH_A": "科技",
    }
    market = rng.normal(0.00025, 0.0090, len(dates))
    factors = {
        "金融": rng.normal(0.00005, 0.0040, len(dates)),
        "新能源": rng.normal(0.00008, 0.0070, len(dates)),
        "公用事业": rng.normal(0.00003, 0.0025, len(dates)),
        "能源": rng.normal(0.00004, 0.0050, len(dates)),
        "科技": rng.normal(0.00010, 0.0065, len(dates)),
    }
    betas = dict(zip(symbols, [0.85, 0.95, 1.25, 0.45, 0.70, 1.15]))
    start_prices = dict(zip(symbols, [12.0, 42.0, 28.0, 8.0, 6.0, 36.0]))

    rows = []
    for symbol in symbols:
        sector = sectors[symbol]
        idiosyncratic = rng.normal(0, 0.0075, len(dates))
        returns = (
            betas[symbol] * market
            + factors[sector]
            + idiosyncratic
        )
        close = start_prices[symbol] * np.exp(np.cumsum(returns))
        previous_close = np.r_[close[0], close[:-1]]
        gap = rng.normal(0, 0.0020, len(dates))
        open_ = previous_close * (1 + gap)
        spread = np.abs(rng.normal(0.006, 0.002, len(dates)))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = rng.lognormal(15.1, 0.35, len(dates)).astype("int64")
        for idx, date in enumerate(dates):
            rows.append(
                {
                    "date": date.date().isoformat(),
                    "symbol": symbol,
                    "sector": sector,
                    "open": round(float(open_[idx]), 4),
                    "high": round(float(high[idx]), 4),
                    "low": round(float(low[idx]), 4),
                    "close": round(float(close[idx]), 4),
                    "adj_close": round(float(close[idx]), 4),
                    "volume": int(volume[idx]),
                }
            )
    frame = pd.DataFrame(rows)
    path = FIXTURES / "daily_prices.csv"
    frame.to_csv(path, index=False)
    return path


def build_intraday_fixture() -> Path:
    rng = np.random.default_rng(RANDOM_SEED + 35)
    dates = pd.bdate_range("2025-03-03", periods=10)
    morning = pd.date_range("09:35", "11:30", freq="5min").time
    afternoon = pd.date_range("13:05", "15:00", freq="5min").time
    rows = []
    last_close = 100.0
    for date in dates:
        for clock in [*morning, *afternoon]:
            timestamp = pd.Timestamp.combine(date.date(), clock).tz_localize(
                "Asia/Shanghai"
            )
            open_ = last_close
            close = open_ * np.exp(rng.normal(0.00005, 0.0015))
            spread = abs(rng.normal(0.0009, 0.0003))
            high = max(open_, close) * (1 + spread)
            low = min(open_, close) * (1 - spread)
            volume = int(rng.lognormal(10.4, 0.45))
            typical = (high + low + close) / 3
            amount = typical * volume
            rows.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "symbol": "SYNTH_A",
                    "open": round(open_, 4),
                    "high": round(high, 4),
                    "low": round(low, 4),
                    "close": round(close, 4),
                    "volume": volume,
                    "amount": round(amount, 2),
                }
            )
            last_close = close
    frame = pd.DataFrame(rows)
    path = FIXTURES / "intraday_5m.csv"
    frame.to_csv(path, index=False)
    return path


def build_metadata(files: list[Path]):
    metadata = {
        "schema": 1,
        "purpose": "deterministic synthetic fixtures for P2 lessons 31-36",
        "seed": RANDOM_SEED,
        "market_structure": {
            "daily": "six fictional assets with market, sector and idiosyncratic factors",
            "intraday": "fictional A-share-like 5-minute bars, Asia/Shanghai, 48 bars per day",
        },
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in files
        },
        "boundary": "Synthetic educational data; not real security history.",
    }
    (FIXTURES / "fixture_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_lesson_31():
    cells = [
        md(
            source_note(
                31,
                "环境与可复现研究",
                "31_youtube-QVHRIvr0l18",
            )
        ),
        md(
            """
## 本节量化问题

课程强调虚拟环境、Jupyter/编辑器双轨制和标准项目目录。本项目已经在 Datawhale 学习阶段建立 `pkm-quant`，因此这里不重复安装，而是验证：

1. Notebook 是否真的使用统一内核；
2. 当前内核实际安装了哪些直接依赖；
3. 研究结果能否追溯到代码、参数、数据快照和运行环境。

### 输入与输出

- 输入：当前 Python 解释器、已安装库、`environment.yml` 和离线行情文件；
- 输出：依赖版本表、环境核验结果、数据文件指纹和研究清单 JSON；
- 验收：内核必须是 `pkm-quant`，课程直接依赖不能缺失，研究清单保存后能原样回读。
"""
        ),
        md(
            """
## 本节输入是什么？

本节使用三类确定性输入：

1. 手工给出的 3 个价格 `[100.0, 102.0, 101.0]`，只用于演示 pandas 与 NumPy 的最小数据流；
2. `daily_prices.csv` 和 `intraday_5m.csv` 两份**模拟行情文件**，只用于演示数据快照追踪；
3. 当前解释器、已安装包和 `environment.yml`，用于核对运行环境。

模拟行情不对应任何真实证券。本节也不评价策略收益，只回答“这次研究由什么环境、代码和输入文件生成”。

下面的公共准备单元只建立项目路径、绘图字体和随机种子等运行上下文。可核对输出应包括 Python 版本、解释器路径、项目目录和中文字体。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 后续课程会用到哪些库？

先建立“库 → 量化任务”的对应关系，不要求一次背完 API。后续课程会在真实场景中逐步展开。

| 库 | 基本对象/能力 | 量化中的主要用途 |
|---|---|---|
| **NumPy** | `ndarray`、广播、矩阵运算 | 收益矩阵、组合加权、向量化计算 |
| **pandas** | `Series`、`DataFrame`、时间索引 | 读取行情、标签对齐、重采样、滚动统计 |
| **SciPy** | 优化、统计分布、数值求解 | 组合优化、参数估计、显著性检验 |
| **Matplotlib / seaborn** | 静态图表和统计图 | K 线以外的收益、回撤、相关性可视化 |
| **scikit-learn** | 特征处理、模型、交叉验证 | 因子/预测模型与样本外验证 |
| **statsmodels** | 回归、时间序列、统计推断 | OLS、协整、残差和置信区间 |
| **yfinance / AkShare** | 数据接口 | 分别接入海外和国内市场数据；本批先用离线数据 |

学习重点不是孤立记忆库名，而是知道：数据先由 pandas 按日期和证券标签对齐，再在必要处转换为 NumPy 做批量计算，最后用统计库和图表库验证结果。

## 最小数据流：先展示输入价格

先建立一张只有 3 行的带标签价格表。此时还没有计算收益，输出中的一行只代表一个观察日的收盘价。
"""
        ),
        code(
            r"""
# 输入是 3 个确定价格；索引和列名保留观察语义。
demo_prices = pd.DataFrame(
    {"close": [100.0, 102.0, 101.0]},  # [100.0, 102.0, 101.0]
    index=pd.Index(["第 1 日", "第 2 日", "第 3 日"], name="观察日"),
)

assert demo_prices.shape == (3, 1)
demo_prices
"""
        ),
        md(
            """
## 从 pandas 收益表转成 NumPy 数组

下面的数据流会在后续课程反复出现：

1. `pd.DataFrame` 保存带列名的价格表；
2. `pct_change(fill_method=None)` 按列计算简单收益率 `本期价格 / 上期价格 - 1`；
3. `dropna()` 去掉没有前值的首行；
4. `to_numpy(dtype=np.float64)` 取出数值，交给 NumPy 计算；
5. `np.mean` 得到这两个有效观测的样本算术平均日收益。

`to_numpy()` 后不再保留“观察日”和“close”标签，因此应先由 pandas 完成对齐，并在输出时恢复或明确记录标签。这里的样本只有两期有效收益，均值只用于核对 API，不是未来预期收益。
"""
        ),
        code(
            r"""
# 先保留带标签收益表，再转换为包含两个有效收益的 NumPy 数组。
demo_returns = demo_prices.copy()
demo_returns["simple_return"] = demo_returns["close"].pct_change(
    fill_method=None
)
return_array = (
    demo_returns["simple_return"]
    .dropna()
    .to_numpy(dtype=np.float64)
)
sample_mean_return = float(np.mean(return_array))

expected_returns = np.array([0.02, 101.0 / 102.0 - 1])
np.testing.assert_allclose(return_array, expected_returns)
assert return_array.shape == (2,)
assert np.isclose(sample_mean_return, 0.0050980392156863)

display(demo_returns.round(6))
pd.DataFrame(
    {
        "核对结果": [
            str(return_array.shape),
            f"{return_array[0]:.4%}",
            f"{return_array[1]:.4%}",
            f"{sample_mean_return:.4%}",
        ]
    },
    index=[
        "有效收益数组 shape",
        "第 2 日简单收益",
        "第 3 日简单收益",
        "两期样本算术平均日收益",
    ],
)
"""
        ),
        md(
            """
## 核对实际安装的依赖版本

`importlib.metadata.version(distribution)` 查询当前解释器环境中已安装的**分发包元数据**。例如 `scikit-learn` 是分发包名，Python 中通常使用 `import sklearn`。

捕获 `PackageNotFoundError` 后标记为 `MISSING`。环境文件表达“计划安装什么”，版本表表达“当前环境登记了什么版本”；版本存在不等于所有 API、原生依赖或网络数据接口都已成功运行，因此后续课程仍要执行实际任务验收。
"""
        ),
        code(
            r"""
# 查询课程直接依赖的安装版本，并显式标记是否存在。
from importlib import metadata

packages = [
    "numpy", "pandas", "scipy", "matplotlib", "seaborn",
    "scikit-learn", "statsmodels", "jupyterlab", "ipykernel",
    "yfinance", "akshare",
]
versions = {}
for package in packages:
    try:
        versions[package] = metadata.version(package)
    except metadata.PackageNotFoundError:
        versions[package] = "MISSING"

environment_table = pd.DataFrame(
    {
        "version": pd.Series(versions),
        "installed": pd.Series(versions).ne("MISSING"),
    }
)
environment_table.index.name = "distribution"
missing_packages = environment_table.index[
    ~environment_table["installed"]
].tolist()

assert not missing_packages, f"缺少课程依赖：{missing_packages}"
environment_table
"""
        ),
        md(
            """
## 核对当前 Notebook 的实际解释器

`sys.executable` 是当前 Notebook 实际调用的 Python 路径，不是终端中另一个 Python 的路径。这里从解释器所在目录读取环境名，并用带标签表格同时展示实际值和期望值。

断言失败会立即终止执行，避免在错误内核中继续产生看似正常的研究结果。
"""
        ),
        code(
            r"""
# 核对 Notebook 内核实际使用的解释器，而不是只看界面显示名称。
current_env_name = Path(sys.executable).parent.parent.name
kernel_check = pd.DataFrame(
    {
        "实际值": [
            sys.version.split()[0],
            sys.executable,
            current_env_name,
            len(missing_packages),
        ],
        "期望值": [
            "3.11.x",
            "pkm-quant 环境中的 python",
            "pkm-quant",
            0,
        ],
    },
    index=[
        "Python 版本",
        "解释器路径",
        "Conda 环境名",
        "缺失直接依赖数量",
    ],
)

assert current_env_name == "pkm-quant", (
    "当前 Notebook 没有使用 pkm-quant 解释器"
)
kernel_check
"""
        ),
        md(
            """
## 核对 `environment.yml` 的环境声明

`environment.yml` 是声明直接依赖的环境规格文件；它适合回答“项目计划安装什么”，但没有把每个传递依赖精确锁到唯一构建，因此不能替代锁文件或容器镜像。

下面只提取可核对的关键信息，不截断打印整份 YAML。
"""
        ),
        code(
            r"""
# 读取环境规格，并提取环境名与关键直接依赖核对。
environment_file = PROJECT_ROOT.parents[1] / "environment.yml"
environment_text = environment_file.read_text(encoding="utf-8")

declared_env_name = None
for line in environment_text.splitlines():
    if line.startswith("name:"):
        declared_env_name = line.split(":", 1)[1].strip()
        break

environment_declaration = pd.DataFrame(
    {
        "实际值": [
            str(environment_file),
            declared_env_name,
            "  - numpy" in environment_text,
            "  - pandas" in environment_text,
            len(environment_text.splitlines()),
        ]
    },
    index=[
        "环境文件",
        "声明环境名",
        "声明 NumPy",
        "声明 pandas",
        "文件行数",
    ],
)

assert declared_env_name == "pkm-quant"
assert "  - numpy" in environment_text
assert "  - pandas" in environment_text
environment_declaration
"""
        ),
        md(
            """
## 研究清单：给实验建立可追溯身份

下面的代码**不负责选股或计算收益**，而是生成一张研究清单（research manifest）。

一份回测结果并不只由代码决定：

> 回测结果 = 代码 × 参数 × 数据快照 × 运行环境

同一段代码如果换了行情文件、随机种子或库版本，可能产生不同结果。为了以后回答“这份结果由什么生成”，本节清单记录：

| 清单字段 | 记录什么 | 量化研究中的用途 |
|---|---|---|
| `python` / `executable` | Python 版本和实际解释器 | 确认没有误用其他 Conda 环境 |
| `packages` | NumPy、pandas 等分发包版本 | 排查 API 或计算行为变化 |
| `random_seed` | 本项目使用的确定性随机种子 | 复现模拟数据与抽样 |
| `code` | 当前 Notebook 生成脚本的 SHA-256 摘要 | 判断生成实现的文件字节是否变化 |
| `data` | 每个输入 CSV 的 SHA-256 摘要 | 判断输入文件字节是否变化 |

### 第一步：先展示将要追踪的输入文件

研究清单不能只出现一串哈希值。先查看每个 CSV 的行数、列数、时间字段、首尾时间和文件大小，确认“本次究竟追踪了什么输入”。
"""
        ),
        code(
            r"""
# 先读取两份小型教学 fixture，建立带标签的输入文件清单。
fixture_files = sorted(DATA_DIR.glob("*.csv"))
assert fixture_files, "没有找到待追踪的 CSV 文件"
inventory_rows = []
schema_rows = []

for path in fixture_files:
    frame = pd.read_csv(path)
    if "date" in frame.columns:
        time_field = "date"
    elif "timestamp" in frame.columns:
        time_field = "timestamp"
    else:
        time_field = None

    inventory_rows.append(
        {
            "file": path.name,
            "rows": len(frame),
            "columns": frame.shape[1],
            "time_field": time_field,
            "first_time": (
                frame[time_field].iloc[0] if time_field else "N/A"
            ),
            "last_time": (
                frame[time_field].iloc[-1] if time_field else "N/A"
            ),
            "bytes": path.stat().st_size,
        }
    )
    schema_rows.append(
        {
            "file": path.name,
            "fields": ", ".join(frame.columns),
        }
    )

file_inventory = pd.DataFrame(inventory_rows).set_index("file")
schema_table = pd.DataFrame(schema_rows).set_index("file")
assert not file_inventory.empty
display(file_inventory)
schema_table
"""
        ),
        md(
            """
### 第二步：计算并展示 SHA-256 摘要

`hashlib.sha256()` 创建摘要计算器；文件以二进制模式分块读取，每次读取 `1 MiB`，因此大文件也不必一次载入内存。表格只展示摘要前 12 位便于阅读，完整 64 位摘要仍保存在清单中。

SHA-256 比较的是**文件字节**：同一逻辑表若改变列顺序、换行符或保存格式，摘要也会变化。摘要可以高概率识别内容变化，但不能证明行情来源可信、复权正确或不存在未来数据。
"""
        ),
        code(
            r"""
import hashlib

# 为每个输入 CSV 分块计算 SHA-256 内容摘要。
def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)  # 每次读取 1 MiB
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()

data_fingerprints = {}
for path in fixture_files:
    data_fingerprints[path.name] = file_sha256(path)

# 表格只展示短前缀；data_fingerprints 保留完整 64 位摘要。
fingerprint_table = pd.DataFrame(
    {
        "file": [path.name for path in fixture_files],
        "bytes": [path.stat().st_size for path in fixture_files],
        "sha256_prefix": [
            data_fingerprints[path.name][:12] for path in fixture_files
        ],
    }
).set_index("file")

assert all(len(value) == 64 for value in data_fingerprints.values())
fingerprint_table
"""
        ),
        md(
            """
### 第三步：构造并展示研究清单

研究清单是普通 Python 字典，集中记录解释器、平台、随机种子、依赖版本、当前生成脚本和完整数据摘要。

代码摘要的键使用相对路径 `tools/build_first_batch.py`，避免只保存同名文件名而无法判断它位于项目何处。这个摘要覆盖当前生成脚本文件，不自动覆盖手工修改的 Notebook、其他仓库代码或外部服务状态。
"""
        ),
        code(
            r"""
# 将环境、参数、代码快照和数据快照组成研究清单。
generator_path = PROJECT_ROOT / "tools" / "build_first_batch.py"
generator_key = generator_path.relative_to(PROJECT_ROOT).as_posix()
generator_fingerprint = file_sha256(generator_path)

manifest = {
    "python": sys.version.split()[0],
    "executable": sys.executable,
    "platform": platform.platform(),
    "random_seed": RANDOM_SEED,
    "packages": versions,
    "code": {generator_key: generator_fingerprint},
    "data": data_fingerprints,
}

manifest_summary = pd.DataFrame(
    {
        "值": [
            manifest["python"],
            current_env_name,
            manifest["random_seed"],
            len(manifest["packages"]),
            generator_key,
            generator_fingerprint[:12],
            len(manifest["data"]),
        ]
    },
    index=[
        "Python",
        "环境",
        "随机种子",
        "分发包数量",
        "代码文件",
        "代码 SHA-256 前缀",
        "数据文件数量",
    ],
)
manifest_summary
"""
        ),
        md(
            """
### 第四步：保存、回读并核对 JSON

`json.dumps(..., ensure_ascii=False, indent=2)` 生成可读的 UTF-8 JSON；`Path.write_text` 保存，`json.loads` 回读。写完立即回读并断言关键字段，是最小的交付校验。
"""
        ),
        code(
            r"""
# 保存研究清单，再回读验证关键字段。
manifest_path = OUTPUT_DIR / "31_research_manifest.json"
manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
manifest_reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
assert manifest_reloaded["random_seed"] == RANDOM_SEED
assert manifest_reloaded["code"] == manifest["code"]
assert manifest_reloaded["data"] == data_fingerprints
assert manifest_reloaded == manifest

pd.DataFrame(
    {
        "核对结果": [
            manifest_path.exists(),
            manifest_reloaded == manifest,
            len(next(iter(manifest_reloaded["code"].values()))),
            len(manifest_reloaded["data"]),
            str(manifest_path),
        ]
    },
    index=[
        "JSON 文件存在",
        "回读内容与内存对象一致",
        "代码摘要字符数",
        "数据文件数量",
        "输出路径",
    ],
)
"""
        ),
        md(
            """
## 可复用结论

重点不是背 `hashlib` 的写法，而是建立四个研究习惯：

1. 计算前先展示输入，明确文件、shape、时间范围和字段列表；
2. 结果同时记录解释器、直接依赖、随机种子、代码文件和数据文件；
3. 文件摘要变化时，前后两次结果不能视为完全相同的实验；
4. 可追溯性只回答“由什么生成”，正确性仍需数据校验、断言和样本外检验。
"""
        ),
        md(
            """
## 方法边界

- 镜像源只影响下载位置，不保证代码兼容。
- `environment.yml` 适合声明直接依赖；生产复现还需锁文件或容器。
- 固定随机种子只控制显式使用它的随机过程；并行计算、硬件和外部接口仍可能带来差异。
- SHA-256 不能证明数据真实或未被恶意替换；可信来源、签名和业务校验仍需单独记录。
- 当前 `code` 字段只追踪生成脚本，不代表项目全部源码、Notebook 手工修改和 Git 状态。
- Notebook 用于探索，重复逻辑应进入 `src/` 并由测试保护。
- 本节验收是“环境可追溯”，不是“重新安装一次 Anaconda”。
"""
        ),
        md(
            """
## 练习

1. 把最小价格例子的第 3 日价格从 `101.0` 改为 `103.0`，先手算第 3 日收益，再核对 NumPy 输出和样本均值。
2. 复制一份教学 CSV 到临时目录，只改变一个字符，比较修改前后的 SHA-256；不要修改正式 fixture。
3. 假设数据摘要不变、代码摘要变化，写出可以下结论和不能下结论的内容。
4. 查看 `environment.yml`，解释为什么“环境名相同”仍不足以证明两台机器的所有传递依赖完全一致。
"""
        ),
    ]
    write_notebook(NOTEBOOKS / "31_环境与可复现研究.ipynb", cells)


def build_lesson_32():
    cells = [
        md(
            source_note(
                32,
                "NumPy 广播与收益矩阵",
                "32_youtube-309_C1gQHX8",
            )
        ),
        md(
            """
## 本节量化问题

课程用价格数组和收益计算说明 ndarray、广播、矢量化、视图与拷贝。这里把示例扩展为“日期 × 股票”的价格与收益矩阵，重点覆盖日收益、等权横截面均值、超额收益、z-score、axis、性能和内存关系。
"""
        ),
        md(
            """
## 本节数据是什么？

这里读取的 `daily_prices.csv` 是**模拟行情，不是真实股票历史数据**：

- 6 只虚构股票：金融、新能源、公用事业、能源和科技行业；
- 756 个工作日，使用固定随机种子 `365`，每次生成结果一致；
- 收益由“市场共同波动 + 行业波动 + 个股随机波动”组合而成，因此保留了一些适合教学的相关性结构；
- 股票名称、OHLCV、价格路径和收益都不对应任何真实证券。

本节目标是验证 NumPy 的 shape、axis、广播和向量化是否正确。它不能用于评价真实市场、选择股票或证明策略有效；真实行情接口和数据快照将在数据获取课程中单独接入。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 先看原始行情表：一行代表什么？

`daily_prices.csv` 是“长表”（long format）：一行代表某个交易日、某只股票的一组行情。除了价格，还保留 `open/high/low/volume/sector` 等字段。
先读入并查看几行，确认我们还没有把数据变成矩阵。
"""
        ),
        code(
            r'''
# 读取原始长表，并把 date 解析为日期类型，先确认字段和数据形状。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
print("原始表形状：", daily.shape)
print("原始列：", daily.columns.tolist())
daily.head()
'''
        ),
        md(
            """
## 用 `pivot` 把长表变成“日期 × 股票”的价格矩阵

这三行分别完成不同工作：

| 代码 | 含义 |
|---|---|
| `index="date"` | 把交易日放到行索引；一行对应一天 |
| `columns="symbol"` | 把股票代码展开成列；一列对应一只股票 |
| `values="adj_close"` | **只选择复权收盘价字段**，不是选择某一只股票 |
| `sort_index()` | 按日期从早到晚排序 |
| `to_numpy()` | 取出矩阵中的数值，丢掉日期和股票标签，交给 NumPy 做高速计算 |

因此，`close` 是带有日期和股票标签的 Pandas 表；`prices` 是包含**全部 6 只股票复权收盘价**的 NumPy 数组，不是单独一列价格。

`pivot` 不做求平均等聚合，要求每个“日期 × 股票”组合只有一行；如果原始数据有重复记录，应先清洗或明确使用 `pivot_table` 的聚合规则。
"""
        ),
        code(
            r"""
# 将长表重排为“日期 × 股票”的复权收盘价表，再转成 NumPy 数值矩阵。
close = daily.pivot(
    index="date",
    columns="symbol",
    values="adj_close",
).sort_index()

prices = close.to_numpy(dtype=np.float64)

print("close.shape =", close.shape, "含义：日期 × 股票")
print("prices.dtype =", prices.dtype)
assert close.index.is_unique and close.columns.is_unique
assert prices.shape == (close.shape[0], close.shape[1])
close.head()
"""
        ),
        md(
            """
## 课程示例 1：整排计算日收益

这里的公式是“今天价格 ÷ 昨天价格 − 1”。代码拆成四步书写，以便直接观察两个切片如何一一对应；运算顺序仍然是先做除法，再减去 `1`。

- `prices[1:]`：从第 2 个交易日开始，到最后一天；
- `prices[:-1]`：从第 1 天开始，到倒数第 2 天；
- 两个切片形状相同，NumPy 逐元素相除；
- `- 1` 把“价格比值”转换成“收益率”。例如 `105 / 100 - 1 = 0.05`，即 5%。

所以结果比原始价格少一行：第一个交易日没有前一天价格，无法计算日收益。
"""
        ),
        code(
            r"""
# 用相邻两天的价格计算日收益；拆开写便于观察切片、除法和减 1 的含义。
today_prices = prices[1:]
previous_prices = prices[:-1]
price_ratio = today_prices / previous_prices
returns_np = price_ratio - 1

assert returns_np.shape == (len(close) - 1, close.shape[1])
returns_table = pd.DataFrame(
    returns_np,
    index=close.index[1:],
    columns=close.columns,
)
returns_table.head()
"""
        ),
        md(
            """
### 用 pandas 独立校验 NumPy 结果

`close.pct_change(fill_method=None)` 按每只股票列计算相邻两行的百分比变化。第一行没有前值，因此得到 `NaN`；`.iloc[1:]` 去掉这一行。`fill_method=None` 明确要求 pandas 不先用旧价格填补缺失值。

`np.testing.assert_allclose` 比较两个浮点数组是否在容许误差内一致；验证成功时没有输出，所以最后显式打印校验结果。
"""
        ),
        code(
            r"""
# 用带标签的 pandas 结果校验 NumPy 手工公式。
returns_pd = close.pct_change(fill_method=None).iloc[1:]
np.testing.assert_allclose(
    returns_np,
    returns_pd.to_numpy(),
    rtol=1e-12,
)
print("校验通过：NumPy 与 pandas 的日收益结果一致。")
"""
        ),
        md(
            """
## 课程示例 2：广播计算超额收益和横截面标准化

这里没有使用外部市场指数，而是把样本中 6 只股票每天的**等权横截面均值**当作教学代理。它每天只有一个值，个股收益每天有多个值。

`mean(axis=1)` 横向计算每一天的股票均值；`keepdims=True` 不需要额外 `reshape`，直接把结果保留为 `(T, 1)`，使它能沿股票维度广播。`std(..., ddof=0)` 在每天的 6 只样本股票上计算总体标准差，本例只用于演示横截面标准化。
"""
        ),
        code(
            r"""
# 复用同一个横截面均值，计算超额收益和每日横截面 z-score。
cross_mean = returns_np.mean(axis=1, keepdims=True)
cross_std = returns_np.std(axis=1, ddof=0, keepdims=True)
assert (cross_std > 0).all(), "存在横截面标准差为 0 的交易日，无法计算 z-score"

excess_return = returns_np - cross_mean
zscore = (returns_np - cross_mean) / cross_std

assert cross_mean.shape == (returns_np.shape[0], 1)
assert cross_std.shape == (returns_np.shape[0], 1)
np.testing.assert_allclose(excess_return.mean(axis=1), 0, atol=1e-15)
np.testing.assert_allclose(zscore.mean(axis=1), 0, atol=1e-12)
print(
    "shape:",
    "returns", returns_np.shape,
    "mean", cross_mean.shape,
    "std", cross_std.shape,
    "zscore", zscore.shape,
)

# 把第一个交易日的计算拆成表格，直接观察“个股收益−市场均值”和 z-score。
first_day_cross_section = pd.DataFrame(
    {
        "return": returns_np[0],
        "equal_weight_mean": cross_mean[0, 0],
        "excess_return": excess_return[0],
        "zscore": zscore[0],
    },
    index=close.columns,
)
first_day_cross_section.round(4)
"""
        ),
        md(
            """
## 轴选错不会报错，但金融含义会错

收益矩阵的行是交易日、列是股票：

- `axis=1`：压缩列，得到“每天跨股票”的统计量；
- `axis=0`：压缩行，得到“每只股票跨日期”的统计量。

NumPy 只执行指定方向，不知道你想算市场平均还是股票长期平均，因此必须先写清矩阵语义。

`axis` 可以理解为“被压缩掉的维度”。先用一个 `2 × 3` 小矩阵得到确定结果，再回到真实收益矩阵。
"""
        ),
        code(
            r"""
# 小矩阵：axis=1 每行一个均值；axis=0 每列一个均值。
axis_demo = np.array([[1, 2, 3], [4, 5, 6]])
print("axis=1:", axis_demo.mean(axis=1))  # [2., 5.]
print("axis=0:", axis_demo.mean(axis=0))  # [2.5, 3.5, 4.5]

# 回到收益矩阵，对比每天横截面均值和每只股票时间序列均值。
mean_by_date = returns_np.mean(axis=1)
mean_by_stock = returns_np.mean(axis=0)
assert mean_by_date.shape[0] == len(close) - 1
assert mean_by_stock.shape[0] == close.shape[1]

print("按日平均 shape:", mean_by_date.shape, "前 3 日:", np.round(mean_by_date[:3], 6))
pd.Series(mean_by_stock, index=close.columns, name="mean_daily_return").to_frame()
"""
        ),
        md(
            """
## 课程示例 3：循环与矢量化性能

`np.tile(prices, (150, 1))` 只是把同一价格矩阵沿时间方向重复 150 次，用来放大性能差异；它没有产生新的市场信息，不能作为回测样本扩充方法。

两个函数都接收 `(T, N)` 价格矩阵，输出 `(T-1, N)` 收益矩阵：

- `np.empty` 只分配内存、不初始化内容；循环随后会覆盖每个位置；
- `timeit.repeat(..., number=1, repeat=3)` 独立计时 3 次，每次运行函数 1 次；
- 取最小值用于减少偶发系统调度干扰，只代表本机本次测量。

先用 `assert_allclose` 验证结果一致，再比较速度；否则“更快”没有意义。
"""
        ),
        code(
            r"""
# 用同一收益任务比较双重循环和 NumPy 切片矢量化的运行时间。
large = np.tile(prices, (150, 1))
print("性能测试矩阵:", prices.shape, "→", large.shape)

def loop_returns(array):
    # 输入 (T,N) 价格矩阵，输出 (T-1,N) 收益矩阵。
    output = np.empty((array.shape[0] - 1, array.shape[1]))
    for row in range(1, array.shape[0]):
        for column in range(array.shape[1]):
            output[row - 1, column] = array[row, column] / array[row - 1, column] - 1
    return output

def vectorized_returns(array):
    # 使用 NumPy 切片一次计算全部相邻收益。
    return array[1:] / array[:-1] - 1

np.testing.assert_allclose(loop_returns(large[:100]), vectorized_returns(large[:100]))
loop_time = min(timeit.repeat(lambda: loop_returns(large), number=1, repeat=3))
vector_time = min(timeit.repeat(lambda: vectorized_returns(large), number=1, repeat=3))
print(f"循环: {loop_time:.4f}s")
print(f"矢量化: {vector_time:.4f}s")
print(f"本机加速倍数: {loop_time / vector_time:.1f}x")
"""
        ),
        md(
            """
## 课程示例 4：视图、拷贝和常用数组变换

这组 API 分成三类学习：

1. `view` 与 `copy`：修改结果会不会影响原数组；
2. `reshape`、`concatenate`、`stack`：如何改变或组合矩阵形状；
3. `where` 与 `mean(axis=...)`：如何按条件筛选和按轴聚合。

### 4.1 切片视图与显式拷贝

NumPy 的**基础切片**通常返回视图，和原数组共享底层内存；花式索引和布尔索引通常返回拷贝。`.copy()` 可以显式创建独立数组。量化研究中如果对收益切片做原地去极值或标准化，误改原矩阵会污染后续实验。
"""
        ),
        code(
            r"""
# 基础切片共享内存，修改 view 会同步改变 original。
original = np.arange(1.0, 7.0)  # [1., 2., 3., 4., 5., 6.]
view = original[1:4]            # [2., 3., 4.]
view[0] = 99
assert np.shares_memory(original, view)
print("修改 view 后 original:", original)  # [1., 99., 3., 4., 5., 6.]

# 用一份干净数组演示 copy，修改副本不会影响来源。
copy_source = np.arange(1.0, 7.0)   # [1., 2., 3., 4., 5., 6.]
safe_copy = copy_source[1:4].copy() # [2., 3., 4.]
safe_copy[0] = -1
assert not np.shares_memory(copy_source, safe_copy)
assert copy_source[1] == 2
print("修改 copy 后来源数组:", copy_source)
print("独立的 safe_copy:", safe_copy)      # [-1., 3., 4.]
"""
        ),
        md(
            """
### 4.2 改变形状与组合数组

| 方法 | 做什么 | 本例结果 | 量化场景 |
|---|---|---|---|
| `reshape(2, 3)` | 不改元素，只改变观察形状 | `(6,) → (2, 3)` | 将一维数据按批次或资产维度组织 |
| `concatenate` | 沿已有轴首尾拼接 | `[1,2] + [3,4] → [1,2,3,4]` | 拼接连续时间段或同结构数据 |
| `stack` | 新建一个轴后堆叠 | 两个 `(3,) → (3,2)` | 组成“日期 × 股票”矩阵 |

`reshape` 前后元素总数必须一致；`concatenate` 默认沿 `axis=0` 拼接且不新增维度，其他轴的长度必须兼容；`stack` 会先新增维度。
"""
        ),
        code(
            r"""
# 分别演示改变形状、沿已有轴拼接、沿新轴堆叠。
source = np.arange(6)                     # [0, 1, 2, 3, 4, 5]
reshaped = source.reshape(2, 3)           # [[0,1,2], [3,4,5]]

left = np.array([1, 2])
right = np.array([3, 4])
concatenated = np.concatenate([left, right])  # [1, 2, 3, 4]

stock_a_returns = returns_np[:3, 0]       # 股票 A 的前 3 日收益
stock_b_returns = returns_np[:3, 1]       # 股票 B 的前 3 日收益
stacked = np.stack(
    [stock_a_returns, stock_b_returns],
    axis=1,
)  # shape=(3,2)，行=日期，列=股票

print("source:", source, "shape =", source.shape)
print("reshape:\n", reshaped, "shape =", reshaped.shape)
print("concatenate:", concatenated)
print("stack:\n", np.round(stacked, 6), "shape =", stacked.shape)
"""
        ),
        md(
            """
### 4.3 条件选择与按股票求均值

`np.where(condition, x, y)` 对每个位置判断条件：满足时取 `x`，否则取 `y`，输出 shape 与广播后的输入一致。它不会删除元素；真正筛除元素要使用布尔索引。这里把首日负收益替换成 0，只用于演示条件选择，不代表可交易策略。

`returns_np.mean(axis=0)` 压缩时间轴，得到每只股票一个样本期平均日收益。它是描述统计，不等于未来预期收益。
"""
        ),
        code(
            r"""
# 首日只保留正收益；再沿时间轴计算每只股票的平均日收益。
first_day_returns = returns_np[0]
positive_only = np.where(first_day_returns > 0, first_day_returns, 0)
mean_return = returns_np.mean(axis=0)

pd.DataFrame(
    {
        "first_day_return": first_day_returns,
        "positive_only": positive_only,
        "sample_mean_return": mean_return,
    },
    index=close.columns,
).round(6)
"""
        ),
        md(
            """
## 方法边界

- 广播不理解证券标签，矩阵进入 NumPy 前要由 Pandas 完成对齐。
- 向量化可能创建大型中间数组；内存峰值也要测量。
- 金额、累计净值和优化问题默认保留 `float64`，不要只为省内存盲目降精度。
- 性能倍数与硬件、数据规模有关，以本机实测为准，不照搬课程中的固定倍数。
"""
        ),
    ]
    write_notebook(NOTEBOOKS / "32_NumPy广播与收益矩阵.ipynb", cells)


def build_lesson_33():
    cells = [
        md(
            source_note(
                33,
                "NumPy 矩阵运算与 PCA",
                "33_youtube-8re1itSulGk",
            )
        ),
        md(
            """
## 本节量化问题

课程把矩阵乘法、`linalg.solve`、协方差/相关矩阵、特征分解和 PCA 连成组合分析。本 Notebook 用第 32 课同一份**确定性模拟日线**，按下面顺序建立可核对链路：

1. 从 6 只虚构资产、756 个工作日的长表构造价格与简单收益矩阵；
2. 区分 `*` 的逐资产收益贡献与 `@` 的组合收益；
3. 从样本协方差得到组合方差，并求仅含预算约束、允许做空的全局最小方差组合；
4. 对相关矩阵做 PCA，检查第一主成分是否与这 6 只模拟资产的样本共同波动代理一致。

**输入**：`daily_prices.csv`，原始 shape 为 `(4536, 9)`。  
**核心中间结果**：价格矩阵 `(756, 6)`、收益矩阵 `(755, 6)`。  
**输出**：组合贡献表、风险与权重比较表、相关热力图、PCA 方差解释与载荷表。

这里研究的是矩阵方法，不是在验证真实市场因子，也不构成策略收益评估。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 先看原始长表

原始 CSV 中一行代表“某天、某只股票”的一组行情。`read_csv` 读取文件；`parse_dates=["date"]` 在读取时把日期文本解析为 Pandas 时间类型。

为看清“一天有多只股票”，下面展示第一个交易日的全部 6 行，而不是只看普通 `head()`。
"""
        ),
        code(
            r"""
# 读取原始长表，并展示首个交易日的全部股票。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
first_date = daily["date"].min()
first_day_rows = (
    daily.loc[
        daily["date"].eq(first_date),
        ["date", "symbol", "sector", "adj_close", "volume"],
    ]
    .sort_values("symbol")
    .reset_index(drop=True)
)

print("原始表 shape =", daily.shape)
print("交易日数量 =", daily["date"].nunique())
print("股票数量 =", daily["symbol"].nunique())
first_day_rows
"""
        ),
        md(
            """
## 1. 从长表到带标签价格矩阵

`pivot` 只负责重排，不做平均或求和：

- `index="date"`：每行对应一个交易日；
- `columns="symbol"`：每列对应一只股票；
- `values="adj_close"`：格子里放复权收盘价；
- `sort_index()`：按日期标签升序排列。

`pivot` 要求每个“日期 × 股票”组合最多一行；若原始数据有重复，应先清洗，或明确使用 `pivot_table` 的聚合规则。
"""
        ),
        code(
            r"""
# 检查键唯一后，把复权收盘价重排为“日期 × 股票”宽表。
assert not daily.duplicated(["date", "symbol"]).any()
close = daily.pivot(
    index="date",
    columns="symbol",
    values="adj_close",
).sort_index()

assert close.index.is_unique and close.columns.is_unique
assert not close.isna().any().any()
print("close.shape =", close.shape, "含义：日期 × 股票")
close.head(3)
"""
        ),
        md(
            """
### 计算简单收益率

`pct_change(fill_method=None)` 对每只股票分别计算：

```text
当日简单收益率 = 当日价格 / 前一日价格 - 1
```

第一日没有前值，因此会产生一行 `NaN`。本确定性数据已确认价格矩阵没有其他缺失，所以用 `.iloc[1:]` 明确移除首行；真实多资产数据若直接 `dropna()`，任一股票缺失都可能删除整天，必须先诊断缺失原因。
"""
        ),
        code(
            r"""
# 按列计算相邻日简单收益，并移除必然没有前值的第一日。
returns_with_first_nan = close.pct_change(fill_method=None)
assert returns_with_first_nan.iloc[0].isna().all()
returns = returns_with_first_nan.iloc[1:]

assert not returns.isna().any().any()
print("returns.shape =", returns.shape, "含义：日期 × 股票")
returns.head(3).round(6)
"""
        ),
        md(
            """
### 何时转为 NumPy

`to_numpy(dtype=np.float64)` 只保留数值，把 Pandas 的日期索引和股票列名移除。矩阵运算会更直接，但 NumPy 不再替你检查证券标签，所以转换前先保存并核验列顺序。
"""
        ),
        code(
            r"""
# 保存标签后转为浮点收益矩阵；R 的行是日期，列是股票。
assets = returns.columns.copy()
R = returns.to_numpy(dtype=np.float64)
T, N = R.shape

assert R.shape == (755, 6)
print("R.shape =", R.shape)
print("R.dtype =", R.dtype)
print("T（收益日期数）=", T, "N（股票数）=", N)
print("列顺序 =", assets.tolist())
"""
        ),
        md(
            """
## 课程示例 1：组合收益是矩阵乘法

`R` 的形状是 `(交易日, 股票)`，权重向量的形状是 `(股票,)`。

| 运算 | 做什么 | 输出 shape | 金融含义 |
|---|---|---|---|
| `R * weights` | 逐元素乘法；`(N,)` 权重沿日期维广播 | `(T, N)` | 每天、每只股票对组合收益的贡献 |
| `R @ weights` | 每行与权重向量做点积 | `(T,)` | 每天一个组合总收益 |

对某一天而言：

> 组合收益 = 股票 1 收益 × 权重 1 + 股票 2 收益 × 权重 2 + …

因此，`R @ weights` 等价于先执行 `R * weights`，再沿股票轴执行 `.sum(axis=1)`。`axis=1` 属于 `sum`，`@` 本身没有 `axis` 参数。
"""
        ),
        code(
            r"""
# 用 2 天 × 3 只股票的确定性数据观察 * 和 @ 的差别。
demo_returns = np.array([
    [0.01, -0.02, 0.03],   # 第 1 天三只股票收益
    [0.02,  0.01, -0.01],  # 第 2 天三只股票收益
])
demo_weights = np.array([0.50, 0.30, 0.20])

# * 逐元素相乘，保留每只股票的收益贡献，shape=(2,3)。
demo_contribution = demo_returns * demo_weights
# @ 对每一行做点积，直接得到每天组合收益，shape=(2,)。
demo_portfolio_return = demo_returns @ demo_weights

demo_table = pd.DataFrame(
    demo_contribution,
    index=["第1日", "第2日"],
    columns=["股票A贡献", "股票B贡献", "股票C贡献"],
)
demo_table["贡献合计"] = demo_contribution.sum(axis=1)
demo_table["@组合收益"] = demo_portfolio_return

np.testing.assert_allclose(demo_table["贡献合计"], demo_table["@组合收益"])
assert np.isclose(demo_portfolio_return[0], 0.005)
demo_table
"""
        ),
        md(
            """
第 1 天的手工计算为：

```text
1% × 50% + (-2%) × 30% + 3% × 20%
= 0.5% - 0.6% + 0.6%
= 0.5%
```

### 等权权重的形状

`np.full(N, 1 / N)` 创建长度为 `N` 的等权向量。权重必须与收益矩阵列顺序一一对应，并检查合计为 1。
"""
        ),
        code(
            r"""
# 创建与 assets 列顺序一致的等权权重。
weights_equal = np.full(N, 1 / N)
weight_table = pd.DataFrame(
    {"weight": weights_equal, "weight_percent": weights_equal * 100},
    index=assets,
)

assert weights_equal.shape == (N,)
assert np.isclose(weights_equal.sum(), 1)
print("weights_equal.shape =", weights_equal.shape)
print("权重合计 =", f"{weights_equal.sum():.2%}")
weight_table.round(4)
"""
        ),
        md(
            """
### 回到完整收益矩阵

实际数据中，`R` 有 `T` 个交易日和 `N` 只股票。下面同时保留逐股票贡献和组合总收益，并用断言验证两条计算路径一致。
"""
        ),
        code(
            r"""
# * 得到每天每只股票的收益贡献；@ 得到每天组合总收益。
contribution_by_asset = R * weights_equal
portfolio_return = R @ weights_equal

assert contribution_by_asset.shape == (T, N)
assert portfolio_return.shape == (T,)
np.testing.assert_allclose(
    portfolio_return,
    contribution_by_asset.sum(axis=1),
)

# 用带标签表格查看前 5 天：最后一列应等于前面各股票贡献之和。
contribution_preview = pd.DataFrame(
    contribution_by_asset[:5],
    index=returns.index[:5],
    columns=assets,
)
contribution_preview["贡献合计"] = contribution_by_asset[:5].sum(axis=1)
contribution_preview["@组合收益"] = portfolio_return[:5]
contribution_preview.round(6)
"""
        ),
        md(
            """
这里每一期都使用同一目标权重，隐含**逐期恢复目标权重、忽略交易成本**。买入持有组合的权重会随价格漂移，不能长期直接套用固定 `weights_equal`；由收盘信号产生的权重还要滞后到可成交时点。

## 课程示例 2：协方差与相关系数

先用 3 个观测、2 个资产的确定性收益认识 API：

- `rowvar=False`：行是观测，列是资产；
- `ddof=1`：样本协方差除以 `T-1`；
- 协方差有“收益率平方”单位，相关系数没有量纲。

两者都描述样本共同波动，不等于因果关系。
"""
        ),
        code(
            r"""
# 用小矩阵得到可手工核对的样本协方差和相关系数。
risk_demo = np.array([
    [ 0.01,  0.00],
    [ 0.00,  0.01],
    [-0.01, -0.01],
])
demo_covariance = np.cov(risk_demo, rowvar=False, ddof=1)
demo_correlation = np.corrcoef(risk_demo, rowvar=False)

display(pd.DataFrame(
    demo_covariance,
    index=["资产A", "资产B"],
    columns=["资产A", "资产B"],
).round(5))
pd.DataFrame(
    demo_correlation,
    index=["资产A", "资产B"],
    columns=["资产A", "资产B"],
).round(2)
"""
        ),
        md(
            """
### 回到完整收益矩阵并年化

日收益样本协方差乘以 `252`，是在“约 252 个交易期、收益协方差可线性年化”的约定下得到年化协方差。它忽略自相关、交易日差异和结构变化，不是对所有过程都成立的恒等式。
"""
        ),
        code(
            r"""
# 估计完整样本的日协方差、相关矩阵与约定式年化协方差。
covariance = np.cov(R, rowvar=False, ddof=1)
correlation = np.corrcoef(R, rowvar=False)
annual_covariance = covariance * 252

assert covariance.shape == (N, N)
assert correlation.shape == (N, N)

# 找出对角线之外相关性最高和最低的资产对，便于核对样本结构。
upper_triangle = np.triu_indices(N, k=1)
pair_table = pd.DataFrame({
    "asset_1": assets.to_numpy()[upper_triangle[0]],
    "asset_2": assets.to_numpy()[upper_triangle[1]],
    "correlation": correlation[upper_triangle],
}).sort_values("correlation")

print("日协方差 shape =", covariance.shape)
display(pair_table.iloc[[0, -1]].reset_index(drop=True).round(4))
pd.DataFrame(correlation, index=assets, columns=assets).round(3)
"""
        ),
        md(
            """
### 二次型得到组合方差

组合年化方差与波动率分别为：

```text
annual_variance   = wᵀ Σannual w
annual_volatility = sqrt(annual_variance)
```

方差的单位是收益率平方，不应把它直接当作普通百分比；开平方后才是与收益率同量纲的波动率。
"""
        ),
        code(
            r"""
# 用二次型计算等权组合年化方差，再开平方得到年化波动率。
equal_variance = weights_equal @ annual_covariance @ weights_equal
equal_volatility = np.sqrt(equal_variance)

risk_summary = pd.Series({
    "年化方差（收益率平方）": equal_variance,
    "年化波动率": equal_volatility,
}, name="等权组合")
display(risk_summary.to_frame())
print("等权组合年化波动率 =", f"{equal_volatility:.4%}")
"""
        ),
        md(
            """
## 课程示例 3：`np.linalg.solve` 与最小方差权重

先用固定方程 `A @ x = b` 认识 `solve`。它直接求解线性方程，不显式构造逆矩阵，通常比 `np.linalg.inv(A) @ b` 更稳定。
"""
        ),
        code(
            r"""
# 解固定的 2 × 2 线性方程，并代回验证。
A = np.array([[2.0, 1.0], [1.0, 3.0]])
b = np.array([1.0, 1.0])
x = np.linalg.solve(A, b)

np.testing.assert_allclose(A @ x, b)
pd.DataFrame({"x": x, "A @ x": A @ x, "b": b}, index=["方程1", "方程2"])
"""
        ),
        md(
            """
### 仅含预算约束、允许做空的全局最小方差组合

只要求权重和为 1 时，全局最小方差（Global Minimum Variance, GMV）权重为：

```text
w = Σ⁻¹1 / (1ᵀΣ⁻¹1)
```

`np.linalg.solve(Σ, 1)` 直接求解 `Σx=1`。这里仍有“权重合计为 1”的预算约束，但没有多头或仓位上下限，所以负权重表示做空。
"""
        ),
        code(
            r"""
# 求仅含预算约束的 GMV 方向，再归一化使权重和为 1。
ones = np.ones(N)
raw_solution = np.linalg.solve(annual_covariance, ones)
budget_only_gmv = raw_solution / (ones @ raw_solution)
gmv_variance = budget_only_gmv @ annual_covariance @ budget_only_gmv
gmv_volatility = np.sqrt(gmv_variance)

assert np.isclose(budget_only_gmv.sum(), 1)
assert gmv_variance <= equal_variance + 1e-12
weight_comparison = pd.DataFrame(
    {
        "等权": weights_equal,
        "预算约束_GMV_允许做空": budget_only_gmv,
    },
    index=assets,
)
weight_percent_table = (weight_comparison * 100).rename(
    columns=lambda name: f"{name}（%）"
)
display(weight_percent_table.round(4).rename_axis("股票"))
pd.DataFrame(
    {
        "年化方差": [equal_variance, gmv_variance],
        "年化波动率": [equal_volatility, gmv_volatility],
    },
    index=["等权", "预算约束_GMV_允许做空"],
)
"""
        ),
        md(
            """
GMV 结果只是在同一训练样本内优化和评价：协方差矩阵奇异或病态时 `solve` 会失败或极不稳定；本例也没有多头、仓位上限、换手、成本或样本外验证，不能直接当作可执行组合。

### 相关矩阵热力图怎么读？

- 每个格子是两只股票日收益的相关系数，范围为 `-1～1`；
- 对角线是资产与自身的相关性，恒为 `1.00`；
- 红色表示正相关，蓝色表示负相关，接近白色表示线性相关较弱；
- 图中直接标出两位小数，颜色用于快速浏览，数字用于准确比较。

热力图里的红色只是“正相关”的颜色编码，**不是 Notebook 告警**。相关性描述样本期内的同步波动，不代表因果关系，也不保证未来稳定。
"""
        ),
        code(
            r"""
# 用带数值标注的热力图同时呈现相关方向、强弱和精确数值。
fig, ax = plt.subplots(figsize=(8.5, 6.5))
sns.heatmap(
    correlation,
    ax=ax,
    annot=True,
    fmt=".2f",
    cmap="RdBu_r",
    center=0,
    vmin=-1,
    vmax=1,
    square=True,
    linewidths=0.6,
    linecolor="white",
    xticklabels=assets,
    yticklabels=assets,
    annot_kws={"fontsize": 10},
    cbar_kws={"label": "相关系数", "shrink": 0.82},
)
ax.set_title("模拟资产日收益相关矩阵", fontsize=15, pad=14)
ax.set_xlabel("股票")
ax.set_ylabel("股票")
ax.tick_params(axis="x", rotation=30)
ax.tick_params(axis="y", rotation=0)
fig.tight_layout()
fig.savefig(
    OUTPUT_DIR / "33_correlation_matrix.png",
    dpi=160,
    bbox_inches="tight",
)
plt.show()
"""
        ),
        md(
            """
## 课程示例 4：特征分解与 PCA

PCA（Principal Component Analysis，主成分分析）把多个相关资产压缩为少数互不相关的统计方向。第一步先把每只股票收益标准化：

```text
标准化收益 = (原收益 − 样本均值) / 样本标准差
```

这样高波动股票不会仅因为数值尺度更大而主导结果。`axis=0` 表示每只股票沿时间维分别计算均值；`ddof=1` 与样本协方差口径一致。标准化后每列均值约为 0、样本标准差约为 1，因此下面等价于对收益相关矩阵做 PCA，而不是对原始协方差矩阵做 PCA。
"""
        ),
        code(
            r"""
# 对每只股票沿时间轴标准化，并检查列均值与标准差。
standardized = (R - R.mean(axis=0)) / R.std(axis=0, ddof=1)
standardized_table = pd.DataFrame(
    standardized,
    index=returns.index,
    columns=assets,
)
standardization_check = pd.DataFrame(
    {
        "mean": standardized_table.mean(),
        "std_ddof1": standardized_table.std(ddof=1),
    }
)
standardization_check.round(6)
"""
        ),
        md(
            """
### 特征值、特征向量与解释率

先用一个固定对称矩阵认识 `np.linalg.eigh`：

- 它用于实对称或复 Hermitian 矩阵；
- 特征值默认升序；
- 特征向量按列存放；
- 特征向量整体乘以 `-1` 仍表示同一方向。
"""
        ),
        code(
            r"""
# 分解固定对称矩阵，并用 V @ diag(λ) @ V.T 重建原矩阵。
symmetric_demo = np.array([[2.0, 1.0], [1.0, 2.0]])
demo_eigenvalues, demo_eigenvectors = np.linalg.eigh(symmetric_demo)
demo_reconstructed = (
    demo_eigenvectors
    @ np.diag(demo_eigenvalues)
    @ demo_eigenvectors.T
)

np.testing.assert_allclose(demo_reconstructed, symmetric_demo)
print("特征值（默认升序）=", demo_eigenvalues)
print("重建矩阵：\n", np.round(demo_reconstructed, 6))
"""
        ),
        md(
            """
### 实际 PCA 与方差解释比例

特征值表示每个主成分解释的样本方差；特征向量表示该统计方向对各股票的载荷。实际使用时按特征值倒序排列。方差解释比例是“该特征值 ÷ 全部特征值之和”，累计比例最终应为 100%。
"""
        ),
        code(
            r"""
# 对标准化收益的相关矩阵做特征分解，并按解释方差从大到小排序。
corr_for_pca = np.cov(standardized, rowvar=False, ddof=1)
eigenvalues, eigenvectors = np.linalg.eigh(corr_for_pca)
order = np.argsort(eigenvalues)[::-1]
eigenvalues = eigenvalues[order]
eigenvectors = eigenvectors[:, order]
explained_ratio = eigenvalues / eigenvalues.sum()

assert np.isclose(explained_ratio.sum(), 1)
pca_summary = pd.DataFrame(
    {
        "特征值": eigenvalues,
        "方差解释比例": [f"{value:.3%}" for value in explained_ratio],
        "累计比例": [f"{value:.3%}" for value in np.cumsum(explained_ratio)],
    },
    index=[f"PC{i}" for i in range(1, N + 1)],
)
pca_summary.round(4)
"""
        ),
        md(
            """
### 第一主成分载荷、得分与共同波动代理

- `eigenvectors[:, 0]`：PC1 对每只股票的载荷；
- `standardized @ loading`：每个日期的 PC1 得分；
- `standardized.mean(axis=1)`：这 6 只样本资产的等权标准化共同波动代理，不是可交易市场组合收益。

为让不同线性代数实现的展示方向一致，下面约定“绝对值最大的载荷为正”；这只是符号规范，不改变主成分本身。
"""
        ),
        code(
            r"""
# 统一 PC1 符号，计算得分，并与样本共同波动代理比较。
pc1_loading = eigenvectors[:, 0].copy()
largest_loading_position = np.argmax(np.abs(pc1_loading))
if pc1_loading[largest_loading_position] < 0:
    pc1_loading *= -1

first_pc_score = standardized @ pc1_loading
equal_weight_proxy = standardized.mean(axis=1)
pc_proxy_corr = np.corrcoef(first_pc_score, equal_weight_proxy)[0, 1]

loading_table = pd.DataFrame(
    {"PC1载荷": pc1_loading},
    index=assets,
)
display(loading_table.round(4))
print("PC1 与样本共同波动代理相关系数 =", round(float(pc_proxy_corr), 3))
assert pc_proxy_corr > 0.5
"""
        ),
        md(
            """
## 可复用结论、练习与边界

### 可复用结论

1. Pandas 负责对齐日期和股票标签，NumPy 负责形状明确后的矩阵运算。
2. `*` 保留逐资产贡献，`@` 收缩资产维得到组合总收益。
3. `wᵀΣw` 是组合方差，开平方才是波动率。
4. PCA 最大化样本方差解释量，不最大化收益，也不自动提供预测信号。

### 建议练习

- 把等权改成自定义权重，先检查 shape、列顺序和权重合计，再核对“贡献合计 = `@` 结果”。
- 删除一只股票后重新计算 GMV 与 PCA，观察协方差估计和 PC1 载荷如何变化。
- 把样本拆为训练期和测试期，只在训练期估计协方差/PCA，再检查测试期稳定性。

### 方法边界

- `np.linalg.eigh` 针对对称矩阵，返回特征值默认从小到大，第一主成分要倒序取。
- 特征向量整体乘以 `-1` 仍是同一方向，因此符号没有固定含义。
- 预算约束 GMV 允许产生负权重；它不是 A 股普通多头账户可直接执行的组合。
- 样本内最小方差通常偏乐观，协方差和主成分会随窗口变化。
- 全样本 PCA 只适合描述；若用作预测特征，必须在训练窗口拟合，避免未来信息。
- PC1 与本样本代理高度相关，只说明模拟样本同步，不证明它是真实市场因子。
"""
        ),
    ]
    write_notebook(NOTEBOOKS / "33_NumPy矩阵运算与PCA.ipynb", cells)


def build_lesson_34():
    cells = [
        md(
            source_note(
                34,
                "Pandas 标签与行情表",
                "34_youtube-06Rm58cYWZg",
            )
        ),
        md(
            """
## 本节量化问题

本实验读取 6 只模拟资产、756 个交易日的日线长表，构造“日期 × 股票”的复权收盘价宽表，再依次验证：

1. 选择一列和多列时，`Series`、`DataFrame` 的对象类型和 shape 有何不同；
2. Pandas 如何按日期标签自动对齐，以及缺失标签为何产生 `NaN`；
3. `loc` 的标签端点和 `iloc` 的位置端点如何对应；
4. `float32` 节省了多少内存、引入了多少表示误差；
5. `apply(axis=0)` 和向量化表达式如何得到相同的按股票年化收益。

输入是 `(4536, 9)` 的模拟日线长表；核心中间表 `close` 的 shape 是 `(756, 6)`，行表示日期、列表示股票。输出优先保留日期和股票标签，便于直接核对。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 先看原始行情表

先原样读取 CSV，确认字段、行数、股票数、日期数和日期 dtype。`parse_dates=["date"]` 要求 pandas 在读取时把 `date` 从文本转换为 `datetime64[ns]`。

此时数据仍是**长表**：每一行是一只股票在一个交易日的一条记录。先观察原始数据，再做任何重排。
"""
        ),
        code(
            r"""
# 读取并展示原始长表；最后一行保留为表格输出。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
print("daily.shape =", daily.shape)
print("字段 =", daily.columns.tolist())
print("股票数 =", daily["symbol"].nunique())
print("日期数 =", daily["date"].nunique())
print("date dtype =", daily["date"].dtype)

assert daily.shape == (4536, 9)
assert daily["symbol"].nunique() == 6
assert daily["date"].nunique() == 756
daily.head()
"""
        ),
        md(
            """
### 从长表重排为“日期 × 股票”宽表

`pivot(index="date", columns="symbol", values="adj_close")` 的三个关键参数分别决定：

- `index`：结果的行标签，这里是交易日期；
- `columns`：结果的列标签，这里是股票代码；
- `values`：每个“日期 × 股票”格子里的数值，这里是复权收盘价。

`pivot` 要求每个 `(date, symbol)` 组合唯一；若同一股票同一天有多条记录，应先明确聚合规则，而不是让重复值静默通过。`sort_index()` 默认整理行轴上的日期。
"""
        ),
        code(
            r"""
# 检查主键唯一后，将复权收盘价重排为带日期和股票标签的宽表。
duplicate_pairs = daily.duplicated(["date", "symbol"]).sum()
assert duplicate_pairs == 0

close = daily.pivot(
    index="date",
    columns="symbol",
    values="adj_close",
).sort_index()

assert close.index.is_unique and close.columns.is_unique
assert close.shape == (756, 6)
print("close.shape =", close.shape, "含义：日期 × 股票")
print("股票标签 =", close.columns.tolist())
close.head()
"""
        ),
        md(
            """
## 课程示例 1：Series、DataFrame 和标签对齐

### 1.1 选择一列与选择多列

`close["BANK_A"]` 用一个列标签选择单列，结果是一维 `Series`，shape 为 `(756,)`；`close[["BANK_A", "EV_A"]]` 用列标签列表选择多列，结果仍是二维 `DataFrame`，shape 为 `(756, 2)`。

这里的方括号按**列标签**选择，不等同于 NumPy 按整数位置切片。
"""
        ),
        code(
            r"""
# 对比选择单列和多列后的对象类型与 shape。
bank_series = close["BANK_A"]
two_stock_frame = close[["BANK_A", "EV_A"]]

assert isinstance(bank_series, pd.Series)
assert isinstance(two_stock_frame, pd.DataFrame)
print("bank_series.shape =", bank_series.shape)
print("two_stock_frame.shape =", two_stock_frame.shape)
two_stock_frame.head()
"""
        ),
        md(
            """
### 1.2 用确定性小例子观察自动对齐

两个 Series 做算术时，pandas 先取日期标签的**并集**，再把同一标签上的数值配对。任一侧缺少某个日期，该日期的计算结果就是 `NaN`。

下面用股票收益减基准收益计算超额收益。数值很小且固定，可以直接核对：共同日期只有 `2025-03-04` 和 `2025-03-05`。
"""
        ),
        code(
            r"""
# 两个收益序列的日期不完全相同，减法会按标签并集对齐。
stock_return = pd.Series(
    [0.010, -0.020, 0.030],
    index=pd.to_datetime(["2025-03-03", "2025-03-04", "2025-03-05"]),
    name="stock_return",
)
benchmark_return = pd.Series(
    [0.004, -0.001, 0.002],
    index=pd.to_datetime(["2025-03-04", "2025-03-05", "2025-03-06"]),
    name="benchmark_return",
)
aligned_excess = (stock_return - benchmark_return).rename("excess_return")

alignment_demo = pd.concat(
    [stock_return, benchmark_return, aligned_excess],
    axis=1,
)
assert aligned_excess.isna().sum() == 2
alignment_demo
"""
        ),
        md(
            """
### 1.3 显式决定使用交集，而不是掩盖缺口

`Series.align(other, join="inner")` 只保留两侧共同日期。进入组合、超额收益或回归计算前，还应检查双方独有的日期。

自动对齐只保证“标签相同的数值被放在一起”，不会判断两个相同日期是否使用相同时区、交易日历、复权口径、频率或单位。也不要默认用 `fill_value=0`：只有业务上能证明“缺失就是零”时，这个假设才成立。
"""
        ),
        code(
            r"""
# 显式保留日期交集，并分别报告双方缺失的标签。
stock_common, benchmark_common = stock_return.align(
    benchmark_return,
    join="inner",
)
safe_excess = stock_common - benchmark_common

stock_only = stock_return.index.difference(benchmark_return.index)
benchmark_only = benchmark_return.index.difference(stock_return.index)
print("仅股票有 =", [date.date() for date in stock_only])
print("仅基准有 =", [date.date() for date in benchmark_only])

safe_alignment = pd.DataFrame(
    {
        "stock_return": stock_common,
        "benchmark_return": benchmark_common,
        "excess_return": safe_excess,
    }
)
assert safe_alignment.index.equals(
    pd.to_datetime(["2025-03-04", "2025-03-05"])
)
safe_alignment
"""
        ),
        md(
            """
## 课程示例 2：`loc` 与 `iloc` 的端点

`loc` 使用日期和股票标签；标签切片包含开始、结束两个端点。`iloc` 使用整数位置，停止位置不包含，所以要对结束行位置显式 `+1`。

列也必须选择相同对象：不能让 `loc` 选择 `BANK_A、EV_A`，却让 `iloc[:, :2]` 隐式取当前表的前两列。下面先把股票标签转换为真实列位置，再验证两个结果的标签和值完全一致。
"""
        ),
        code(
            r"""
# 用同样的 3 个日期、2 只股票对照 loc 标签切片和 iloc 位置切片。
selected_symbols = ["BANK_A", "EV_A"]
loc_slice = close.loc[
    "2023-03-01":"2023-03-03",
    selected_symbols,
]

row_start = close.index.get_loc(pd.Timestamp("2023-03-01"))
row_stop = close.index.get_loc(pd.Timestamp("2023-03-03")) + 1
column_positions = close.columns.get_indexer(selected_symbols)
assert (column_positions >= 0).all()

iloc_slice = close.iloc[
    row_start:row_stop,
    column_positions,
]

pd.testing.assert_frame_equal(loc_slice, iloc_slice)
print("行位置 =", row_start, "到", row_stop - 1, "；iloc 停止位置 =", row_stop)
print("列位置 =", column_positions.tolist())
loc_slice
"""
        ),
        md(
            """
## 课程示例 3：dtype、内存与精度

`astype("float32")` 把数值列从 64 位浮点数转换成 32 位浮点数，shape 不变。`memory_usage(index=True, deep=True)` 估计各列和索引占用的字节数；本例日期索引不会随数值 dtype 一起减半。

把 `float32` 再转回 `float64` 后与原表比较，可以测出这一次存储转换造成的最大绝对表示误差。它只描述当前价格表，不能自动证明收益复合、协方差和优化结果同样安全。
"""
        ),
        code(
            r"""
# 比较两种浮点 dtype 的总内存和相对原始 float64 的价格表示误差。
close64 = close.astype("float64")
close32 = close.astype("float32")

memory64 = close64.memory_usage(index=True, deep=True).sum()
memory32 = close32.memory_usage(index=True, deep=True).sum()
max_abs_error = (close64 - close32.astype("float64")).abs().to_numpy().max()

dtype_comparison = pd.DataFrame(
    {
        "memory_KiB": [memory64 / 1024, memory32 / 1024],
        "max_abs_error_vs_float64": [0.0, max_abs_error],
    },
    index=pd.Index(["float64", "float32"], name="dtype"),
)

assert close64.shape == close32.shape == (756, 6)
assert close32.dtypes.eq(np.dtype("float32")).all()
assert memory32 < memory64
dtype_comparison
"""
        ),
        md(
            """
## 课程示例 4：`apply` 与向量化年化收益

### 4.1 先用确定性价格表理解 `apply(axis=0)`

`DataFrame.apply(function, axis=0)` 每次把一整列传给函数，因此这里每只股票得到一个结果。几何年化公式为：

> `(期末价格 / 期初价格) ** (每年期数 / 样本变化期数) - 1`

`**` 是幂运算。下面故意使用“每年 2 期、样本有 2 个变化区间”的小例子，因此指数等于 1：A 从 100 涨到 121，结果为 `0.21`；B 从 200 跌到 180，结果为 `-0.10`。
"""
        ),
        code(
            r"""
# 定义按单列价格计算的几何年化收益，并用固定小表核对 axis=0。
def annualized_return(series, periods_per_year=252):
    clean = series.dropna()
    periods = len(clean) - 1
    if periods <= 0:
        raise ValueError("至少需要两个有效价格")
    if clean.iloc[0] <= 0 or clean.iloc[-1] <= 0:
        raise ValueError("几何年化要求期初和期末价格为正")
    ending_to_start = clean.iloc[-1] / clean.iloc[0]
    return ending_to_start ** (periods_per_year / periods) - 1

demo_prices = pd.DataFrame(
    {
        "A": [100.0, 110.0, 121.0],
        "B": [200.0, 190.0, 180.0],
    },
    index=["期初", "中间", "期末"],
)
demo_annual = demo_prices.apply(
    annualized_return,
    axis=0,
    periods_per_year=2,
)

np.testing.assert_allclose(
    demo_annual.to_numpy(),
    np.array([0.21, -0.10]),
)
demo_annual.rename("annualized_return").to_frame()
"""
        ),
        md(
            """
### 4.2 回到完整行情：逐列 `apply` 与整表向量化

完整 `close` 没有缺失值，共有 756 个价格观测，因此相邻价格变化区间是 `756 - 1 = 755`。向量化写法先让期末和期初两行按股票标签相除，再一次对全部股票做幂运算。

本例用 `252` 个交易期代表一年，所以结果是按规则交易期频率计算的样本期几何年化收益；它不是未来预期收益。
"""
        ),
        code(
            r"""
# 用两种方法计算全部股票的年化收益，并按股票标签验证结果一致。
assert close.notna().all().all()
annual_apply = close.apply(
    annualized_return,
    axis=0,
    periods_per_year=252,
)

periods = len(close) - 1
ending_to_start = close.iloc[-1] / close.iloc[0]
annual_vector = ending_to_start ** (252 / periods) - 1

pd.testing.assert_index_equal(annual_apply.index, annual_vector.index)
np.testing.assert_allclose(
    annual_apply.to_numpy(),
    annual_vector.to_numpy(),
    rtol=1e-12,
    atol=1e-12,
)

annual_output = pd.DataFrame(
    {
        "apply_pct": annual_apply * 100,
        "vectorized_pct": annual_vector * 100,
        "absolute_difference": (annual_apply - annual_vector).abs(),
    }
)
print("价格观测数 =", len(close), "；变化期数 =", periods)
annual_output.round(
    {
        "apply_pct": 2,
        "vectorized_pct": 2,
        "absolute_difference": 12,
    }
)
"""
        ),
        md(
            """
### 4.3 正确性验证后再比较性能

`timeit.repeat(..., number=20, repeat=3)` 独立计时 3 轮，每轮执行 20 次。每轮返回的是 20 次总耗时，所以除以 `number` 后才是单次毫秒数；取最小值用于减少偶发调度干扰。

这里的 `lambda` 只把带参数的计算包装成计时器可调用的无参数函数。性能倍数取决于本机、pandas 版本、行列规模和函数复杂度，不能写成固定结论。
"""
        ),
        code(
            r"""
# 分开计时 apply 和向量化表达式，报告本机每次调用耗时。
def vectorized_annualized_return(frame, periods_per_year=252):
    frame_periods = len(frame) - 1
    ending_to_start = frame.iloc[-1] / frame.iloc[0]
    return ending_to_start ** (periods_per_year / frame_periods) - 1

number = 20
repeat = 3
apply_runs = timeit.repeat(
    lambda: close.apply(
        annualized_return,
        axis=0,
        periods_per_year=252,
    ),
    number=number,
    repeat=repeat,
)
vector_runs = timeit.repeat(
    lambda: vectorized_annualized_return(close),
    number=number,
    repeat=repeat,
)

apply_ms = min(apply_runs) / number * 1000
vector_ms = min(vector_runs) / number * 1000
timing = pd.Series(
    {
        "apply_ms_per_call": apply_ms,
        "vectorized_ms_per_call": vector_ms,
        "local_speedup_x": apply_ms / vector_ms,
    },
    name="本机测量值",
)
timing.to_frame()
"""
        ),
        md(
            """
## 安全修改：先筛选、排序并创建独立副本

`between(..., inclusive="both")` 选择包含两端的日期范围；`.eq("BANK_A")` 做逐行标签比较；两个布尔条件用 `&` 连接，不能写 Python 的 `and`。

收益依赖时间顺序，所以筛选后显式按日期排序。`.copy()` 创建独立结果，后续新增列不会修改原始 `daily`。
"""
        ),
        code(
            r"""
# 只保留教学所需列，按时间排序后创建独立的 3 月 BANK_A 表。
march_mask = (
    daily["date"].between(
        "2023-03-01",
        "2023-03-31",
        inclusive="both",
    )
    & daily["symbol"].eq("BANK_A")
)
march = (
    daily.loc[
        march_mask,
        ["date", "symbol", "adj_close"],
    ]
    .sort_values("date")
    .copy()
)

assert len(march) == 23
assert march["date"].is_monotonic_increasing
print("march.shape =", march.shape)
march.head()
"""
        ),
        md(
            """
### 在副本中新增日收益列

`pct_change(fill_method=None)` 按当前行顺序计算“本行价格 ÷ 上一行价格 − 1”，并明确禁止先用旧价格填补缺失值。第一行没有前值，因此 `daily_return` 为 `NaN`。

最后检查原始长表没有新增该列，证明这次修改只发生在 `march` 副本中。
"""
        ),
        code(
            r"""
# 在已排序副本中计算收益；原始 daily 保持不变。
march.loc[:, "daily_return"] = march["adj_close"].pct_change(
    fill_method=None
)

assert "daily_return" not in daily.columns
assert march["daily_return"].isna().sum() == 1
march.head()
"""
        ),
        md(
            """
## 方法边界

- 标签对齐产生 `NaN` 是数据缺口提示，不应直接 `fillna(0)` 掩盖。
- `loc` 依赖标签语义；`iloc` 依赖当前排列位置，行列重排后整数位置会改变。
- `float32` 是否足够取决于金额尺度、累计计算和优化稳定性；本项目默认 `float64`。
- `apply` 适合没有现成向量化表达的复杂逐列/逐行逻辑；常规收益和聚合优先使用内置运算。
- 几何年化假设观测频率规则。内部缺失交易日会使“有效观测数”与真实持有时间不同，必须另行处理。
- 样本期年化收益只是历史描述统计，不是策略承诺或未来预期收益。
"""
        ),
        md(
            """
## 可复用结论与练习

**可复用结论**

1. 先用 pandas 完成日期和证券标签对齐，再决定是否转换为 NumPy。
2. 切片后同时核对标签、shape 和数值，不能只看行数。
3. 性能比较必须在结果一致之后进行，并报告本机测量条件。
4. 对价格做 `pct_change` 前先按证券、时间排序，并明确缺失值处理。

**练习**

- 从 `close` 中选择 `ENERGY_A` 和 `TECH_A` 的 2023 年 4 月数据，分别用 `loc` 和 `iloc` 得到同一结果，并用 `assert_frame_equal` 验证。
- 删除某只股票中间一个日期，比较自动对齐、`align(join="inner")` 和错误的 `fillna(0)` 对超额收益的影响。
- 分别用 252 个交易期和实际日历天数年化同一段收益，解释两种口径为何不同。
"""
        ),
    ]
    write_notebook(NOTEBOOKS / "34_Pandas标签与行情表.ipynb", cells)


def build_lesson_35():
    cells = [
        md(
            source_note(
                35,
                "时间索引与 OHLCV 重采样",
                "35_youtube-TNDtFf1FePM",
            )
        ),
        md(
            """
## 本节量化问题

本实验读取 1 个模拟标的、10 个交易日、每天 48 根的 5 分钟行情，依次完成：

1. 观察原始时间文本及其显式 `+08:00` 偏移；
2. 把同一时刻规范化为 UTC，再转换回 `Asia/Shanghai` 显示；
3. 建立有序、唯一的 `DatetimeIndex`，按本地日期选择数据；
4. 按字段语义把 5 分钟 OHLCV 和成交额聚合到自然日；
5. 用成交额/成交量计算日 VWAP，并从原始 bar 手工复核；
6. 区分普通工作日偏移与带休市表的交易日历。

原始表 shape 为 `(480, 8)`；时间列提升为索引后，`bars` shape 为 `(480, 7)`；最终日频表 shape 为 `(10, 7)`。

本教学数据把 `timestamp` 解释为 5 分钟 bar 的**结束时刻**，例如 `09:35` 表示从开盘后第一段 5 分钟形成的 bar。真实数据必须查阅供应商文档，确认时间戳究竟代表开始、结束还是撮合时刻。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 先看原始 5 分钟数据

原始表每行是一根 5 分钟 K 线。先不要转换时间：直接观察 `timestamp` 的文本形式、字段和 dtype，确认源文本已经包含 `+08:00` 时区偏移。
"""
        ),
        code(
            r"""
# 原样读取 CSV，先展示尚未转换的时间文本和 8 个原始字段。
raw_bars = pd.read_csv(DATA_DIR / "intraday_5m.csv")
print("raw_bars.shape =", raw_bars.shape)
print("原始列 =", raw_bars.columns.tolist())
print("timestamp dtype =", raw_bars["timestamp"].dtype)
print("首条时间文本 =", raw_bars.loc[0, "timestamp"])

assert raw_bars.shape == (480, 8)
assert raw_bars["symbol"].nunique() == 1
raw_bars.head()
"""
        ),
        md(
            """
### 将带偏移时间规范化为 UTC，再转换为上海显示

源字符串已经带 `+08:00`。`pd.to_datetime(..., utc=True, errors="raise")` 会解析其中的偏移，并把同一绝对时刻统一表示为 UTC；`.dt.tz_convert("Asia/Shanghai")` 保持绝对时刻不变，只改变当地显示。

第一条记录可以直接核对：

- 源文本：`2025-03-03T09:35:00+08:00`
- UTC：`2025-03-03 01:35:00+00:00`
- 上海：`2025-03-03 09:35:00+08:00`

如果真实输入是不带时区的上海钟表时间，不能直接用 `utc=True` 假定它属于 UTC；应先解析为 naive 时间，再按来源时区 `tz_localize("Asia/Shanghai")`。
"""
        ),
        code(
            r"""
# 同时保留源文本、UTC 表示和上海表示，观察同一时刻的三种写法。
parsed_utc = pd.to_datetime(
    raw_bars["timestamp"],
    utc=True,
    errors="raise",
)
shanghai_time = parsed_utc.dt.tz_convert("Asia/Shanghai")

timestamp_preview = pd.DataFrame(
    {
        "source_text": raw_bars["timestamp"].head(3),
        "parsed_utc": parsed_utc.head(3),
        "Asia/Shanghai": shanghai_time.head(3),
    }
)
assert str(parsed_utc.dt.tz) == "UTC"
assert str(shanghai_time.dt.tz) == "Asia/Shanghai"
timestamp_preview
"""
        ),
        md(
            """
### 建立有序的 DatetimeIndex

`set_index("timestamp")` 把时间列提升为行索引，所以数据列由 8 列变为 7 列；`sort_index()` 保证时间升序。后续 `first`、`last` 和部分字符串切片都依赖正确的时间顺序。

本例只有一个标的，因此时间戳本身唯一。多标的数据中，不同股票可以共享时间戳，应检查 `(timestamp, symbol)` 联合键，而不是要求 DatetimeIndex 单独唯一。
"""
        ),
        code(
            r"""
# 用上海时间建立索引，并验证单标的教学数据的时间顺序和唯一性。
bars = raw_bars.assign(timestamp=shanghai_time)
bars = bars.set_index("timestamp").sort_index()

assert isinstance(bars.index, pd.DatetimeIndex)
assert str(bars.index.tz) == "Asia/Shanghai"
assert bars["symbol"].nunique() == 1
assert bars.index.is_monotonic_increasing and bars.index.is_unique
assert bars.shape == (480, 7)
print("bars.shape =", bars.shape)
print("时间区间 =", bars.index.min(), "→", bars.index.max())
bars.head()
"""
        ),
        md(
            """
## 课程示例 1：部分字符串索引和时间属性

### 1.1 按索引所在时区选择一个本地日期

`bars.loc["2025-03-03"]` 是 DatetimeIndex 的部分字符串标签选择，返回上海时区中这一个本地日期的全部记录。本例一天有 48 根 bar，第一根标记为 `09:35`，最后一根标记为 `15:00`。
"""
        ),
        code(
            r"""
# 选择上海本地日期 2025-03-03，并展示数量和首尾时间。
one_day = bars.loc["2025-03-03"]

assert len(one_day) == 48
assert one_day.index[0].strftime("%H:%M") == "09:35"
assert one_day.index[-1].strftime("%H:%M") == "15:00"

one_day_summary = pd.Series(
    {
        "bar_count": len(one_day),
        "first_bar": one_day.index[0],
        "last_bar": one_day.index[-1],
    },
    name="value",
)
one_day_summary.to_frame()
"""
        ),
        md(
            """
### 1.2 从 DatetimeIndex 提取小时

`.index.hour` 为每根 bar 返回当地小时；`groupby(...).size()` 再统计各小时包含多少条记录。结果中没有 12 点，是因为教学数据模拟了午间休市。
"""
        ),
        code(
            r"""
# 按上海当地小时统计 bar 数量，保留 hour 标签便于核对交易时段。
hour_counts = (
    one_day.groupby(one_day.index.hour)
    .size()
    .rename("bar_count")
)
hour_counts.index.name = "hour"
assert hour_counts.sum() == 48
hour_counts.to_frame()
"""
        ),
        md(
            """
## 课程示例 2：按字段语义聚合 OHLCV

### 2.1 先按自然日聚合 OHLCV 和成交额

`resample("1D", closed="left", label="left")` 在索引的 `Asia/Shanghai` 时区按自然日分桶：

- `closed="left"`：左边界属于当前桶；
- `label="left"`：用当天 `00:00` 标记结果；
- `open="first"`、`high="max"`、`low="min"`、`close="last"`；
- `volume="sum"`、`amount="sum"`。

`first/last` 依赖前面已经按时间排序。自然日重采样会产生周末空桶，本样本从 12 个自然日桶中用 `dropna(subset=["open"])` 删除 2 个无交易周末，留下 10 个交易日。

当前代码明确只处理一个标的；若 `symbol` 多于一个，必须先按 `symbol` 分组，否则不同证券会被聚合进同一根日 K 线。
"""
        ),
        code(
            r"""
# 为每个字段指定符合日 K 线语义的聚合规则。
assert bars["symbol"].nunique() == 1, "当前示例只适用于单标的"
aggregation = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
    "amount": "sum",
}
calendar_daily = bars.resample(
    "1D",
    closed="left",
    label="left",
).agg(aggregation)

daily_ohlcv = calendar_daily.dropna(subset=["open"]).copy()
assert len(calendar_daily) == 12
assert daily_ohlcv.shape == (10, 6)
print("自然日桶 =", len(calendar_daily), "；有交易日 =", len(daily_ohlcv))
daily_ohlcv.head(3)
"""
        ),
        md(
            """
### 2.2 用成交额除以成交量计算日 VWAP

日 VWAP 使用整个日桶的总成交额除以总成交量：

> `daily_vwap = sum(amount) / sum(volume)`

除法前先检查成交量大于 0，避免得到无意义的无穷大。本模拟数据的 `amount` 来自每根 bar 的典型价格乘成交量，因此这里只验证聚合公式；它不是逐笔成交数据推导出的真实市场 VWAP。
"""
        ),
        code(
            r"""
# 在日频 OHLCV 表上增加 VWAP，并展示公式中的两个输入和结果。
assert daily_ohlcv["volume"].gt(0).all()

daily_bars = daily_ohlcv.copy()
daily_bars.loc[:, "vwap"] = (
    daily_bars["amount"] / daily_bars["volume"]
)

assert daily_bars.shape == (10, 7)
daily_bars[["amount", "volume", "vwap"]].head(3)
"""
        ),
        md(
            """
### 2.3 从原始 5 分钟 bar 手工复核第一天

重新从 `2025-03-03` 的 48 根 bar 计算每个字段，再与 `daily_bars` 的第一行逐项比较。断言验证数值，带字段标签的表格负责让人直接核对。
"""
        ),
        code(
            r"""
# 独立计算首个交易日的 OHLCV、成交额和 VWAP，再与重采样结果比较。
sample_date = daily_bars.index[0]
sample_minutes = bars.loc[sample_date.strftime("%Y-%m-%d")]

manual_values = pd.Series(
    {
        "open": sample_minutes["open"].iloc[0],
        "high": sample_minutes["high"].max(),
        "low": sample_minutes["low"].min(),
        "close": sample_minutes["close"].iloc[-1],
        "volume": sample_minutes["volume"].sum(),
        "amount": sample_minutes["amount"].sum(),
        "vwap": (
            sample_minutes["amount"].sum()
            / sample_minutes["volume"].sum()
        ),
    },
    name="manual_from_5m",
)
resampled_values = (
    daily_bars.loc[sample_date, manual_values.index]
    .astype(float)
    .rename("resampled")
)
manual_check = pd.concat(
    [manual_values, resampled_values],
    axis=1,
)
manual_check.loc[:, "abs_difference"] = (
    manual_check["manual_from_5m"] - manual_check["resampled"]
).abs()

np.testing.assert_allclose(
    manual_check["manual_from_5m"].to_numpy(dtype=float),
    manual_check["resampled"].to_numpy(dtype=float),
    rtol=1e-12,
    atol=1e-12,
)
print("手工校验日期 =", sample_date.date(), "；bar 数 =", len(sample_minutes))
manual_check.round(6)
"""
        ),
        md(
            """
## 失败示例：把平均每根 bar 成交量误当成日成交量

`mean(volume)` 本身不是数学错误，它表示“平均每根 5 分钟 bar 的成交量”；错误是把这个统计量解释为“全日成交量”。对于每天恰好 48 根的完整样本：

> 日成交量总和 ÷ 平均每根 bar 成交量 = 48

因此日总量必须用 `sum`，而不是一刀切对所有字段调用 `mean`。
"""
        ),
        code(
            r"""
# 对比日成交量总和、平均 bar 成交量和真实 bar 数量。
mean_by_day = bars.resample(
    "1D",
    closed="left",
    label="left",
).mean(numeric_only=True)
bar_count = bars["volume"].resample(
    "1D",
    closed="left",
    label="left",
).count()

volume_comparison = pd.DataFrame(
    {
        "daily_volume_sum": daily_bars["volume"],
        "mean_5m_bar_volume": mean_by_day.loc[daily_bars.index, "volume"],
        "actual_bar_count": bar_count.loc[daily_bars.index],
    }
)
volume_comparison.loc[:, "sum_div_mean"] = (
    volume_comparison["daily_volume_sum"]
    / volume_comparison["mean_5m_bar_volume"]
)

np.testing.assert_allclose(
    volume_comparison["sum_div_mean"],
    volume_comparison["actual_bar_count"],
)
volume_comparison.head(3).round(6)
"""
        ),
        md(
            """
## 课程示例 3：`tz_localize` 与 `tz_convert`

naive Timestamp 只有钟表时间，还没有对应的绝对时刻：

- `tz_localize("Asia/Shanghai")` 按上海地区解释这个钟表时间，从而确定一个绝对时刻；
- `tz_convert("America/New_York")` 保持 UTC 时刻不变，只改变当地显示。

纽约结果显示为前一天不是错误。对于有夏令时切换的地区，本地化还要根据数据语义处理 `ambiguous` 和 `nonexistent` 时刻。
"""
        ),
        code(
            r"""
# 把上海当地钟表时间确定为一个时刻，再转换到纽约和 UTC 显示。
naive = pd.Timestamp("2025-03-03 09:35:00")
shanghai = naive.tz_localize("Asia/Shanghai")
new_york = shanghai.tz_convert("America/New_York")

assert shanghai.tz_convert("UTC") == new_york.tz_convert("UTC")
timezone_demo = pd.Series(
    {
        "naive（无绝对时刻）": str(naive),
        "localized_shanghai": str(shanghai),
        "converted_new_york": str(new_york),
        "same_instant_utc": str(shanghai.tz_convert("UTC")),
    },
    name="value",
)
timezone_demo.to_frame()
"""
        ),
        md(
            """
## 工作日偏移不等于交易日历

`BDay` 只编码周一到周五，不知道交易所休市、临时停市或补班规则。下面声明一个纯教学休市日 `2025-03-04`：

- 普通 `BDay(1)` 仍返回 3 月 4 日；
- `CustomBusinessDay` 收到这张休市表后跳到 3 月 5 日。

`CustomBusinessDay` 也只和传入的日历一样可靠；生产研究应使用版本化、可追溯的官方交易所日历。
"""
        ),
        code(
            r"""
# 用显式声明的教学休市日，对比普通工作日和自定义业务日。
from pandas.tseries.offsets import BDay, CustomBusinessDay

calendar_start = pd.Timestamp("2025-03-03")
declared_closure = pd.Timestamp("2025-03-04")
plain_bday_result = calendar_start + BDay(1)
custom_bday_result = calendar_start + CustomBusinessDay(
    holidays=[declared_closure]
)

assert plain_bday_result == pd.Timestamp("2025-03-04")
assert custom_bday_result == pd.Timestamp("2025-03-05")
pd.Series(
    {
        "起始日": calendar_start.date(),
        "声明休市日": declared_closure.date(),
        "普通 BDay(1)": plain_bday_result.date(),
        "CustomBusinessDay(1)": custom_bday_result.date(),
    },
    name="date",
).to_frame()
"""
        ),
        md(
            """
## 可视化日成交量

把日成交量除以 `1_000_000` 后，以“百万模拟单位”为纵轴，避免图中出现难读的大整数。横轴使用交易日字符串，因此 10 个交易日等距排列，周末不会按两个自然日的宽度留空。

柱顶数值用于准确读取，图形用于比较相对高低；输出保存到 `outputs/35_daily_volume.png`。
"""
        ),
        code(
            r"""
# 用百万模拟单位绘制带数值标注的日成交量柱状图。
daily_volume_million = daily_bars["volume"] / 1_000_000
fig, ax = plt.subplots(figsize=(9, 4.8))
bar_artists = ax.bar(
    daily_bars.index.strftime("%m-%d"),
    daily_volume_million,
    color="#4C78A8",
)
ax.set_title("合成 5 分钟行情聚合后的日成交量")
ax.set_xlabel("交易日")
ax.set_ylabel("成交量（百万模拟单位）")
ax.tick_params(axis="x", rotation=45)
ax.grid(axis="y", alpha=0.25)
ax.set_ylim(0, daily_volume_million.max() * 1.18)
ax.bar_label(
    bar_artists,
    fmt="%.2f",
    padding=3,
    fontsize=8,
)
fig.tight_layout()
chart_path = OUTPUT_DIR / "35_daily_volume.png"
fig.savefig(
    chart_path,
    dpi=160,
    bbox_inches="tight",
)
print("图表已保存：", chart_path)
plt.show()
"""
        ),
        md(
            """
## 方法边界

- 时间戳必须声明代表 bar 起点、终点还是撮合时刻；错误约定会造成整段信号错位。
- `first/last` 只对已经按时间排序的数据有正确语义。
- 多标的数据必须先按 `symbol` 分组；联合键 `(timestamp, symbol)` 应唯一。
- 重采样前要检测缺 bar、重复 bar、半日交易和零成交量，不能只依赖固定的 48 根断言。
- 自然日重采样只适用于此处白天交易样例；期货夜盘、加密资产和跨时区资产需要显式交易日映射。
- OHLCV 只保留桶内摘要，无法恢复真实成交顺序。
- VWAP 使用总成交额/总成交量；简单平均分钟价格不是 VWAP，模拟 bar 成交额也不等同于逐笔成交数据。
- `BDay` 不是交易所日历；任何自定义休市表都必须记录来源和版本。
"""
        ),
        md(
            """
## 可复用结论与练习

**可复用结论**

1. 先展示原始时间文本，再决定解析、localize 或 convert，不能猜测来源时区。
2. 重采样规则由字段语义决定：OHLC、成交量和成交额不能使用同一个聚合函数。
3. 聚合结果应选一天回到原始 bar 手工复核，而不是只看代码能运行。
4. 自然日、工作日和交易日是三种不同概念。

**练习**

- 删除 `2025-03-03` 的一根 5 分钟 bar，先用 bar count 检测异常，再观察 OHLCV 哪些字段会变化。
- 把首日数据重采样为 30 分钟桶，显式设置 `closed` 和 `label`，手工校验第一个桶。
- 为两个模拟标的复制同一时间索引，先按 `symbol` 分组再重采样，并验证不会把两只股票成交量混在一起。
"""
        ),
    ]
    write_notebook(NOTEBOOKS / "35_时间索引与OHLCV重采样.ipynb", cells)


def build_lesson_36():
    cells = [
        md(
            source_note(
                36,
                "滚动窗口、指数加权与回撤",
                "36_youtube-Tn_M5INHO0Q",
            )
        ),
        md(
            """
## 本节量化问题

本课输入一只虚构股票的日频**复权收盘价**，依次回答四个问题：

1. 最近若干个观测的均值和离散程度如何变化；
2. 固定观测窗口、累计窗口和指数衰减权重有何区别；
3. 如何从简单收益率构造净值、历史峰值和回撤；
4. 为什么指标只使用历史数据，仍不代表交易收益没有未来信息。

输出包括带日期标签的 SMA、布林带、EMA、净值和回撤，以及一期延迟与错误同 bar 计算的对照。每个较难 API 先用确定性小序列得到可手工核对的结果，再应用到模拟行情。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 先看原始长表

原始 CSV 是长表：同一交易日有多只虚构股票，每行是一只股票的一天记录。先按日期和股票排序展示，确认字段和数据形态，再筛选单一标的。
"""
        ),
        code(
            r"""
# 读取并展示原始长表；按日期排序后可直接看到同一天的多只股票。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
print("原始表形状：", daily.shape)
print("原始列：", daily.columns.tolist())
display_columns = ["date", "symbol", "sector", "adj_close", "volume"]
daily.sort_values(["date", "symbol"]).loc[:, display_columns].head(12)
"""
        ),
        md(
            """
## 筛选 `TECH_A` 的复权收盘价

`daily["symbol"].eq("TECH_A")` 产生逐行布尔条件；`.loc[行条件, 列标签]` 同时选择行和列。随后把 `date` 设为索引并按日期排序，得到一维 `Series`。

这里保留名称 `adj_close`，避免把复权收盘价误写成未复权的普通 `close`。
"""
        ),
        code(
            r"""
# 从长表筛选 TECH_A，并构造成“日期 → 复权收盘价”的带标签序列。
tech_rows = daily.loc[
    daily["symbol"].eq("TECH_A"),
    ["date", "symbol", "adj_close"],
].copy()

adj_close = (
    tech_rows
    .set_index("date")["adj_close"]
    .sort_index()
    .rename("adj_close")
)
assert adj_close.index.is_monotonic_increasing
assert adj_close.index.is_unique
assert adj_close.gt(0).all()
print("TECH_A 记录数：", len(adj_close))
print("日期范围：", adj_close.index.min().date(), "→", adj_close.index.max().date())
adj_close.head().to_frame()
"""
        ),
        md(
            """
## 从价格计算简单收益率

`pct_change(fill_method=None)` 按时间索引向下计算

```text
当日简单收益率 = 当日复权收盘价 / 前一日复权收盘价 - 1
```

第一日没有前一日价格，因此收益率为 `NaN`。`fill_method=None` 明确禁止 Pandas 先用旧价格填补缺失值；真实行情中的其他缺失收益不能随意当作 0。
"""
        ),
        code(
            r"""
# 计算相邻交易日的简单收益率，并保留日期标签。
returns = adj_close.pct_change(fill_method=None).rename("simple_return")
assert pd.isna(returns.iloc[0])
assert returns.iloc[1:].notna().all()

pd.concat(
    [adj_close, returns],
    axis=1,
).head()
"""
        ),
        md(
            """
## 课程示例 1：先用小序列理解 `rolling` 与 `min_periods`

`rolling(window=3)` 在每个位置取“包含当前位置在内的最近 3 个观测”，不是 3 个自然日。

- `min_periods=3`：必须凑满 3 个有效观测才输出；
- `min_periods=2`：有 2 个有效观测即可提前输出；
- `.mean()`：沿时间方向对每个窗口求均值。
"""
        ),
        code(
            r"""
# 用 5 个确定值核对滚动窗口，不依赖模拟行情。
rolling_demo = pd.Series(
    [10.0, 11.0, 13.0, 12.0, 14.0],
    index=["D1", "D2", "D3", "D4", "D5"],
    name="price",
)
rolling_demo_table = pd.DataFrame({
    "price": rolling_demo,
    "ma3_full": rolling_demo.rolling(window=3, min_periods=3).mean(),
    "ma3_min2": rolling_demo.rolling(window=3, min_periods=2).mean(),
})

assert np.isclose(rolling_demo_table.loc["D3", "ma3_full"], (10 + 11 + 13) / 3)
assert np.isclose(rolling_demo_table.loc["D5", "ma3_full"], (13 + 12 + 14) / 3)
rolling_demo_table.round(4)
"""
        ),
        md(
            """
### 回到真实序列：20 个观测的简单移动平均

`window=20` 表示最近 20 条价格记录；对本课的完整工作日样例，通常近似 20 个交易日，但它不是 20 个自然日。`min_periods=20` 要求完整窗口，`min_periods=5` 则用于观察提前输出的差异。
"""
        ),
        code(
            r"""
# 对复权收盘价分别计算完整窗口和允许提前输出的 SMA20。
ma20 = adj_close.rolling(window=20, min_periods=20).mean().rename("sma20")
ma20_early = adj_close.rolling(window=20, min_periods=5).mean().rename("sma20_min5")

assert ma20.iloc[:19].isna().all()
assert ma20_early.iloc[:4].isna().all()
assert np.isclose(ma20.iloc[19], adj_close.iloc[:20].mean())
print("SMA20 首个有效日期：", ma20.first_valid_index().date())
pd.concat(
    [adj_close, ma20, ma20_early],
    axis=1,
).head(22).round(4)
"""
        ),
        md(
            """
## 课程示例 2：布林带不是固定 95% 概率区间

这里使用价格水平的 20 观测样本标准差：

```text
中轨 = SMA20
上轨 = SMA20 + 2 × 20 期样本标准差
下轨 = SMA20 - 2 × 20 期样本标准差
```

`std(ddof=1)` 使用分母 `n-1`；`2 * rolling_std` 是标量广播，随后按相同日期逐点相加或相减。布林带是描述历史价格位置的技术指标，不是均值的统计置信区间，也不能保证未来价格有 95% 概率落在带内。
"""
        ),
        code(
            r"""
# 计算布林带，并把每个中间量放进带日期标签的表格。
rolling_std = (
    adj_close
    .rolling(window=20, min_periods=20)
    .std(ddof=1)
    .rename("std20")
)
upper = ma20 + 2 * rolling_std
lower = ma20 - 2 * rolling_std
band_table = pd.DataFrame({
    "adj_close": adj_close,
    "sma20": ma20,
    "std20": rolling_std,
    "lower": lower,
    "upper": upper,
})
band_table["inside"] = adj_close.between(lower, upper)
valid_band_table = band_table.dropna(subset=["sma20", "std20"])
coverage = valid_band_table["inside"].mean()

assert valid_band_table.index[0] == ma20.first_valid_index()
print(f"本样本完整窗口内的历史带内比例：{coverage:.1%}")
valid_band_table.head(3).round(4)
"""
        ),
        md(
            """
## 课程示例 3：先用确定性收益理解净值、峰值与回撤

`cumprod()` 沿时间方向逐期复合收益；`expanding(min_periods=1).max()` 从序列起点到当前位置寻找历史最高净值，与这里的 `cummax()` 等价。

```text
回撤 = 当前净值 / 截至当前的历史峰值 - 1
```

回撤序列为 0 或负数。下面第 2 期从 `1.10` 下跌到 `0.88`，所以回撤恰好是 `-20%`。
"""
        ),
        code(
            r"""
# 用确定性收益路径核对逐期复合、历史峰值和回撤。
drawdown_demo_return = pd.Series(
    [0.00, 0.10, -0.20, 0.05],
    index=["起点", "第1期", "第2期", "第3期"],
    name="return",
)
drawdown_demo_nav = (1 + drawdown_demo_return).cumprod()
drawdown_demo_peak = drawdown_demo_nav.expanding(min_periods=1).max()
drawdown_demo = pd.DataFrame({
    "return": drawdown_demo_return,
    "nav": drawdown_demo_nav,
    "running_peak": drawdown_demo_peak,
    "drawdown": drawdown_demo_nav / drawdown_demo_peak - 1,
})

assert np.isclose(drawdown_demo.loc["第2期", "drawdown"], -0.20)
drawdown_demo.round(4)
"""
        ),
        md(
            """
### 回到真实序列：归一化净值和最大回撤

本课价格没有中间缺失，只有收益率首项因为无前值而缺失。将这一个起点收益设为 0，可让净值从 `1.0` 开始；真实行情的其他缺失值不能照此处理。
"""
        ),
        code(
            r"""
# 从 1.0 起步构造净值，并输出最大回撤发生日的完整诊断。
normalized_returns = returns.copy()
normalized_returns.iloc[0] = 0.0
nav = (1 + normalized_returns).cumprod().rename("nav")
running_peak = nav.expanding(min_periods=1).max()
drawdown = (nav / running_peak - 1).rename("drawdown")
max_drawdown = drawdown.min()
worst_date = drawdown.idxmin()

np.testing.assert_allclose(nav, adj_close / adj_close.iloc[0], rtol=1e-12)
assert (drawdown <= 1e-12).all()
print("最大回撤日期：", worst_date.date())
print(f"最大回撤（负值）：{max_drawdown:.2%}")
print(f"最大回撤幅度：{-max_drawdown:.2%}")
pd.DataFrame({
    "nav": nav,
    "running_peak": running_peak,
    "drawdown": drawdown,
}).loc[[worst_date]].round(6)
"""
        ),
        md(
            """
## 课程示例 4：EWM 是指数衰减，不是固定窗口

`ewm(span=3, adjust=False).mean()` 使用递推公式：

```text
EMA_t = α × x_t + (1 - α) × EMA_(t-1)
α = 2 / (span + 1)
```

`span=3` 时 `α=0.5`。较早观测的权重不断指数衰减，但不会像 rolling 一样在固定边界外突然归零。`min_periods` 只控制至少有多少个观测后才显示结果，不会把 EWM 截断成固定窗口。
"""
        ),
        code(
            r"""
# 用价格跳变观察 SMA3 与 span=3 的 EMA 如何响应新信息。
shock = pd.Series(
    [100.0, 100.0, 100.0, 110.0, 110.0],
    index=["D1", "D2", "D3", "D4", "D5"],
    name="price",
)
ewm_demo = pd.DataFrame({
    "price": shock,
    "sma3": shock.rolling(window=3, min_periods=1).mean(),
    "ema_span3": shock.ewm(span=3, adjust=False).mean(),
})

assert np.isclose(ewm_demo.loc["D4", "sma3"], 103.3333333333)
assert np.isclose(ewm_demo.loc["D4", "ema_span3"], 105.0)
ewm_demo.round(4)
"""
        ),
        md(
            """
### 回到真实序列：SMA20 与 EMA20

本样本中可比较价格到两条平滑线的平均绝对距离；这个数值只描述当前模拟路径，不能证明 EMA 在所有市场中都更好或更有预测力。
"""
        ),
        code(
            r"""
# 对真实序列计算 EMA20，并用带日期标签的末尾数据核对。
ema20 = (
    adj_close
    .ewm(span=20, adjust=False, min_periods=20)
    .mean()
    .rename("ema20")
)
distance_sma = (adj_close - ma20).abs().mean()
distance_ema = (adj_close - ema20).abs().mean()

print(f"本样本价格到 SMA20 的平均绝对距离：{distance_sma:.3f}")
print(f"本样本价格到 EMA20 的平均绝对距离：{distance_ema:.3f}")
pd.concat(
    [adj_close, ma20, ema20],
    axis=1,
).tail(5).round(4)
"""
        ),
        md(
            """
## 指标无未来，不代表交易收益无未来

当日简单收益率对应“前一收盘到当日收盘”的价格变化。当日收盘后才知道 `adj_close > SMA20` 是否成立，因此不能再用这个信号解释已经发生的当日收益。

下面把收盘信号 `shift(1)` 后作用于下一条收益，作为**一期延迟的教学对照**。它只消除最明显的同 bar 泄漏，不等于真实成交模型：若信号依赖官方收盘价，真实交易通常还要使用下一可成交价格并重新定义收益区间。
"""
        ),
        code(
            r"""
# 构造一期延迟持仓，并展示首次信号附近的日期对齐。
signal_at_close = adj_close.gt(ma20).astype("int8").rename("signal_at_close")
position_one_bar_later = (
    signal_at_close
    .shift(1, fill_value=0)
    .astype("int8")
    .rename("position_one_bar_later")
)
strategy_return = (position_one_bar_later * returns).rename("one_bar_lag_return")
same_bar_return = (signal_at_close * returns).rename("wrong_same_bar_return")

first_signal_date = signal_at_close[signal_at_close.eq(1)].index[0]
first_signal_position = adj_close.index.get_loc(first_signal_date)
timeline = pd.concat(
    [
        adj_close,
        ma20,
        returns,
        signal_at_close,
        position_one_bar_later,
        strategy_return,
    ],
    axis=1,
)
timeline.iloc[
    max(0, first_signal_position - 2): first_signal_position + 3
].round(6)
"""
        ),
        md(
            """
### 汇总一期延迟与错误同 bar 结果

两条路径使用同一信号，差别只在信号作用的收益期间。巨大差异用于暴露时间错位，不应被解释成策略有效性。
"""
        ),
        code(
            r"""
# 逐期复合两种收益，并把结果格式化为百分比。
comparison = pd.Series({
    "教学对照_一期延迟": (1 + strategy_return.dropna()).prod() - 1,
    "错误_同bar收益": (1 + same_bar_return.dropna()).prod() - 1,
}, name="cumulative_return").to_frame()
comparison.style.format("{:.2%}")
"""
        ),
        code(
            r"""
# 同时绘制价格指标与回撤；图中的收益和价格均来自合成数据。
from matplotlib.ticker import PercentFormatter

fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
axes[0].plot(adj_close, label="复权收盘价", linewidth=1)
axes[0].plot(ma20, label="SMA20")
axes[0].plot(upper, label="上轨", alpha=0.6)
axes[0].plot(lower, label="下轨", alpha=0.6)
axes[0].fill_between(adj_close.index, lower, upper, alpha=0.08)
axes[0].legend()
axes[0].set_title("滚动均线与布林带（合成数据）")
axes[0].set_ylabel("复权价格")
axes[1].fill_between(drawdown.index, drawdown, 0, color="tab:red", alpha=0.45)
axes[1].set_title(f"回撤，MDD={max_drawdown:.1%}")
axes[1].set_ylabel("回撤")
axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
fig.tight_layout()
fig.savefig(OUTPUT_DIR / "36_rolling_and_drawdown.png", dpi=140)
plt.show()
"""
        ),
        md(
            """
## 方法边界

- `rolling(window=20)` 统计最近 20 个观测，不保证等于 20 个自然日。
- `ewm(span=20)` 是指数衰减，不是只保留 20 个观测的硬窗口；`min_periods` 只是输出门槛。
- 均线是平滑后的历史，不会自动产生预测力。
- `center=True` 会把未来值放入当前窗口，不可直接用于历史信号。
- `shift(1)` 只是一期延迟教学；真实执行需明确下单时点、可成交价格、滑点、涨跌停和停牌。
- 布林带的两倍标准差只是惯例，金融价格和收益不满足固定正态假设。
- 本课只把收益率首项设为 0 以建立净值起点；真实行情的中间缺失值不能直接填 0。
- 最大回撤依赖完整路径；它不同于波动率，也不能由期末收益单独推断。
"""
        ),
        md(
            """
## 可复用结论与练习

可复用计算顺序是：

```text
复权价格 → 简单收益率 → 滚动/指数指标
         → 从 1.0 起步的净值 → 历史峰值 → 回撤
         → 信号生成时间 → 延迟后的持仓 → 对应收益期间
```

练习：

1. 把小序列的 `window=3` 改为 `window=2`，先手算再核对输出。
2. 比较 `ewm(span=3, adjust=False)` 与 `adjust=True`，说明前几项为何不同。
3. 使用下一交易日的 `open` 构造更明确的执行收益，比较它与一期 close-to-close 教学结果。
4. 找出最大回撤的峰值日期、谷底日期和修复日期；若样本末尾尚未修复，应明确标记。
"""
        ),
    ]
    write_notebook(NOTEBOOKS / "36_滚动窗口与回撤.ipynb", cells)


def build_lab_1():
    cells = [
        md(
            """
# L1｜收益矩阵与组合风险综合实验

本实验连接第 31–36 课：

```text
环境清单
  → Pandas 标签化行情
  → NumPy 收益矩阵
  → 按时间切分训练期和测试期
  → 训练期协方差与最小方差权重
  → 测试期固定目标权重组合收益
  → rolling 风险、净值和回撤
```

输入是 `日期 × 股票` 的复权收盘价和简单收益率；输出是训练期权重、测试期逐日组合收益、从 `1.0` 起步的净值、回撤和滚动年化波动率。目标不是寻找最赚钱组合，而是建立可复现、避免使用测试期估计权重的最小研究流程。

> **组合口径**：测试期每个收益期间都应用相同目标权重，这在数学上是固定权重 constant-mix 组合，隐含逐期再平衡且暂不计交易成本。它不是“一次买入固定股数后一直持有”。

> **数据声明**：本实验使用固定随机种子生成的 6 只虚构股票行情，不是真实证券数据。图表和指标只用于验证研究流程，不能用于判断真实市场或策略收益。
"""
        ),
        code(COMMON_SETUP),
        md(
            """
## 1. 先看原始长表

CSV 中每行是一只虚构股票的一天记录。按日期和股票排序后展示两天数据，可直接看到同一日期对应多只股票，而不是立即把原始结构隐藏在宽表中。
"""
        ),
        code(
            r"""
# 读取并展示原始长表。
daily = pd.read_csv(DATA_DIR / "daily_prices.csv", parse_dates=["date"])
print("原始表形状：", daily.shape)
print("原始列：", daily.columns.tolist())
display_columns = ["date", "symbol", "sector", "adj_close", "volume"]
daily.sort_values(["date", "symbol"]).loc[:, display_columns].head(12)
"""
        ),
        md(
            """
### 数据契约与质量检查

研究代码至少要验证列契约、`日期 + 股票` 唯一性、缺失值和价格正值。断言负责阻止错误继续传播，带标签检查表负责让读者看到验证了什么。
"""
        ),
        code(
            r"""
# 把关键质量检查汇总成可见结果，再用断言阻止不合格数据继续运行。
required_columns = ["date", "symbol", "adj_close", "volume", "sector"]
quality_check = pd.Series({
    "必需列齐全": set(required_columns).issubset(daily.columns),
    "日期_股票重复行数": int(daily.duplicated(["date", "symbol"]).sum()),
    "必需字段缺失数": int(daily[required_columns].isna().sum().sum()),
    "非正复权价格数": int(daily["adj_close"].le(0).sum()),
}, name="result")

assert bool(quality_check["必需列齐全"])
assert quality_check["日期_股票重复行数"] == 0
assert quality_check["必需字段缺失数"] == 0
assert quality_check["非正复权价格数"] == 0
quality_check.to_frame()
"""
        ),
        md(
            """
### 长表重排为价格矩阵

`pivot(index="date", columns="symbol", values="adj_close")` 将长表重排为：

- 行：交易日期；
- 列：股票；
- 单元格：复权收盘价。

`pivot` 遇到重复的 `date + symbol` 会报错，不会像 `pivot_table` 那样默认聚合。矩阵进入 NumPy 前，Pandas 标签是防止股票顺序错位的第一道保护。
"""
        ),
        code(
            r"""
# 将长表重排为“日期 × 股票”的复权收盘价矩阵。
close = (
    daily
    .pivot(index="date", columns="symbol", values="adj_close")
    .sort_index()
)

assert close.index.is_monotonic_increasing
assert close.index.is_unique and close.columns.is_unique
assert not close.isna().any().any()
print("价格矩阵 shape：", close.shape, "含义：日期 × 股票")
close.head()
"""
        ),
        md(
            """
### 从价格矩阵计算简单收益率矩阵

`pct_change(fill_method=None)` 对每只股票列分别计算相邻交易日的简单收益率。首个价格日没有前值，因此只明确去掉第一行 `.iloc[1:]`。

本合成宽表没有中间缺失值；真实多资产数据若使用 `.dropna(axis=0, how="any")`，会删除任一股票缺失的整天，属于完整样本选择，必须记录其影响。
"""
        ),
        code(
            r"""
# 按股票列计算简单收益率；结果仍是“日期 × 股票”。
returns_with_first_nan = close.pct_change(fill_method=None)
returns = returns_with_first_nan.iloc[1:]

assert returns.shape == (len(close) - 1, close.shape[1])
assert returns.notna().all().all()
print("收益矩阵 shape：", returns.shape, "含义：日期 × 股票")
returns.head().style.format("{:.3%}")
"""
        ),
        md(
            """
## 2. 训练期估计、测试期验证

`iloc[:split]` 和 `iloc[split:]` 沿日期方向按位置切分，不随机打乱。这里前 60% 收益观测为训练期，后 40% 为测试期；训练期结束日必须早于测试期开始日。
"""
        ),
        code(
            r"""
# 沿时间顺序切分，并显示两段样本的观测数和日期边界。
split = int(len(returns) * 0.6)
train = returns.iloc[:split]
test = returns.iloc[split:]
assert train.index.max() < test.index.min()

split_summary = pd.DataFrame({
    "observations": [len(train), len(test)],
    "start": [train.index.min().date(), test.index.min().date()],
    "end": [train.index.max().date(), test.index.max().date()],
}, index=["train", "test"])
split_summary
"""
        ),
        md(
            """
### 训练期年化协方差

`train.cov()` 默认沿日期方向，用每两只股票的训练期简单收益率计算样本协方差，得到 `(股票, 股票)` 矩阵。乘以 `252` 是日频风险常用的年化约定：

```text
年化协方差 ≈ 日协方差 × 252
```

它依赖收益分布与时间稳定性假设。乘以正数 `252` 不会改变最小方差权重，只改变目标函数和风险的单位。
"""
        ),
        code(
            r"""
# 计算保留股票标签的训练期年化协方差和单资产年化波动率。
annual_cov_labeled = train.cov() * 252
asset_annual_vol = pd.Series(
    np.sqrt(np.diag(annual_cov_labeled)),
    index=train.columns,
    name="annualized_vol",
)

assert annual_cov_labeled.shape == (train.shape[1], train.shape[1])
print("年化协方差 shape：", annual_cov_labeled.shape, "含义：股票 × 股票")
display(annual_cov_labeled.round(4))
asset_annual_vol.to_frame().style.format("{:.2%}")
"""
        ),
        md(
            """
### 先用二资产小例子理解 `w @ Σ @ w`

权重 `w` 的 shape 为 `(N,)`，协方差 `Σ` 的 shape 为 `(N, N)`：

```text
(N,) @ (N, N) @ (N,) → 标量组合方差
```

组合波动率是方差的平方根。下面两资产无相关性，第二项波动更低，因此最小方差权重会更多配置第二项。
"""
        ),
        code(
            r"""
# 用确定性二资产协方差核对组合方差和波动率。
demo_cov = np.array([
    [0.04, 0.00],
    [0.00, 0.01],
])
demo_weights = pd.DataFrame(
    {
        "equal": [0.50, 0.50],
        "minvar": [0.20, 0.80],
    },
    index=["资产A", "资产B"],
)
demo_risk = pd.DataFrame({
    "variance": {
        column: float(demo_weights[column].to_numpy() @ demo_cov @ demo_weights[column].to_numpy())
        for column in demo_weights
    }
})
demo_risk["volatility"] = np.sqrt(demo_risk["variance"])

assert np.isclose(demo_risk.loc["equal", "variance"], 0.0125)
assert np.isclose(demo_risk.loc["minvar", "variance"], 0.0080)
demo_risk.style.format({"variance": "{:.4f}", "volatility": "{:.2%}"})
"""
        ),
        md(
            """
### 用 SLSQP 求训练期 long-only 最小方差权重

优化目标是年化组合方差 `w @ Σ @ w`。约束含义：

- `bounds=[(0, 1)] * N`：每只股票权重在 0 到 100% 之间，禁止做空；
- `sum(w) - 1 = 0`：权重总和为 1，资金全部投入；
- `x0=equal_weights`：以等权组合为数值搜索起点；
- `method="SLSQP"`：处理边界和等式约束的数值优化方法。

该问题没有预期收益目标，因此“最小方差”不等于“最高收益”。
"""
        ),
        code(
            r"""
# 仅使用训练期协方差求解最小方差权重。
from scipy.optimize import minimize

annual_cov = annual_cov_labeled.to_numpy(dtype=np.float64)
n_assets = train.shape[1]
equal_weights = np.full(n_assets, 1 / n_assets)

def portfolio_variance(weight_vector, covariance):
    return float(weight_vector @ covariance @ weight_vector)

result = minimize(
    fun=portfolio_variance,
    x0=equal_weights,
    args=(annual_cov,),
    method="SLSQP",
    bounds=[(0.0, 1.0)] * n_assets,
    constraints={"type": "eq", "fun": lambda w: w.sum() - 1},
)
assert result.success, result.message
minvar_weights = result.x
assert np.isclose(minvar_weights.sum(), 1)
assert (minvar_weights >= -1e-10).all()

weight_matrix = pd.DataFrame(
    {
        "等权": equal_weights,
        "训练期最小方差": minvar_weights,
    },
    index=train.columns,
)
weight_matrix.index.name = "symbol"

print("优化状态：", result.message)
print("迭代次数：", result.nit)
weight_matrix.style.format("{:.2%}")
"""
        ),
        md(
            """
### 检查训练期目标风险

最小方差权重应在训练期协方差口径下不高于等权组合风险。这个断言验证优化目标，但不保证测试期收益、波动或回撤一定更好。
"""
        ),
        code(
            r"""
# 比较两个组合在训练期协方差下的方差和年化波动率。
training_risk = pd.DataFrame({
    "variance": {
        "等权": portfolio_variance(equal_weights, annual_cov),
        "训练期最小方差": portfolio_variance(minvar_weights, annual_cov),
    }
})
training_risk["annual_vol"] = np.sqrt(training_risk["variance"])

assert training_risk.loc["训练期最小方差", "variance"] <= training_risk.loc["等权", "variance"] + 1e-12
training_risk.style.format({"variance": "{:.6f}", "annual_vol": "{:.2%}"})
"""
        ),
        md(
            """
权重只使用训练期数据估计，测试期不重新估计。随后每个测试期收益都乘同一组目标权重，数学上隐含每期再平衡回目标比例且成本为 0。

这与“一次买入后固定股数”不同：买入持有组合的权重会随各资产价格涨跌而漂移。真正滚动研究还应在每个再估计日只使用当时可得窗口，并明确再平衡频率和成本。
"""
        ),
        md(
            """
## 3. 测试期组合收益：先保留标签，再用 NumPy 校验

`test` 的 shape 是 `(T, N)`：日期 × 股票；`weight_matrix` 的 shape 是 `(N, K)`：股票 × 组合。

```text
(T, N) @ (N, K) → (T, K)
```

`DataFrame.dot` 会按股票标签检查和对齐；NumPy `@` 只按位置运算。因此先用 Pandas 得到安全结果，再显式断言列顺序，并用 NumPy 独立校验。
"""
        ),
        code(
            r"""
# 用标签安全的矩阵乘法计算两个组合的测试期逐日收益。
assert test.columns.equals(weight_matrix.index)
portfolio_returns = test.dot(weight_matrix)

test_array = test.to_numpy(dtype=np.float64)
weight_array = weight_matrix.to_numpy(dtype=np.float64)
portfolio_returns_np = test_array @ weight_array
np.testing.assert_allclose(
    portfolio_returns.to_numpy(),
    portfolio_returns_np,
)

print(
    "shape：",
    "test", test.shape,
    "@ weights", weight_matrix.shape,
    "=", portfolio_returns.shape,
)
portfolio_returns.head().style.format("{:.3%}")
"""
        ),
        md(
            """
### 用首个测试日核对每只股票的收益贡献

逐元素乘法保留每只股票的贡献；沿股票行求和后，等于矩阵乘法得到的当日组合收益。贡献表同时展示资产收益、权重和两个组合的贡献，避免只看到最终标量。
"""
        ),
        code(
            r"""
# 拆解首个测试日的逐股票贡献，并用合计校验组合收益。
first_test_date = test.index[0]
first_day_return = test.loc[first_test_date]
first_day_contribution = pd.DataFrame({
    "asset_return": first_day_return,
    "equal_weight": weight_matrix["等权"],
    "equal_contribution": first_day_return * weight_matrix["等权"],
    "minvar_weight": weight_matrix["训练期最小方差"],
    "minvar_contribution": first_day_return * weight_matrix["训练期最小方差"],
})

np.testing.assert_allclose(
    [
        first_day_contribution["equal_contribution"].sum(),
        first_day_contribution["minvar_contribution"].sum(),
    ],
    portfolio_returns.loc[first_test_date],
)
print("首个测试日：", first_test_date.date())
first_day_contribution.style.format("{:.3%}")
"""
        ),
        md(
            """
## 4. 从 `1.0` 起步构造净值与回撤

`cumprod(axis=0)` 沿日期方向对每个组合分别复合收益。测试期首个收益发生前的资本是 `1.0`，因此先在训练期最后日期加入净值起点，再计算历史峰值和回撤：

```text
净值 = (1 + 每期收益) 的累计乘积
历史峰值 = 截至当前的累计最大净值
回撤 = 当前净值 / 历史峰值 - 1
```
"""
        ),
        code(
            r"""
# 在第一个测试收益发生前加入 1.0 起点，再计算净值、峰值和回撤。
initial_nav = pd.DataFrame(
    [np.ones(portfolio_returns.shape[1])],
    index=pd.DatetimeIndex(
        [train.index[-1]],
        name=portfolio_returns.index.name,
    ),
    columns=portfolio_returns.columns,
)
nav = pd.concat([
    initial_nav,
    (1 + portfolio_returns).cumprod(axis=0),
])
running_peak = nav.cummax(axis=0)
drawdown = nav / running_peak - 1

assert np.allclose(nav.iloc[0], 1.0)
assert (drawdown <= 1e-12).all().all()
drawdown_diagnostics = pd.DataFrame({
    "max_drawdown": drawdown.min(),
    "worst_date": drawdown.idxmin(),
})

display(nav.head(3).round(6))
drawdown_diagnostics.style.format({"max_drawdown": "{:.2%}"})
"""
        ),
        md(
            """
### 60 观测滚动年化波动率

`rolling(window=60, min_periods=60)` 对每个组合列分别取最近 60 个收益观测；它不是 60 个自然日。`std(ddof=1)` 计算窗口样本标准差，乘 `sqrt(252)` 按日频惯例年化。

它是历史实现波动率估计，不是未来风险保证。
"""
        ),
        code(
            r"""
# 对每个组合分别计算 60 观测滚动年化波动率。
rolling_vol = (
    portfolio_returns
    .rolling(window=60, min_periods=60)
    .std(ddof=1)
    * np.sqrt(252)
)

assert rolling_vol.iloc[:59].isna().all().all()
print("首个完整 60 观测窗口日期：", rolling_vol.dropna().index[0].date())
rolling_vol.dropna().head().style.format("{:.2%}")
"""
        ),
        md(
            """
### 测试期指标汇总

- 几何年化收益：用测试期末净值和测试收益观测数按 252 期年化；
- 年化样本波动率：测试期日收益样本标准差乘 `sqrt(252)`；
- 最大回撤：包含 `1.0` 起点的回撤序列最小值。

三者描述不同性质，最小方差组合不保证收益最高，也不保证最大回撤最浅。
"""
        ),
        code(
            r"""
# 汇总测试期几何年化收益、年化样本波动率和最大回撤。
summary = pd.DataFrame({
    "annualized_geometric_return": nav.iloc[-1] ** (252 / len(portfolio_returns)) - 1,
    "annualized_sample_vol": portfolio_returns.std(axis=0, ddof=1) * np.sqrt(252),
    "max_drawdown": drawdown.min(),
})

display(summary.style.format("{:.2%}"))
print("解读：请比较波动率、收益和最大回撤；三项排序不必一致。")
"""
        ),
        md(
            """
## 5. 矢量化结果与显式循环一致

性能比较前必须先验证正确性。循环函数显式检查输入 shape，避免 `zip` 在权重长度错误时静默截断：

- 收益矩阵：`(T, N)`；
- 单组合权重：`(N,)`；
- 输出：`(T,)`。
"""
        ),
        code(
            r"""
# 用显式循环复算最小方差组合，并展示前 5 日逐项一致。
def loop_portfolio(matrix, weight_vector):
    matrix = np.asarray(matrix)
    weight_vector = np.asarray(weight_vector)
    assert matrix.ndim == 2
    assert weight_vector.shape == (matrix.shape[1],)

    output = np.empty(matrix.shape[0], dtype=np.float64)
    for row_index, row in enumerate(matrix):
        total = 0.0
        for column_index, value in enumerate(row):
            total += value * weight_vector[column_index]
        output[row_index] = total
    return output

loop_result = loop_portfolio(test_array, minvar_weights)
vector_result = test_array @ minvar_weights
np.testing.assert_allclose(loop_result, vector_result)

print("校验通过：循环与矩阵乘法结果一致。")
pd.DataFrame({
    "loop": loop_result[:5],
    "matrix_multiplication": vector_result[:5],
}, index=test.index[:5]).round(8)
"""
        ),
        md(
            """
### 只在结果一致后比较性能

`np.tile(test_array, (300, 1))` 只沿日期方向重复同一测试矩阵以放大计时差异；它没有产生新市场信息，不能当作扩充回测样本。循环和矩阵乘法使用相同的 `number` 与 `repeat` 设置，倍数只代表本机本次运行。
"""
        ),
        code(
            r"""
# 重复同一矩阵做本机性能实验，不把重复数据解释成新样本。
large = np.tile(test_array, (300, 1))
repeat_count = 3
print("性能测试 shape：", test_array.shape, "→", large.shape)

loop_time = min(timeit.repeat(
    lambda: loop_portfolio(large, minvar_weights),
    number=1,
    repeat=repeat_count,
))
vector_time = min(timeit.repeat(
    lambda: large @ minvar_weights,
    number=1,
    repeat=repeat_count,
))
print(f"循环：{loop_time:.4f}s")
print(f"矩阵乘法：{vector_time:.4f}s")
print(f"本机加速倍数：{loop_time / vector_time:.1f}x")
"""
        ),
        md(
            """
## 6. 图形诊断

三张图分别回答：测试期资本如何复合、组合曾从历史峰值下跌多少、最近 60 个收益观测的历史波动率是多少。净值高低不能代替回撤或波动率诊断。
"""
        ),
        code(
            r"""
# 绘制带明确单位的测试期净值、回撤和滚动波动率。
from matplotlib.ticker import PercentFormatter

fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
nav.plot(ax=axes[0], title="样本外净值（合成数据）")
drawdown.plot(ax=axes[1], title="样本外回撤")
rolling_vol.plot(ax=axes[2], title="60 日滚动年化波动率")
axes[0].set_ylabel("净值")
axes[0].axhline(1.0, color="black", linewidth=0.8, alpha=0.5)
axes[1].set_ylabel("回撤")
axes[1].yaxis.set_major_formatter(PercentFormatter(1.0))
axes[2].set_ylabel("年化波动率")
axes[2].yaxis.set_major_formatter(PercentFormatter(1.0))
axes[2].set_xlabel("日期")
for axis in axes:
    axis.grid(alpha=0.2)
fig.tight_layout()
fig.savefig(
    OUTPUT_DIR / "L1_portfolio_risk.png",
    dpi=160,
    bbox_inches="tight",
)
plt.show()
"""
        ),
        md(
            """
### 如何解读本次确定性合成样本

先看汇总表确认哪个组合的测试期波动率较低，再分别检查年化收益和最大回撤。训练期最小方差只优化训练期协方差口径；即使测试期波动较低，也不推出测试期收益更高或最大回撤更小。
"""
        ),
        md(
            """
## 7. 验收与方法边界

- 输入价格以日期和证券标签唯一对齐。
- 收益矩阵为 `日期 × 股票`，权重为 `股票`。
- `to_numpy()` 会移除股票标签，数值运算前必须断言列顺序。
- 权重只在训练期估计，测试期不使用未来样本重新估计。
- 长仓最小方差权重有总和与上下界约束。
- 测试期每期使用同一目标权重，隐含逐期再平衡和零交易成本；它不是固定股数买入持有。
- 若一次买入后不再平衡，应计算各资产财富腿和随价格漂移的权重，不能每天直接使用初始权重做 `R @ w`。
- 日频协方差乘 252 和波动率乘 `sqrt(252)` 是年化约定，不是稳定分布保证。
- 训练期样本协方差存在估计误差、共线性和结构漂移；最小方差权重可能集中且不稳定。
- 完整行缺失删除会改变共同样本；真实数据必须记录上市、停牌和缺失处理。
- 循环和矩阵乘法结果一致，性能倍数由本机实测。
- 尚未加入手续费、滑点、停牌、涨跌停、可成交价格、复权事件和权重漂移，因此本实验不是完整回测。
- 测试期只是同一确定性合成过程的时间后段，不能代表真实市场的实盘外推。
"""
        ),
        md(
            """
## 8. 可复用结论与练习

可复用研究顺序：

```text
原始长表 → 数据契约 → 日期 × 股票价格
          → 简单收益率 → 时间切分
          → 训练期协方差 → 受约束权重
          → 标签安全的样本外组合收益
          → 1.0 起点净值 → 峰值/回撤/滚动风险
```

练习：

1. 打乱 `weight_matrix` 的股票索引，比较 Pandas `dot` 与未检查列顺序的 NumPy `@`。
2. 把训练比例改为 50% 和 70%，记录权重、训练风险和测试风险如何变化。
3. 将固定目标权重组合改为一次买入后的固定股数持有，比较权重漂移和净值。
4. 加入每次再平衡的双边成本，并比较日度、月度再平衡。
5. 给单只股票引入若干缺失日，分别测试完整行删除、停牌零收益假设和可投资股票池变化；说明每种处理的业务含义。
"""
        ),
    ]
    write_notebook(LABS / "L1_收益矩阵与组合风险.ipynb", cells)


def main():
    daily = build_daily_fixture()
    intraday = build_intraday_fixture()
    build_metadata([daily, intraday])
    build_lesson_31()
    build_lesson_32()
    build_lesson_33()
    build_lesson_34()
    build_lesson_35()
    build_lesson_36()
    build_lab_1()


if __name__ == "__main__":
    main()
