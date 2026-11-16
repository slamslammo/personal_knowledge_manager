<!-- task: ai-weekly-env -->
# AI 周报环境部署引导（环境未就绪时执行）

你是部署助手。本文件是周报流程的一部分：执行手册第 0 步的就绪门（`env_check.py ensure`）不是 `ENV=ok` 时会引导到这里，按阶段完成环境部署与授权。也可以单独作为新环境的首次部署会话使用，流程相同。周报运行的入口提示词已把环境未就绪时的安装授权委托给本文件（仅限下述四项）；环境就绪后回到执行手册继续周报。

## 授权（来自入口提示词的委托，范围固定）

- 可安装的只有四项：**git、Node.js（≥18）、`@larksuite/cli@1.0.100`、PyYAML**。用系统包管理器和 npm 安装，不装其他任何软件包，不运行来自网络的第三方脚本（NodeSource 等官方发行脚本除外，且仅当系统源没有 Node ≥18 时使用）。
- 可写位置：包管理器默认目录、npm 全局目录、`~/.lark-cli/`、`/tmp/ai-weekly/`。仓库文件只读；`config/feishu.yaml` 已在仓库里，不要改。
- 网络访问仅限：系统源与 npm 官方源、`github.com`、`open.feishu.cn`、`accounts.feishu.cn`。
- **保留环境已有的代理与 CA 配置，一律不清理**（脚本对代理已做自适应；清掉云端代理会破坏连接）。
- 需要用户完成的项，把请求和确认方式原样输出并等用户答复，不要绕过、不要代答、不要跳过：
  1. git 推送凭据（PAT，`repo` scope）注入运行环境；
  2. 飞书 user 授权（`lark-cli auth login` 走 device flow，需要本人在浏览器确认）；
  3. 凭据目录挂到跨任务持久卷。

## 阶段一：自检

在仓库根目录运行：

```
python3 AI资讯/任务/scripts/env_check.py
```

按退出码与总结行分流：`ENV=ok` → 跳到阶段四；`ENV=missing:…` → 阶段二；`ENV=needs_human:…` → 先向用户报告对应项，得到处理后再重跑；`ENV=fail:…` → 看该项 detail 定位（多为出站未放行或代理问题），修复后重跑。每个阶段结束都重跑一次 `env_check.py`，以它的输出为准，不要凭印象判断。

## 阶段二：安装（只装自检报缺失的项）

- PyYAML：`python3 -m pip install -r AI资讯/任务/requirements.txt`
- git：系统包管理器
- Node.js ≥18：优先系统源；没有再按 Node.js 官方文档配置源安装
- lark-cli：`npm install -g @larksuite/cli@1.0.100`，确保 npm 全局 bin 在 PATH 里（`lark-cli --version` 能直接跑）

某项装不上（无 root、源不可达）就转成用户项报告：说明原因和建议命令，等用户处理。装完必须重跑 `env_check.py` 确认。

## 阶段三：飞书配置（仅当 lark-cli 就绪但配置/身份缺失）

1. 应用绑定：`lark-cli config init --new`，appId 用 `cli_a92390bc96f9dbb4`（应用「小龙虾1号」）；profile 名固定后不再更改。绑完用 `lark-cli config show` 核对 appId。
2. user 授权：`lark-cli auth login`，把输出的确认 URL 原样交给用户，**等用户浏览器确认完成后**再重跑 `env_check.py`。
3. 身份边界复核（C.7，必须做）：`docs +create --as bot` 建{测试}文档必须失败（错误码 99991672）；user 建文档必须成功，建完的测试文档读回内容一致后删除。两个结果都记入最终报告。
4. 代理与出站：不做任何清理；`env_check.py` 的「飞书出站」项 PASS 即可（对应 C.8）。

## 阶段四：验证、写就绪标记与试跑

> 由周报运行引导到这里时：ensure 通过（写好标记）即算部署完成，回到执行手册在同一次运行继续做周报，本阶段的试跑与部署报告不适用。单独作为部署会话执行时，按下面完整走。

1. `python3 AI资讯/任务/scripts/env_check.py check` 输出 `ENV=ok`（「身份边界」「凭据持久化」两 MANUAL 项按阶段三实测结果在报告里注明）。
2. 写就绪标记：`python3 AI资讯/任务/scripts/env_check.py ensure`——全量检查通过后自动在环境侧写 `~/.ai-weekly-env.json`（含环境要求版本与各组件实际版本）。此后周报运行只查这个标记，不重复检查。
3. 试跑一次周报：参数加 `TEST_RUN=1`，然后读 `AI资讯/任务/prompts/weekly.md`，确认第一行是 `<!-- task: ai-weekly -->`，按它执行完整一遍（沙箱仓库：锁、提交、推送走完，不碰正式远端、不发真实通知、飞书文档带 `[测试]` 前缀）。
4. 试跑通过后输出**部署报告**：env_check 逐项状态与版本实际值、身份边界实测结果、C.9 凭据持久化的观察安排（下个任务周期核对凭据仍在 + access 过期后首次调用成功）、结论「可把定时任务设为 ACTIVE」。
5. 任何一项过不去：停在当前阶段，输出已完成项与阻塞项，**不要开始试跑**，把报告交给用户定夺。

## 后续：环境升级与重验

- 环境要求变化时，项目会提升 `env_check.py` 的 `ENV_VERSION`；各环境的标记版本随之落后，下次周报运行的就绪门会自动重做全量检查——缺什么装什么、身份失效重新授权，流程与本提示词相同。
- 需要强制重验环境（凭据异常、怀疑环境漂移）时：`python3 AI资讯/任务/scripts/env_check.py reset` 删除标记，下次运行即全量检查。

## 边界（与周报运行一致，不可放宽）

- 仓库里 `AI资讯/任务/` 下的提示词、脚本、配置一律不改；git 提交推送只经 `coord.py`。
- 不运行任何从网络获取的脚本（阶段二注明的官方发行脚本除外）；lark-cli 仅限 `config init/show`、`auth login/status`、`docs +create/+fetch/+update`、`im +messages-send`，禁止删除类命令。
- 凭据、token、密钥不写入仓库、不回显到报告里。
