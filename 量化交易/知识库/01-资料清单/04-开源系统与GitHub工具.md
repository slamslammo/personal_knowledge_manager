<!--# opensourcetools -->
# 开源系统与 GitHub 工具

> 本页是[资料清单](node:refs)「开源工具」分类的详情页：记录选型顺序、验收规则和使用边界；资料入口以清单主页的表格为准。工具取数时的来源规范见[数据与财经信息源](node:infosystems)，运行环境统一使用[实验环境](node:env)的 `pkm-quant`。

## 选型顺序

工具按研究阶段选择，不追求一次安装完整量化平台。

```text
pandas 最小回测
      ↓
RQAlpha 对照事件驱动       Qlib 对照因子 / ML 研究流
      ↓                              ↓
交易、组合和数据边界稳定以后再评估完整系统
      ↓
QuantDinger / vn.py / WonderTrader / LEAN / NautilusTrader
```

## 当前优先级

| 优先级 | 项目 | 最适合解决的问题 | 当前判断与边界 |
|---|---|---|---|
| P0 | pandas / NumPy | 把信号、仓位、收益、成本和净值逐行算清楚。 | 当前继续使用；透明度高于过早引入框架。 |
| P1 | [Microsoft Qlib](https://github.com/microsoft/qlib) | 因子表达式、数据集、模型、实验记录、信号分析和回测的研究工作流。 | 因子阶段优先试用；它是研究平台，不等同于券商执行系统，数据复权和 point-in-time 仍需自己审计。 |
| P1 | [RQAlpha](https://github.com/ricequant/rqalpha) | A 股/期货的事件驱动回测、撮合、账户、税费和风险模块。 | 适合与 pandas 最小回测对照；许可证限制非商业使用，不能只看“代码公开”。 |
| P2 | [VectorBT Community](https://github.com/polakowo/vectorbt) | 用 NumPy/Numba/Rust 快速做多参数、多资产和 walk-forward 实验。 | 社区版与 PRO 功能并存，许可证含 Commons Clause；用于研究前先确认功能和许可边界。 |
| P2 | [PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt) | 均值方差、有效前沿、风险模型和组合优化。 | 等相关性、组合和约束实验开始后再引入。 |
| P2 | [QuantStats](https://github.com/ranaroussi/quantstats) | 从收益序列生成绩效指标和报告。 | 作为报告与交叉检查工具，指标定义仍需自己核对。 |

## 完整系统观察清单

| 系统 | 架构定位 | 为什么值得跟踪 | 为什么现在不直接采用 |
|---|---|---|---|
| [QuantDinger](https://github.com/brokermr810/QuantDinger) | 2026 年出现的 Apache-2.0、本地优先 AI Trading OS，覆盖研究、Python 策略、回测、模拟/实盘和监控。 | 形态与本项目“AI + 研究到执行闭环”高度相关，Docker 自托管和审计思路值得研究。 | 项目很新、功能面很宽；A 股实盘链路、数据质量、撮合真实性、严格回测和风险隔离需要独立验收。首次评估只用样例数据和模拟盘，不放真实密钥。 |
| [VeighNa / vn.py](https://github.com/vnpy/vnpy) | Python 事件驱动交易框架，覆盖国内外接口、策略应用和实盘。 | 中文生态成熟，适合以后理解网关、事件总线、订单、账户和实盘运维。 | 系统和接口较重，当前会遮蔽最小回测机制；许多实盘接口还依赖券商、操作系统和账户条件。 |
| [WonderTrader](https://github.com/wondertrader/wondertrader) | C++ 核心 + Python 子框架，覆盖 CTA、截面、高频、执行、风控和调度。 | 国内市场、性能和多策略组合管理设计有参考价值。 | 更接近机构/生产工程；需要额外数据、接口和部署评估，不适合作为当前第一套回测框架。 |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | Apache-2.0 的多资产事件驱动引擎，支持本地 Docker 回测和实盘适配。 | 工程完整，研究、回测和交易模型值得做架构对照。 | 本地引擎开源不代表数据、云服务和所有工作流免费；当前也不是 A 股优先路径。Learning Center 继续观察，不作为主课。 |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | Rust 核心、Python 策略接口的高性能事件驱动回测与交易引擎。 | 回测与实盘共用核心、订单簿/延迟模型和确定性设计值得后期研究。 | 学习和部署复杂度高，当前需求尚未到多场所、低延迟生产系统。 |

QuantDinger 的 [抖音搜索入口](https://www.douyin.com/search/quantdinger?aid=8aa3d5cd-cee3-4530-8a50-36d550e1b99d&modal_id=7634178326050917641&type=general) 只用于发现演示，项目判断以 GitHub 代码、许可证、文档、测试和本地验收为准。

用户提供的 [Bilibili Qlib 平台课程](https://www.bilibili.com/cheese/play/ep2655722?query_from=0&search_id=6176764068262669706&search_query=%E9%87%8F%E5%8C%96&is_PCend=1) 保留为“外部演示、待评估”。它需要登录或付费，不进入免费核心路线；学习 Qlib 首先使用官方仓库、官方文档和示例配置。

## 项目验收模板

任何开源量化系统进入本机环境前，都先回答：

1. 许可证是否允许当前用途，核心模块是否真的开源；
2. 最近发布、提交、Issue 和测试是否显示仍在维护；
3. 数据从哪里来，是否包含退市股票、公司行动和披露时点；
4. 回测是向量化还是事件驱动，成交、费用、滑点和订单生命周期怎样建模；
5. 同一策略能否使用固定数据快照重复运行；
6. 是否能与当前 pandas 基线得到可解释的一致或差异结果；
7. 模拟盘和实盘是否强隔离，密钥、下单、风控和紧急停止是否可审计。

在完成这些检查前，项目状态只标记为“雷达”或“试验”，不因为演示视频、Star 数或 AI 功能直接进入主工具链。
