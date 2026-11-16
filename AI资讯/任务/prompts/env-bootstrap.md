<!-- task: ai-weekly-env -->
# AI 周报环境部署引导

本文件由执行手册在核心依赖缺失或验收交付环境时调用。入口只提供稳定部署授权；依赖版本、初始化步骤与验收方法在本项目维护。完成能自动处理的项后返回执行手册，不另行修改生产任务提示词。

## 授权与边界

- 仅安装 **git、Node.js（≥18）、`@larksuite/cli@1.0.100`、PyYAML**。优先系统包管理器和 npm，不安装其他软件；仅当系统源无合适 Node 版本时，允许按官方文档使用官方发行脚本。
- 可写包管理器默认目录、npm 安装目录、CLI 实际 config/data/logs 目录、`~/.ai-weekly-env.json`、项目验收状态目录及 `/tmp/ai-weekly/`。CLI 路径优先核实 `LARKSUITE_CLI_CONFIG_DIR`、`LARKSUITE_CLI_DATA_DIR`、`LARKSUITE_CLI_LOG_DIR` 与 XDG 配置；未自定义时通常分别为 `~/.lark-cli/`、`~/.local/share/lark-cli/` 和工具默认日志目录。wrapper 也可能覆盖这些变量，必须核实实际值。
- 验收状态默认为 `~/.local/state/ai-weekly/`（遵循 `XDG_STATE_HOME`），可由 `AI_WEEKLY_STATE_DIR` 指定。它只存非敏感观察结果，不是凭据备份。仓库提示词、脚本和配置均只读，不自行改部署模式。
- 网络仅用于系统/npm 官方源及其必要发行下载主机、GitHub、飞书官方鉴权与文档接口。必要重定向域名由平台环境配置放行，不绕过网络策略。
- 保留已有代理、CA 与 TLS 校验，不统一清理代理。
- lark-cli 初始化允许 `config init/show`、`auth login/status`；文档验收使用 `docs +create/+fetch/+update`，日常交付使用项目脚本。禁止删除类命令；测试文档保留作证据。
- 凭据、token、密钥不写进仓库、不输出到报告；只报告配置项名称、必要的文件路径和脱敏状态。不要完整回显 `config show` 或授权状态中的敏感字段。

## 一、自检与分流

在仓库根目录执行：

```
python3 AI资讯/任务/scripts/env_check.py check
```

输出分开解释：

- `ENV=ok` 仅表示核心生产依赖就绪；`ENV=missing/needs_human/fail:…` 表示 Python/PyYAML 或 Git 依赖仍阻塞。只补这部分也可以继续生成 Git 周报。
- `DELIVERY=ok` 表示本次机器检查通过，不代表完整文档读写、通知送达或跨任务凭据验收完成。`DELIVERY=degraded:…` 是交付层缺项，不得让正式 Git 周报停产。
- `ACCEPTANCE=pending` 表示还有实际验收；核心标记、CLI 本地授权状态和一次运行成功都不能替代验收。

验收模式下尝试补齐交付层；正式模式下仅核心依赖阻塞，飞书缺项记录降级后继续。需要人工时输出缺项及操作入口，不无限等待，也不把未完成项记为通过。已经能执行的沙箱部分可以完成，最终报告仍须标明交付未通过。

## 二、安装缺失依赖

只安装自检确实报缺失的项：

- PyYAML：`python3 -m pip install -r AI资讯/任务/requirements.txt`
- git：系统包管理器。
- Node.js ≥18：先用系统源，无合适版本再按官方文档配置源。
- lark-cli：`npm install -g @larksuite/cli@1.0.100`，确认 npm bin 在 PATH、`lark-cli --version` 可运行。

无安装权限或发行源不可达时，报告该项与所需平台操作；不要尝试安装额外软件绕过。安装后重跑自检。

Git 写入身份优先复用平台已有授权；缺失时由用户在平台秘密设置中提供仅本仓库写权限的身份或细粒度 token，不要求另建固定 `repo` scope 的 classic PAT。不要把 token 发到聊天。dry-run 只作早期检查，正式可写性仍由协调脚本实际推送验证。

## 三、飞书初始化与实际读写

1. 已有可用配置时直接复用。配置缺失才运行 `lark-cli config init --new`，绑定应用「小龙虾1号」`cli_a92390bc96f9dbb4`。保持固定 profile，核对当前激活 appId，不完整回显配置；App Secret 如需提供，只通过平台安全设置或工具安全输入。
2. user 缺失时运行 `lark-cli auth login`；把工具输出的用户确认 URL 交给本人。设备码只用于本次授权，不写进仓库或部署报告。定时任务不能完成浏览器确认时，报告后结束当前授权阶段，用户完成后再触发任务。
3. 运行 `python3 AI资讯/任务/scripts/env_check.py check --require-delivery`，确认服务端鉴权验证通过。该命令严格检查交付层；失败只表示交付验收未过，正式 Git 周报仍按降级规则执行。
4. 文档始终显式使用 **user**：由本次沙箱周报同步创建/更新 `[测试]` 文档，再实际读回核对标题和正文。保留测试文档。bot 仅负责通知；此前 bot 建文档的 99991672 是旧权限观察，**不是必须持续失败的验收条件**，不再为验证失败而创建 bot 文档。
5. 执行 `python3 AI资讯/任务/scripts/credential_probe.py --doc <测试文档ID>`（本次同步成功后可省略 `--doc` 从结果文件读取）。它执行真实 user 文档读取，记录必要的过期时间和实例观察，不输出正文或凭据。重复本地 `auth status` 不能证明自动续期。

## 四、跨任务状态与续期

先核实平台为本任务提供哪种安全、可回写的跨任务状态保存机制，再配置 CLI 的全部实际 config/data（含加密主密钥、DPoP 状态）以及验收状态目录。不要承诺平台存在可任意挂载的持久卷；发布一次环境快照也不代表之后刷新的 token 会写回给新任务。平台若没有所需机制，报告阻塞项，保持验收模式。

至少收集以下证据，分别报告，不合并为“全过”：

1. 当前任务实际 user 读取成功；
2. 后续独立任务免扫码读取成功，并能读取此前的非敏感观察记录；
3. access token 到期后首次 API 调用成功，新的过期时间确实前移；
4. 刷新后的状态能被后续独立任务再次读取使用。

实例标识只辅助区分运行环境，不能替代平台任务记录；同一机器的第二次进程调用不算跨任务证据。每周运行间隔贴近已观察到的 refresh token 约 7 天期限，没有延迟余量，须按实际过期时间验证提前保活与状态回写机制后再长期启用。不能用“通常 30 天”作保证。

## 五、返回项目流程与报告

1. 核心就绪后运行 `env_check.py ensure`。它仅缓存核心依赖，标记为 `core_ready`，不缓存人工验收结论。
2. 返回 `weekly.md`，由 `deployment.py plan/start` 根据 `config/deployment.yaml` 选择模式。仓库当前默认 `acceptance`：无需临时修改任务提示词，提交推送到本地沙箱，飞书标题带 `[测试]`，真实通知跳过。
3. 沙箱流程完成后按执行手册运行 `deployment.py finish`，报告实际检查、沙箱提交、飞书测试文档及凭据观察结果。交付失败时本次验收写 pending/failed；凭据跨任务观察单独保持 pending，不能由本次沙箱通过推成“可长期 ACTIVE”。
4. 只有用户审阅验收证据并明确批准后，才在开发流程中将项目配置改为 `production` 并发布；运行中的智能体不自行改配置。定时任务入口保持不变。
