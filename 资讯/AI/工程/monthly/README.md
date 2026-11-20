# 月报（规划中，尚未开发）

月报在每月初汇总上一个自然月的 AI 资讯，与周报是**相互独立的定时任务**：独立入口提示词 `prompts/routine-monthly.md`、独立执行手册、独立调度（周报每周跑上周，月报每月初跑上月）。依据见 [周报规格 2.2–2.3](../../文档/方案.md) 与 [工程分层提案](../../文档/提案/2026-11-20-工程分层与周报三段式串联.md)。

## 已预留的复用点（core 层直接可用）

- `core/weeks.py`：月份/季度归属（周四所在月）与到期、补生成判定已实现
- `core/paths.py`：`monthly()` 路径与 `MONTHLY_RE` 发布白名单正则已定义
- `core/coord.py`：发布白名单已包含月报路径
- `core/feishu_sync.py`：文档查重前缀需参数化（「AI 周报」→「AI 月报」）
- `core/quality.py`：质量推导拆分（PR-C）后可按月报口径参数化
- `config/ranking.yaml`：月度榜单参数已预留

## 待月报提案定夺（届时再立项，本次不做）

1. 采集边界：只读已发布周报与榜单 JSON，还是含独立联网搜索及次数门槛
2. 校验骨架：`validate` / `check_run` 的参数化上提方式（月报结构不同于周报）
3. `routine-monthly.md` 与 `monthly.md` 随月报 PR 同步创建；三份入口的安全规则段落须逐字节一致（由 `core/check_portability.py` 扩展检查）
