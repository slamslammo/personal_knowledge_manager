# AI 资讯任务

本目录是生成 `AI资讯/` 内容的定时任务工程：方案、配置、提示词、脚本与版本记录都在这里，任务的执行规则不依赖平台设置或聊天记录。

## 文件

| 文件 | 内容 |
| --- | --- |
| [方案.md](方案.md) | 板块规划、内容规则、数据源、GitHub 榜单算法、运行架构、存储与迁移设计 |
| [版本规划.md](版本规划.md) | 版本路线、当前状态、迭代记录 |
| [部署指南.md](部署指南.md) | 在 Claude Code 云端或其他平台部署的步骤与上线检查 |
| [config/task.yaml](config/task.yaml) | 部署清单：定时、能力、网络、写入路径 |
| [config/sources.yaml](config/sources.yaml) | 信息源与数据接口 |
| [config/ranking.yaml](config/ranking.yaml) | 各榜单的规则参数 |
| [prompts/routine-prompt.md](prompts/routine-prompt.md) | 当前贴在定时任务中的提示词（过渡版 v0.0） |

## 快速部署

1. 按 [部署指南.md](部署指南.md) 第 2 节配置环境网络和 GitHub 授权。
2. 新建或编辑定时任务：每周一 10:00（GMT+8），挂载本仓库，提示词复制 `prompts/routine-prompt.md` 全文。
3. 手动触发一次，按部署指南 2.4 的清单检查。

## 维护约定

- 修改规则时，先改 `方案.md`，再同步提示词和配置，并在 `版本规划.md` 记录原因。
- 定时任务运行时只读本目录，不会修改这里的文件。
- 本目录的改动走 PR；周报等产出由定时任务直接提交到 `main`。
