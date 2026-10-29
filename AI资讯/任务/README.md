# AI 资讯任务

本目录是生成 `AI资讯/` 内容的定时任务工程：方案、配置、提示词、脚本与版本记录都放在这里，任务的执行规则以仓库文件为准，不依赖聊天记录。

## 文件

| 文件 | 内容 | 状态 |
| --- | --- | --- |
| [方案.md](方案.md) | 板块规划、内容规则、数据源、GitHub 榜单算法、运行架构、存储与迁移设计 | 已完成 |
| [版本规划.md](版本规划.md) | 版本路线、当前状态、迭代记录 | 持续更新 |
| [部署指南.md](部署指南.md) | 验收、在 Claude Code 云端或其他平台部署的步骤与上线检查 | 已完成 |
| [config/task.yaml](config/task.yaml) | 部署清单：定时、能力、网络、写入路径 | 已完成 |
| [config/sources.yaml](config/sources.yaml) | 信息源与数据接口 | 已完成 |
| [config/ranking.yaml](config/ranking.yaml) | 各榜单的规则参数 | 已完成 |
| [config/topics.yaml](config/topics.yaml) | 元数据 topics 受控词表与机构名写法 | 已完成 |
| [prompts/routine-prompt.md](prompts/routine-prompt.md) | 入口提示词：贴进定时任务，含安全规则与失败通知 | 已完成 |
| [prompts/weekly.md](prompts/weekly.md) | 周报执行手册 | v0.1 验收中 |
| [templates/weekly.md](templates/weekly.md) | 周报模板 | v0.1 验收中 |
| [scripts/](scripts/) | 日期计算、采集、排名、校验脚本与测试 | v0.1 验收中 |
| `prompts/monthly.md`、`quarterly.md` 及模板 | 月报、季报执行手册 | v0.2 计划 |

## 脚本

在仓库根目录运行，只依赖 Python 标准库和 PyYAML。中间文件默认写到 `/tmp/ai-weekly/`（可用环境变量 `AI_WEEKLY_TMP` 修改）。

```bash
S=AI资讯/任务/scripts
python3 $S/weeks.py --week 2026-W43             # 报告周、路径、月报季报到期判定
python3 $S/collect_trendshift.py --week 2026-W43
python3 $S/collect_hn.py --week 2026-W43
python3 $S/collect_hf.py --week 2026-W43
python3 $S/rank_github.py --week 2026-W43       # 需要先写 /tmp/ai-weekly/judgments.json
python3 $S/validate.py --week 2026-W43 [--backfill]
python3 $S/check_run.py --week 2026-W43       # 运行完整性检查：各步是否在本次运行中做完
python3 -m unittest discover -s $S/tests -t $S/tests
```

## 快速部署

1. 在开发会话里按 [部署指南.md](部署指南.md) 第 2 节用测试模式跑一遍，确认产出。
2. 按部署指南第 3 节配置环境网络和 GitHub 授权。
3. 新建或编辑定时任务：每周一 10:00（GMT+8），挂载本仓库，提示词复制 `prompts/routine-prompt.md` 全文。
4. 手动触发一次，按部署指南 3.4 的清单检查。

## 维护约定

- 修改规则时，先改 `方案.md`，再同步执行手册、模板、脚本和配置，并在 `版本规划.md` 记录原因。
- 改脚本要同步改测试，提交前运行单元测试。
- 执行手册、脚本和配置合并到 `main` 后下一次运行即生效；只有 `prompts/routine-prompt.md` 变化时才需要重新粘贴到定时任务。
- 定时任务运行时只读本目录，不会修改这里的文件。
- 本目录的改动走 PR；周报等产出由定时任务提交到工作分支，建 PR 后自动合并到 `main`。
