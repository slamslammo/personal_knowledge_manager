# AI 资讯工程

本目录是 AI 资讯任务的运行时文件集合。模式及平台状态见 [部署指南 4.1](../文档/部署指南.md#41-当前配置)。运行会话按固定入口读取执行手册；开发方案与决策见 [文档索引](../文档/README.md)。

## 文件

| 文件 | 内容 |
| --- | --- |
| `prompts/routine-prompt.md` | 入口提示词，贴进定时任务（稳定，不随流程改动） |
| `prompts/weekly.md` | 执行手册，运行时从仓库读取 |
| `prompts/env-bootstrap.md` | 环境就绪门引导到的部署分支 |
| `config/` | 部署清单、运行时上限、信息源、榜单参数、主题词表、飞书配置、部署模式 |
| `templates/weekly.md` | 周报模板，`draft.py` 据此生成草稿 |
| `scripts/` | 协调、采集、排名、草稿、校验、交付、执行记录脚本与 `tests/` |
| `requirements.txt` | 运行依赖（PyYAML） |

`prompts/monthly.md`、`quarterly.md` 及对应模板属 v0.2，尚未编写。

## 运行环境

- Python ≥ 3.10 + PyYAML。平台专属的解释器、身份和网络配置见 [部署指南](../文档/部署指南.md#47-workbuddy-本机主运行者)。
- 在**仓库根目录**运行，只依赖 Python 标准库和 PyYAML。中间文件默认写到 `/tmp/ai-weekly/`（可用 `AI_WEEKLY_TMP` 修改）。
- 本地、CI 与部署环境使用同一份依赖清单：`python3 -m pip install -r 资讯/AI/工程/requirements.txt`。

## 唯一推荐运行链路

按 [weekly.md](prompts/weekly.md) 执行：先判断是否恢复已有验收；新运行再检查核心依赖、读取实际模式、确定报告周，由 `deployment.py start` 决定运行、校验、等待或退出。只有取得运行锁后才采集、写作、检查、发布和交付。不要另拼一套 `coord.py start --test` 流程绕过项目入口。

缺依赖或授权时转 [env-bootstrap.md](prompts/env-bootstrap.md)；已有沙箱只恢复交付，已发布生产稿只补交付或只读核对，均不重跑整周。具体分支和命令只在执行手册维护。

`deployment.py plan` 只报告实际计划，不能替代启动；一次性测试覆盖及跨进程传递按执行手册处理，不改保存入口。

产出写在 `/tmp/ai-weekly/out/` 下与仓库相同的相对路径处，由 `coord.py` 统一提交；运行会话只读工程文件。

开发验证只运行测试与可移植性检查，不触发周报：

```bash
python3 -m unittest discover -s 资讯/AI/工程/scripts/tests -t 资讯/AI/工程/scripts/tests
python3 资讯/AI/工程/scripts/check_portability.py
```

## 维护约定

- 改脚本要同步改测试，提交前运行全部单元测试与 `check_portability.py`。
- 执行文件（prompts、templates、config、scripts）保持**平台无关**：平台专属做法只写在 [../文档/部署指南.md](../文档/部署指南.md) 第 4 节；`check_portability.py` 随单测检查这一点。
- 产出路径统一由 `scripts/paths.py` 生成，不要各脚本各自拼字符串。
- 入口提示词 `prompts/routine-prompt.md` 只放引导、授权、安全边界和失败通知；流程、格式、平台细节都改在仓库里。执行文件合并到 `main` 后下一次运行即生效，不用重新粘贴入口；**只有入口本身改了**才需要同步平台任务配置里的快照。
- 运行会话只读本目录，不会修改这里的文件；工程改动在开发会话走 PR。
