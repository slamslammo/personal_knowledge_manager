# AI 资讯任务

本目录是生成 `AI资讯/` 内容的定时任务工程：方案、配置、提示词、脚本与版本记录都放在这里，任务的执行规则以仓库文件为准，不依赖聊天记录。

## 文件

| 文件 | 内容 | 状态 |
| --- | --- | --- |
| [方案.md](方案.md) | 板块规划、内容规则、数据源、GitHub 榜单算法、运行架构、存储与迁移设计 | 已完成 |
| [版本规划.md](版本规划.md) | 版本路线、当前状态、迭代记录 | 持续更新 |
| [部署指南.md](部署指南.md) | 验收、各平台（Claude Code 云端、Codex、自建调度）的部署步骤、跨平台验收与上线检查 | 已完成 |
| [config/task.yaml](config/task.yaml) | 部署清单：定时、能力、网络、写入路径 | 已完成 |
| [config/runtime.yaml](config/runtime.yaml) | 运行上限：重试、搜索次数、返工轮数、协调锁的租约与等待 | v0.8 |
| [config/sources.yaml](config/sources.yaml) | 信息源与数据接口 | 已完成 |
| [config/ranking.yaml](config/ranking.yaml) | 各榜单的规则参数 | 已完成 |
| [config/topics.yaml](config/topics.yaml) | 元数据 topics 受控词表与机构名写法 | 已完成 |
| [prompts/routine-prompt.md](prompts/routine-prompt.md) | 入口提示词：贴进定时任务，含安全规则与失败通知 | 已完成 |
| [prompts/weekly.md](prompts/weekly.md) | 周报执行手册：协调、采集、写作、检查、提交、通知、校验流程、失败处理 | v0.8 |
| [templates/weekly.md](templates/weekly.md) | 周报模板（`draft.py` 据此生成草稿） | 已上线 |
| [scripts/](scripts/) | 协调锁、采集、原文读取、排名、草稿、校验与质量门槛、独立校验、执行记录、可移植性检查，以及测试 | v0.8 |
| `prompts/monthly.md`、`quarterly.md` 及模板 | 月报、季报执行手册 | v0.2 计划 |

## 脚本

在仓库根目录运行，只依赖 Python 标准库和 PyYAML。中间文件默认写到 `/tmp/ai-weekly/`（可用环境变量 `AI_WEEKLY_TMP` 修改）。

按执行手册的顺序（产出写在 `/tmp/ai-weekly/out/` 下，由 `coord.py` 提交）：

```bash
S=AI资讯/任务/scripts
python3 $S/weeks.py --week 2026-W43 > /tmp/ai-weekly/week.json   # 报告周、路径、月报季报到期判定
python3 $S/coord.py start --platform claude --test               # 协调锁：决定运行、校验、等待或退出
python3 $S/collect_all.py                                         # 全部采集，产出 digest.md、materials.json
python3 $S/rank_github.py --week 2026-W43                        # 需要先写 /tmp/ai-weekly/judgments.json
python3 $S/tracelog.py search "② 核实" "查询词"                    # 每次联网搜索都记录
python3 $S/draft.py                                               # 生成周报草稿；--degraded 生成降级版
python3 $S/finalize.py                                            # 刷新数据说明的事实部分
python3 $S/check_run.py                                           # 完整性检查与质量门槛
python3 $S/coord.py publish                                       # 提交推送
python3 $S/verify.py --record                                     # 独立校验另一次运行的产出
python3 $S/trace_view.py --week 2026-W43                          # 还原整周的执行过程
python3 $S/check_portability.py                                   # 可移植性检查
python3 -m unittest discover -s $S/tests -t $S/tests
```

## 快速部署

1. 在开发会话里按 [部署指南.md](部署指南.md) 第 3 节用测试模式跑一遍，确认产出。
2. 按部署指南第 4 节配置目标平台：定时每周一 10:00（GMT+8；第二个平台晚 1 小时以上），命令可以联网，有推送本仓库 `main` 的凭证，模型选高档、思考强度最高，提示词复制 `prompts/routine-prompt.md` 全文。
3. 新平台先按部署指南 4.4 做跨平台验收，再按 4.5 手动触发一次正式运行做上线检查。

## 维护约定

- 修改规则时，先改 `方案.md`，再同步执行手册、模板、脚本和配置，并在 `版本规划.md` 记录原因。
- 改脚本要同步改测试，提交前运行单元测试。
- 入口提示词 `prompts/routine-prompt.md` 只放引导、授权、安全边界和失败通知，尽量不改；流程、格式、平台细节都改在仓库里。执行手册、脚本和配置合并到 `main` 后下一次运行即生效，不用重新粘贴。
- 执行文件（prompts、templates、config、scripts）保持平台无关，平台相关的做法只写在 `部署指南.md` 第 4 节；`check_portability.py` 随单元测试检查这一点。
- 定时任务的会话只用于运行和诊断，任务工程的改动在开发会话里做。
- 定时任务运行时只读本目录，不会修改这里的文件。
- 本目录的改动走 PR，等审查结束、用户确认后合并；周报、数据和状态文件由定时任务经 `coord.py` 直接推送到 `main`。
