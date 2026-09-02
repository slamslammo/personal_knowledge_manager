# P2 Python 量化工具栈

本目录把「365 天量化金融」第 31–60 课整理为可重复运行的学习实验；当前已完成 30 个逐课 Notebook 和 L1–L6 六个综合实验。

## 组织方式

- 每节课程一个 Notebook，与课程编号、视频和图文口播一一对应。
- 每个模块增加一个综合实验，把逐课 API 串成量化研究任务。
- 视频、口播和截图仍保留在课程采集目录；本目录只保存学习代码、离线样例数据、输出和设计记录。

P2 课程只保留一个浏览器入口：

[打开 PAM「365 天量化金融」知识地图](../../../../pam-video-captures/365-days-quant-finance/knowledge-map.html)。

知识地图在课程大纲内提供逐课图文与代码实践链接，并在对应模块提供 L1–L6 综合实验入口。本目录不再生成或维护独立 `index.html`；下表仅作为文件清单和维护索引。

## 当前模块

- **环境与数值计算（31–33、L1）**：研究环境与可复现性、NumPy 收益矩阵、组合风险和 PCA。
- **时间序列处理（34–39、L2）**：标签与时间对齐、OHLCV 重采样、滚动统计、行业面板、缺失值与可交易状态、财报 point-in-time 合并；L2 将清洗、估值/成交分离、行业截面和数据质量审计串成一条流程。
- **数据与可视化（40–46、L3）**：Matplotlib/Plotly/mplfinance、yfinance/AkShare 离线适配、SQLite 幂等存储与可追溯流水线。
- **统计与模型（47–50、L4）**：技术指标、厚尾诊断、因子回归、防泄漏的时间序列机器学习。
- **工程与性能（51–58、L5）**：装饰器、受控并发、线程/进程边界、Numba、调试、pytest、Git 与 Docker 配置审计。
- **自动化交付（59–60、L6）**：本地月报生成、哈希清单和 P2 工具链完成度审计。

| 类型 | 课程 | Notebook（Jupyter） | HTML（浏览器） | 状态 |
|---|---|---|---|---|
| 逐课 | 31 环境与可复现研究 | [打开](notebooks/31_环境与可复现研究.ipynb) | [阅读](reports/31_环境与可复现研究.html) | 执行通过 |
| 逐课 | 32 NumPy 广播与收益矩阵 | [打开](notebooks/32_NumPy广播与收益矩阵.ipynb) | [阅读](reports/32_NumPy广播与收益矩阵.html) | 执行通过 |
| 逐课 | 33 矩阵运算、组合风险与 PCA | [打开](notebooks/33_NumPy矩阵运算与PCA.ipynb) | [阅读](reports/33_NumPy矩阵运算与PCA.html) | 执行通过 |
| 逐课 | 34 Pandas 标签对齐与行情表 | [打开](notebooks/34_Pandas标签与行情表.ipynb) | [阅读](reports/34_Pandas标签与行情表.html) | 执行通过 |
| 逐课 | 35 时间索引、时区与 OHLCV 重采样 | [打开](notebooks/35_时间索引与OHLCV重采样.ipynb) | [阅读](reports/35_时间索引与OHLCV重采样.html) | 执行通过 |
| 逐课 | 36 Rolling、EWM、回撤与未来信息 | [打开](notebooks/36_滚动窗口与回撤.ipynb) | [阅读](reports/36_滚动窗口与回撤.html) | 执行通过 |
| 逐课 | 37 MultiIndex、分组与行业中性化 | [打开](notebooks/37_MultiIndex分组与行业中性化.ipynb) | [阅读](reports/37_MultiIndex分组与行业中性化.html) | 执行通过 |
| 逐课 | 38 缺失值、估值与可交易性 | [打开](notebooks/38_缺失值处理与可交易性.ipynb) | [阅读](reports/38_缺失值处理与可交易性.html) | 执行通过 |
| 逐课 | 39 财报行情合并与时点一致性 | [打开](notebooks/39_财报行情合并与时点一致性.ipynb) | [阅读](reports/39_财报行情合并与时点一致性.html) | 执行通过 |
| 逐课 | 40 同一结果表驱动策略可视化 | [打开](notebooks/40_同一结果表驱动策略可视化.ipynb) | [阅读](reports/40_同一结果表驱动策略可视化.html) | 执行通过 |
| 逐课 | 41 Plotly 交互 K 线 | [打开](notebooks/41_Plotly交互K线.ipynb) | [阅读](reports/41_Plotly交互K线.html) | 执行通过 |
| 逐课 | 42 mplfinance 复盘图 | [打开](notebooks/42_mplfinance复盘图.ipynb) | [阅读](reports/42_mplfinance复盘图.html) | 执行通过 |
| 逐课 | 43 yfinance 数据适配与复权口径 | [打开](notebooks/43_yfinance数据适配与复权口径.ipynb) | [阅读](reports/43_yfinance数据适配与复权口径.html) | 执行通过 |
| 逐课 | 44 AkShare 数据契约与时点 | [打开](notebooks/44_AkShare数据契约与时点.ipynb) | [阅读](reports/44_AkShare数据契约与时点.html) | 执行通过 |
| 逐课 | 45 SQLite 行情库与幂等增量 | [打开](notebooks/45_SQLite行情库与幂等增量.ipynb) | [阅读](reports/45_SQLite行情库与幂等增量.html) | 执行通过 |
| 逐课 | 46 可复现量化数据流水线 | [打开](notebooks/46_可复现量化数据流水线.ipynb) | [阅读](reports/46_可复现量化数据流水线.html) | 执行通过 |
| 逐课 | 47 技术指标公式与可执行时点 | [打开](notebooks/47_技术指标公式与可执行时点.ipynb) | [阅读](reports/47_技术指标公式与可执行时点.html) | 执行通过 |
| 逐课 | 48 SciPy 厚尾收益与极端风险 | [打开](notebooks/48_SciPy厚尾收益与极端风险.ipynb) | [阅读](reports/48_SciPy厚尾收益与极端风险.html) | 执行通过 |
| 逐课 | 49 statsmodels 因子回归与稳健推断 | [打开](notebooks/49_statsmodels因子回归与稳健推断.ipynb) | [阅读](reports/49_statsmodels因子回归与稳健推断.html) | 执行通过 |
| 逐课 | 50 sklearn 防泄漏时序分类 | [打开](notebooks/50_sklearn防泄漏时序分类.ipynb) | [阅读](reports/50_sklearn防泄漏时序分类.html) | 执行通过 |
| 逐课 | 51 装饰器、重试、缓存与资源边界 | [打开](notebooks/51_装饰器重试缓存与资源边界.ipynb) | [阅读](reports/51_装饰器重试缓存与资源边界.html) | 执行通过 |
| 逐课 | 52 asyncio 受控并发数据获取 | [打开](notebooks/52_asyncio受控并发数据获取.ipynb) | [阅读](reports/52_asyncio受控并发数据获取.html) | 执行通过 |
| 逐课 | 53 线程、进程与回测并行边界 | [打开](notebooks/53_线程进程与回测并行边界.ipynb) | [阅读](reports/53_线程进程与回测并行边界.html) | 执行通过 |
| 逐课 | 54 Numba 数值循环加速与验算 | [打开](notebooks/54_Numba数值循环加速与验算.ipynb) | [阅读](reports/54_Numba数值循环加速与验算.html) | 执行通过 |
| 逐课 | 55 回测调试与未来函数审计 | [打开](notebooks/55_回测调试与未来函数审计.ipynb) | [阅读](reports/55_回测调试与未来函数审计.html) | 执行通过 |
| 逐课 | 56 pytest 量化单元测试 | [打开](notebooks/56_pytest量化单元测试.ipynb) | [阅读](reports/56_pytest量化单元测试.html) | 执行通过 |
| 逐课 | 57 Git 实验版本与结果追踪 | [打开](notebooks/57_Git实验版本与结果追踪.ipynb) | [阅读](reports/57_Git实验版本与结果追踪.html) | 执行通过 |
| 逐课 | 58 Docker 可复现研究环境设计 | [打开](notebooks/58_Docker可复现研究环境设计.ipynb) | [阅读](reports/58_Docker可复现研究环境设计.html) | 执行通过 |
| 逐课 | 59 自动月报流水线与幂等交付 | [打开](notebooks/59_自动月报流水线与幂等交付.ipynb) | [阅读](reports/59_自动月报流水线与幂等交付.html) | 执行通过 |
| 逐课 | 60 P2 工具链总结与完成度审计 | [打开](notebooks/60_P2工具链总结与完成度审计.ipynb) | [阅读](reports/60_P2工具链总结与完成度审计.html) | 执行通过 |
| 综合 | L1 收益矩阵与组合风险 | [打开](labs/L1_收益矩阵与组合风险.ipynb) | [阅读](reports/L1_收益矩阵与组合风险.html) | 执行通过 |
| 综合 | L2 行情清洗与时间对齐 | [打开](labs/L2_行情清洗与时间对齐.ipynb) | [阅读](reports/L2_行情清洗与时间对齐.html) | 执行通过 |
| 综合 | L3 数据获取、存储与报告 | [打开](labs/L3_数据获取存储与报告.ipynb) | [阅读](reports/L3_数据获取存储与报告.html) | 执行通过 |
| 综合 | L4 防泄漏统计建模 | [打开](labs/L4_防泄漏统计建模.ipynb) | [阅读](reports/L4_防泄漏统计建模.html) | 执行通过 |
| 综合 | L5 可测试的量化计算模块 | [打开](labs/L5_可测试的量化计算模块.ipynb) | [阅读](reports/L5_可测试的量化计算模块.html) | 执行通过 |
| 综合 | L6 一键生成月报 | [打开](labs/L6_一键生成月报.ipynb) | [阅读](reports/L6_一键生成月报.html) | 执行通过 |

## 运行

```bash
conda activate pkm-quant
cd "/Users/mojiawen/Documents/personal_knowledge_manager/量化交易/实验/p2-python-toolchain"
jupyter lab
```

Notebook 选择 `Python (pkm-quant)` 内核。当前 Notebook 默认读取 `data/fixtures/` 中的离线合成行情，并在课内构造必要的小样例、缺失状态和财报发布时间，不会重复请求 yfinance 或 AkShare。

第 31–40 课使用 NumPy、pandas、SciPy、Matplotlib 等依赖；第 41–42 课在同一环境中增加：

- `plotly`：生成交互式 K 线、均线和成交量图，并导出包含 Plotly JavaScript 的离线 HTML；
- `mplfinance`：按标准 OHLCV 数据契约生成静态 K 线、指标和信号复盘图。

第 43–60 课继续使用同一环境，并补充：

- `statsmodels`：因子回归与 HAC/Newey–West 稳健推断；
- `numba`：数值循环 JIT，明确区分首次编译与预热性能；
- `pytest`：实际执行量化单元测试；
- `Jinja2`：本地 HTML 月报模板。

不另建课程专用环境。Plotly 的自包含 HTML 文件较大是离线交互能力的结果；本阶段不引入需要 Kaleido 的 `write_image` 链路。

`.ipynb` 是供 Jupyter 读取的结构化文件，普通浏览器可能显示 JSON；直接阅读请使用 `reports/` 中的 HTML。

批量验收：

```bash
conda activate pkm-quant
python tools/validate_notebooks.py
```

当前验收结果见 [notebook-validation.md](notebook-validation.md)：2026-07-29 使用 `pkm-quant` 从干净内核执行，36/36 个 Notebook、304/304 个代码单元通过。后续以该脚本重新生成的报告为准，不手工维护执行计数。

## 关键边界

- 样例行情是固定随机种子生成的教学数据，不代表真实证券历史表现；第 38 课的缺口与停牌例子、第 39 课的行业和财报表也都是为说明方法而构造的模拟数据。
- 所有实时接口只负责刷新数据快照，Notebook 默认不依赖网络。
- 填补后的估值价格不等于可成交价格；财报必须按 `available_at` 而不是报告期末做 point-in-time 对齐。
- K 线的开高低收必须使用兼容的频率、时区和复权口径；图中的金叉/死叉是信号发现日，不等同于下单日或成交日。
- Notebook 能运行、图表能生成都不等于策略有效；未来信息、复权、交易成本、可交易约束和样本外验证仍需单独检查。
- 第 31–60 课与 L1–L6 统一沿用第 32 课形成的教学规范：先展示输入与目标，再解释方法、参数、shape/axis 和关键运算符，用可手算的确定性小例子核对语义，最后回到完整模拟行情并明确金融边界。

设计决策见 [课程辅助设计.md](课程辅助设计.md)，阶段变化见 [迭代记录.md](迭代记录.md)。后续批次继续先更新这两份文档，再沿用同一模板扩展。
