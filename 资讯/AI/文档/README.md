# AI 周报开发与维护

每期汇总上一周的 AI 资讯、写入 GitHub，再同步飞书并通知。日常维护从这里开始，按改动范围查对应文件。

## 周报怎么跑

| 阶段 | 从哪里看 |
| --- | --- |
| 准备和协调 | [weekly.md](../工程/prompts/weekly.md) 串起运行步骤。[deployment.py](../工程/scripts/deployment.py) 判定模式和恢复入口，[coord.py](../工程/scripts/coord.py) 负责运行资格、锁、发布和运行状态。 |
| 采集、排名和草稿 | [collect_all.py](../工程/scripts/collect_all.py) 调度采集，[rank_github.py](../工程/scripts/rank_github.py) 算榜单，[draft.py](../工程/scripts/draft.py) 按[模板](../工程/templates/weekly.md)生成草稿。模型核实来源、选题、分析和写作。 |
| 检查、发布和交付 | [finalize.py](../工程/scripts/finalize.py) 更新数据说明，[validate.py](../工程/scripts/validate.py) 检查内容，[check_run.py](../工程/scripts/check_run.py) 检查运行证据。Git 发布成功后，[feishu_sync.py](../工程/scripts/feishu_sync.py) 同步发布稿并处理通知。 |

## 本地上手

准备 Git 和 Python 3.10 或以上，建议使用虚拟环境。在仓库根目录运行下面的命令，可查看工作目录并完成离线测试。测试包含可移植性检查，开发测试无需飞书凭据。

```bash
python3 -m pip install -r 资讯/AI/工程/requirements.txt
python3 资讯/AI/工程/scripts/workdir.py print
python3 -m unittest discover -s 资讯/AI/工程/scripts/tests -t 资讯/AI/工程/scripts/tests
```

工作目录默认在检出目录的同级 `.ai-weekly/work`，以查询结果为准。草稿和本次输出在那里，已发布的周报、榜单和运行记录在 [数据目录](../数据/)。改目录和文件命名看 [paths.py](../工程/scripts/paths.py)，改清理和归档看 [workdir.py](../工程/scripts/workdir.py)，相关回归在 [test_runtime_paths.py](../工程/scripts/tests/test_runtime_paths.py)。

## 从改动到合并

- 从最新 `main` 建分支。已确认规则下的缺陷和文档小修直接走 PR，写清问题、改动和验证。改变内容口径、数据源、脚本接口、产出或发布行为时，先写短方案，说明影响和验收方式，由维护者确认取舍后实现。需要在 PR 里讨论未定方案时，可以用草稿 PR。[提案模板](提案/模板.md)
- 先用相关测试复现，再改脚本和回归用例。规则改动同步对应规格和配置。评审核对最终差异、同类路径和测试结果，开发和评审按当次分工安排。
- 工程目录或 CI 工作流有改动时，核对最终 PR 提交的 [CI](../../../.github/workflows/ai-weekly-tests.yml) 结果。纯文档改动未命中路径过滤时，核对链接、命令和 `git diff --check`，记录 CI 未触发。
- 工程、配置和文档由维护者合并 PR 或授权合并。当期报告、榜单和运行状态按运行授权由 `coord.py` 发布。人工修复状态文件也走 PR，写明原因。正式触发、排程和平台切换由维护者决定。

## 验收与排错

- **改榜单。** 先确认是修实现还是改口径。查规格、榜单配置和 `rank_github.py`，运行 `python3 资讯/AI/工程/scripts/tests/test_rank.py` 验证排序和边界。[榜单规格](方案.md#63-github-热度榜算法) · [榜单配置](../工程/config/ranking.yaml)
- **Git 已发布，飞书未同步。** 从已发布提交补交付或只读核对。修交付脚本时，用 `test_feishu_sync.py` 复现失败和重试，再按需做沙箱验收。[补交付](部署指南.md#补交付) · [飞书测试](../工程/scripts/tests/test_feishu_sync.py)
- **验证发布链路。** CI 运行离线测试。合并后，下次正常运行读取最新 `main`。涉及运行行为的改动按需演练，测试参数按执行手册传入。正式交付分别查 Git 提交、飞书正文读回、通知 API 结果和实际收件。[验收与切换](部署指南.md#验收与切换)

内容标准查 [周报规格](方案.md)，参数查 [工程配置](../工程/config/)，安装和授权查 [部署指南](部署指南.md)。固定入口提示词负责引导、授权、安全和失败通知，流程改在仓库手册里。调整入口的授权或安全规则时，单独列出差异供维护者确认。[固定入口](../工程/prompts/routine-prompt.md)

未完成事项查 [版本规划](版本规划.md)，历史取舍和证据查 [提案](提案/README.md)。
