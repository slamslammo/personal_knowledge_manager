# AI 周报工程

这里是 AI 周报的可执行部分。从采集上周资讯到发布 Git 周报、同步飞书，每次运行都由[执行手册](prompts/weekly.md)串起各阶段。

## 目录

| 位置 | 用途 |
| --- | --- |
| [core/](core/) | 共享工具与周报发布基座：路径、协调发布、校验、飞书交付与环境自检。 |
| [weekly/](weekly/) | 周报专属脚本：采集、排名、草稿、整理与运行检查。 |
| [monthly/](monthly/) · [quarterly/](quarterly/) | 月季报独立入口，准备和发布按同一期间执行。 |
| [tests/](tests/) | 离线回归用例（必须用 `unittest discover` 整体运行）。 |
| [prompts/](prompts/) | 任务入口、环境初始化指引和执行手册。 |
| [config/](config/) · [templates/](templates/) | 信息源、榜单参数、运行配置和周报模板。 |
| [requirements.txt](requirements.txt) | 本地开发和 CI 共用的 Python 依赖。 |

## 一期周报的流程

1. **准备。** [prepare.py](weekly/prepare.py) 交出周编号、摘要和工作目录。它读取运行模式和当周状态，确定本次该生成、校验、等待还是退出。[deployment.py](weekly/deployment.py) · [coord.py](core/coord.py)
2. **成稿。** 脚本采集、排名并生成草稿，模型核实来源、选题和写作。[采集](weekly/collect_all.py) · [排名](weekly/rank_github.py) · [草稿](weekly/draft.py)
3. **检查与交付。** [deliver.py](weekly/deliver.py) 接收写好的周报和通知摘要，逐项报告 Git、飞书、通知与归档结果。它整理数据说明，校验正文和本次运行记录，经 `coord.py` 发布到 Git，再同步飞书并通知。[整理](weekly/finalize.py) · [内容校验](core/validate.py) · [运行检查](weekly/check_run.py) · [飞书交付](core/feishu_sync.py)

## 本地开发

准备 Git 和 Python 3.10 或以上，在仓库根目录用自己的 Python 虚拟环境运行。离线测试可在没有飞书凭据的环境中执行。

```bash
python3 -m pip install -r 资讯/AI/工程/requirements.txt
python3 资讯/AI/工程/core/workdir.py print
python3 -m unittest discover -s 资讯/AI/工程/tests -t 资讯/AI/工程/tests
```

第二条命令显示实际工作目录，默认是检出目录同级的 `.ai-weekly/work`。当次草稿和检查结果在该目录，发布后的周报、榜单与运行记录在[数据目录](../数据/)。

- **修榜单**时可先运行 `python3 资讯/AI/工程/tests/test_rank.py`。涉及同分排序时，补一组 star 相同的样本，再核对名次。[榜单规格](../文档/方案.md#63-github-热度榜算法) · [榜单参数](config/ranking.yaml)
- **修飞书交付**时用[离线用例](tests/test_feishu_sync.py)验证失败与重试。已有 Git 发布稿需要补交付时，按[部署指南](../文档/部署指南.md#补交付)使用原发布提交。

提交改动前查[开发规范](../文档/开发规范.md)。其他规格、规划与提案见[文档目录](../文档/README.md)。
