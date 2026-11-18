# AI 资讯工程

本目录是 AI 资讯定时任务的**运行时执行文件集合**：定时任务按入口提示词读取这里的执行手册，再调用这里的脚本完成采集、校验、提交和交付。开发相关的方案与决策记录见 [../文档/README.md](../文档/README.md)。

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

- Python ≥ 3.10 + PyYAML。本机验证请用 `/opt/homebrew/bin/python3.11`：WorkBuddy 自带的 Python 3.13 未装 PyYAML，Xcode 的 `/usr/bin/python3` 是 3.9，低于项目的语法基线。
- 在**仓库根目录**运行，只依赖 Python 标准库和 PyYAML。中间文件默认写到 `/tmp/ai-weekly/`（可用 `AI_WEEKLY_TMP` 修改）。
- 本地、CI 与部署环境使用同一份依赖清单：`python3 -m pip install -r 资讯/AI/工程/requirements.txt`。

## 脚本顺序

产出写在 `/tmp/ai-weekly/out/` 下与仓库相同的相对路径处，由 `coord.py` 统一提交，运行过程中不改动仓库工作区。

```bash
S=资讯/AI/工程/scripts
python3 $S/weeks.py --week 2026-W43 > /tmp/ai-weekly/week.json   # 报告周、路径、月报季报到期判定
python3 $S/coord.py start --platform workbuddy --test            # 协调锁：决定运行、校验、等待或退出
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

> 验收模式请用 `deployment.py plan/start/finish` 走完整链路，不要手工逐条执行上面的命令；正式运行由执行手册调度。

## 维护约定

- 改脚本要同步改测试，提交前运行全部单元测试与 `check_portability.py`。
- 执行文件（prompts、templates、config、scripts）保持**平台无关**：平台专属做法只写在 [../文档/部署指南.md](../文档/部署指南.md) 第 4 节；`check_portability.py` 随单测检查这一点。
- 产出路径统一由 `scripts/paths.py` 生成，不要各脚本各自拼字符串。
- 入口提示词 `prompts/routine-prompt.md` 只放引导、授权、安全边界和失败通知；流程、格式、平台细节都改在仓库里。执行文件合并到 `main` 后下一次运行即生效，不用重新粘贴入口；**只有入口本身改了**才需要同步平台任务配置里的快照。
- 运行会话只读本目录，不会修改这里的文件；工程改动在开发会话走 PR。
