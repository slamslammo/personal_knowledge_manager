<!-- task: ai-weekly-env -->
# AI 周报环境部署引导

本文件由执行手册在核心依赖缺失或验收交付环境时调用。入口只提供稳定部署授权；依赖版本、初始化步骤与验收方法在本项目维护。完成能自动处理的项后返回执行手册，不另行修改生产任务提示词。

如果当前环境已有发布到本地沙箱的周报，只补配置与交付：保留 `/tmp/ai-weekly/`、沙箱提交和原通知预览，补齐后运行 `deployment.py resume`。不要为重新授权而重跑采集、搜索和写稿，也不要先清空仍存设备码或沙箱证据的临时目录。实际文件不可恢复时才报告缺失，按执行手册开始新运行。

## 授权与边界

- 仅安装 **git、Node.js（≥18）、`@larksuite/cli@1.0.100`、PyYAML**。优先系统包管理器和 npm，不安装其他软件；仅当系统源无合适 Node 版本时，允许按官方文档使用官方发行脚本。
- 可写包管理器默认目录、npm 安装目录、CLI 实际 config/data/logs 目录、`~/.ai-weekly-env.json`、项目验收状态目录及 `/tmp/ai-weekly/`。CLI 路径优先核实 `LARKSUITE_CLI_CONFIG_DIR`、`LARKSUITE_CLI_DATA_DIR`、`LARKSUITE_CLI_LOG_DIR` 与 XDG 配置；未自定义时通常分别为 `~/.lark-cli/`、`~/.local/share/lark-cli/` 和工具默认日志目录。wrapper 也可能覆盖这些变量，必须核实实际值。
- 验收状态默认为 `~/.local/state/ai-weekly/`（遵循 `XDG_STATE_HOME`），可由 `AI_WEEKLY_STATE_DIR` 指定。它只存非敏感观察结果，不是凭据备份。仓库提示词、脚本和配置均只读，不自行改部署模式。
- 网络仅用于系统/npm 官方源及其必要发行下载主机、GitHub、飞书官方鉴权与文档接口。必要重定向域名由平台环境配置放行，不绕过网络策略。
- 保留已有代理、CA 与 TLS 校验，不统一清理代理。
- lark-cli 初始化允许 `config init/show`、`auth login/status/qrcode`；`auth qrcode` 仅将本次飞书确认 URL 编码为本地二维码，不创建应用、不访问新服务。文档验收使用 `docs +create/+fetch/+update`，日常交付使用项目脚本。禁止删除类命令；测试文档保留作证据。
- 凭据、token、密钥不写进仓库、不输出到报告；只报告配置项名称、必要的文件路径和脱敏状态。不要完整回显 `config show` 或授权状态中的敏感字段。

## 一、自检与分流

在仓库根目录执行：

```
python3 AI资讯/任务/scripts/env_check.py check
```

输出分开解释：

- `ENV=ok` 仅表示核心生产依赖就绪；`ENV=missing/needs_human/fail:…` 表示 Python/PyYAML 或 Git 依赖仍阻塞。正式运行只要求核心依赖，首次验收新生成还须通过下面的严格交付检查。
- `DELIVERY=ok` 表示本次机器检查通过，不代表完整文档读写、通知送达或跨任务凭据验收完成。`DELIVERY=degraded:…` 是交付层缺项，不得让正式 Git 周报停产。
- `ACCEPTANCE=pending` 表示还有实际验收；核心标记、CLI 本地授权状态和一次运行成功都不能替代验收。

首次验收新生成前必须完成部署和 user/bot 授权，通过 `env_check.py check --require-delivery`；缺项时先报告具体安全配置或本人确认入口并停止，不在授权未完成时先做搜索或完整写稿。C9 仍需后续多次真实运行观察，不是首次生成前置项。正式模式下仅核心依赖阻塞，飞书缺项记录降级后继续；已有沙箱则优先只补交付。两阶段不得混用。

## 二、安装缺失依赖

只安装自检确实报缺失的项：

- PyYAML：`python3 -m pip install -r AI资讯/任务/requirements.txt`
- git：系统包管理器。
- Node.js ≥18：先用系统源，无合适版本再按官方文档配置源。
- lark-cli：`npm install -g @larksuite/cli@1.0.100`，确认 npm bin 在 PATH、`lark-cli --version` 可运行。

无安装权限或发行源不可达时，报告该项与所需平台操作；不要尝试安装额外软件绕过。安装后重跑自检。

Git 写入身份优先复用平台已有授权；缺失时由用户在平台秘密设置中提供仅本仓库写权限的身份或细粒度 token，不要求另建固定 `repo` scope 的 classic PAT。不要把 token 发到聊天。dry-run 只作早期检查，正式可写性仍由协调脚本实际推送验证。

## 三、飞书初始化与实际读写

1. **复用已有应用，不创建新应用。** 当前激活配置已是「小龙虾1号」`cli_a92390bc96f9dbb4` 时直接复用。配置缺失时，用 `lark-cli config init --app-id cli_a92390bc96f9dbb4 --app-secret-stdin --brand feishu --name pkm-feishu-test`，由平台安全设置提供现有应用的 App Secret，经标准输入注入，不把值拼进命令、聊天或报告。保持固定 profile，核对当前激活 appId，不完整回显配置。**禁止使用 `config init --new`，该选项会创建新应用，不是绑定现有应用。** 缺少现有应用凭据时报告所需的安全配置；不要运行无参数的交互初始化去选择创建应用，也不要用创建新应用绕过缺项。若 Agent 工作区限制 init，报告绑定来源与身份策略需求，不加 `--force-init` 绕过。
2. **配置完成后才启动 user 授权。** 安装 CLI 本身不会向用户弹出二维码。user 缺失时运行 `lark-cli auth login --no-wait --json --scope "docx:document:create docx:document:readonly docx:document:write_only search:docs:read offline_access"`，立即取得工具返回的用户确认 URL、设备码和有效期；不要把普通阻塞 `auth login` 挂在后台等待，以免确认入口始终未送到用户。以上权限对应本项目文档创建、读取、编辑、搜索与续期，已在既有授权中核对；如目标应用缺少其中权限，报告缺项，不退回 CLI 默认的全部业务域授权。
   - 将确认 URL 和有效期作为当前回复的可见内容发给本人。需要二维码时，使用 `lark-cli auth qrcode "<本次确认URL>" --output /tmp/ai-weekly/feishu-auth.png`，并通过平台图片/文件输出能力展示生成文件；不能只打印云端路径。平台无法展示图片时直接给可点击 URL，不承诺弹出本机浏览器或系统授权窗。
   - 设备码仅保存到当前任务允许的临时目录，文件权限 600；不回显设备码，不写入 Git 或部署报告。本人在有效期内确认后，先在**同一执行环境**运行 `lark-cli auth login --device-code <本次设备码>`，完成换取并保存凭据，再实际读取验证；不要先重新启动会清空临时目录的整套周报流程。
   - 不把本人点击链接当作已完成 CLI 登录；还必须完成设备码轮询及凭据落盘。若任务已结束、设备码过期，或下一次任务无法恢复原环境及临时状态，则重新生成授权入口，并明确报告跨任务状态问题，不能声称已免扫码。已有有效 user 身份直接复用，不重复要求授权。
3. 运行 `python3 AI资讯/任务/scripts/env_check.py check --require-delivery`，确认核心 Git 写入初筛、工具、绑定及 user/bot 服务端鉴权通过。首次验收的新生成必须在它成功后开始；失败停在部署并报告缺项，不进入采集和写稿。正式运行的 Git 周报仍按飞书降级规则执行；C9 观察不由此命令宣称通过。
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

已有沙箱提交的恢复优先于上述新运行路径：应用配置或本人授权完成后运行 `deployment.py resume`，由脚本重新核实原沙箱提交、同步其正文并完成读回核对。`RESUME=pending` 就保留产物、报告剩余缺项；`RESUME=completed` 仅表示本次验收交付完成。GitHub 生产写入、C9 与 bot 真实送达仍分别报告，不因补交付成功而自动上线。
