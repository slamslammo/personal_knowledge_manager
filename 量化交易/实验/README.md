# 量化交易实验

本目录存放量化交易板块的可运行实验。实验从课程复现开始，逐步扩展到包含数据快照、交易成本、样本外验证和风险约束的研究闭环。

## 当前课程实验

- [365 天量化金融统一课程入口](../../../pam-video-captures/365-days-quant-finance/knowledge-map.html)：第 31–60 课的图文口播、逐课代码与模块综合实验都放在课程大纲的对应位置；当前第 31–42 课以及 L1、L2 已完成。
- [P2 Python 量化工具栈维护说明](p2-python-toolchain/README.md)：记录 Notebook、静态报告、数据与执行验收文件，不再单独提供课程浏览首页。
- [P2 课程辅助设计](p2-python-toolchain/课程辅助设计.md)：记录稳定结构、环境、数据、验收和迭代规则，后续批次以此为准。
- [第一批执行验收](p2-python-toolchain/notebook-validation.md)：记录逐本干净内核执行结果。

## 目录约定

```text
实验/
├── data/       # 数据来源、字段、下载和快照说明
├── p2-python-toolchain/ # 第31–60课逐课 Notebook、综合实验与辅助设计
├── notebooks/  # 可交互学习与分析
├── scripts/    # 可重复执行的数据处理和实验生成脚本
├── outputs/    # 由代码生成的图片与表格
└── reports/    # Notebook 导出的静态 HTML 报告
```

## 环境

```bash
cd 量化交易
conda env create -f environment.yml
conda activate pkm-quant
jupyter lab
```

当前计划使用 Python 3.11、NumPy、pandas、Matplotlib、seaborn、scikit-learn、yfinance 与 AkShare。yfinance 固定为 1.5.1，避免旧版的限流误判与 Cookie 处理问题。首次创建环境后，应记录实际版本和数据接口兼容性。

当前 `pkm-quant` 已在 macOS ARM64 + Miniforge 上创建并验证。若环境已经存在，使用以下命令同步依赖：

```bash
conda env update -n pkm-quant -f environment.yml --prune
conda activate pkm-quant
python -m ipykernel install --user --name pkm-quant --display-name "Python (pkm-quant)"
python 实验/scripts/check_environment.py
```

启动 JupyterLab 后，Notebook 内核选择 `Python (pkm-quant)`。行情接口属于外部服务：2026-07-14 升级到 yfinance 1.5.1 后，当前网络的 AAPL 单次验证仍收到 HTTP 429。遇到 `YFRateLimitError` 时不要反复请求，可稍后只重试一次，或改用课程提供的 AkShare 路线并明确记录数据源。

## 第一轮实验路线

1. 运行 `scripts/task2_theory_origins.py`，验证随机游走、方差时间缩放、凯利仓位和过度下注。
2. 获取一只标的的 OHLCV 数据，检查字段、索引、缺失和复权口径。
3. 计算简单收益率和对数收益率，验证净值连乘关系。
4. 构造 MA5/MA20 信号，区分信号、成交动作和实际仓位。
5. 建立最小回测，使用前一日信号计算当日策略收益。
6. 加入买入持有与市场基准，并计算收益、波动率、Sharpe 和最大回撤。
7. 加入手续费、滑点和换手率，观察策略结果变化。
8. 比较多标的相关性、等权组合和单标的风险。
9. 划分样本内与样本外区间，检查参数选择是否过拟合。

## 实验规范

每个实验应包含：研究问题、数据来源与时间区间、关键假设、代码、结果、观察、结论、限制和对应知识节点。公开仓库不提交来源不清或许可不明的大型行情文件。
