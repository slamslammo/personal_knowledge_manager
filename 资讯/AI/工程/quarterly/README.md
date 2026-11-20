# 季报（规划中，尚未开发）

季报在每季度初汇总上一季度的 AI 资讯，与周报、月报是**相互独立的定时任务**：独立入口提示词 `prompts/routine-quarterly.md`、独立执行手册、独立调度。依据见 [周报规格 2.2–2.3 与第 5 节](../../文档/方案.md) 与 [工程分层提案](../../文档/提案/2026-11-20-工程分层与周报三段式串联.md)。

## 已预留的复用点（core 层直接可用）

- `core/weeks.py`：季度归属与到期判定已实现
- `core/paths.py`：`quarterly()` 路径与 `QUARTERLY_RE` 发布白名单正则已定义
- `core/coord.py`：发布白名单已包含季报路径
- `core/feishu_sync.py`：文档查重前缀需参数化（「AI 季报」）
- `core/quality.py`：质量推导拆分（PR-C）后可按季报口径参数化

## 待季报提案定夺（届时再立项，本次不做）

1. 采集边界：以已发布月报/周报为输入的归纳深度，是否含独立联网搜索
2. 校验骨架：季报结构的参数化校验方式
3. `routine-quarterly.md` 与 `quarterly.md` 随季报 PR 同步创建；三份入口的安全规则段落须逐字节一致（由 `core/check_portability.py` 扩展检查）
