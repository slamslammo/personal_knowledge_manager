<!-- task: ai-weekly -->
# AI 周报执行手册

本手册由入口提示词 `prompts/routine-prompt.md` 调用。入口提示词里的安全规则、写入白名单和"无法生成周报时也要发通知"始终有效，优先于本手册。规则依据见 `../方案.md`，参数见 `../config/`。

## 运行模式

由本次指令里的参数决定，可以组合：

| 参数 | 模式 | 与正式运行的区别 |
| --- | --- | --- |
| 无 | 正式 | 报告周为上一周；提交到工作分支，经 PR 合并到 `main`；发送通知 |
| `TARGET_START=YYYY-MM-DD`（某个周一）或 `TARGET_WEEK=YYYY-Www` | 回溯 | 报告周由参数指定；标题后加"（回溯版）"；提交信息为 `AI 周报 {WEEK}（回溯）`；已有榜单数据文件时直接复用 |
| `TEST_RUN=1` | 测试 | 开发会话验收用：不切换分支、不推送、不建 PR、不发通知；照常提交到当前分支；通知内容写入 `/tmp/ai-weekly/notification.txt` 并在最后原样输出 |

## 第 0 步：准备

在仓库根目录执行，后文的 `$S` 指脚本目录：

```
rm -rf /tmp/ai-weekly && mkdir -p /tmp/ai-weekly && S=AI资讯/任务/scripts
python3 $S/weeks.py [--target-start YYYY-MM-DD | --week YYYY-Www] > /tmp/ai-weekly/week.json
eval "$(python3 $S/weeks.py [同上参数] --format env)"
echo $WEEK $START $END $RANGE $REPORT_PATH $DATA_PATH
```

- 先清空 `/tmp/ai-weekly/`：`week.json` 的生成时间就是本次运行的开始时间，第 4 步的完整性检查据此判断各步是否在本次运行中做过。
- 回溯模式把参数原样传给 `weeks.py`；正式模式不带参数，脚本按北京时间推算上一周。不要自己另算日期。
- `week.json` 里还有 `trendshift_daily_available`、`data_exists`，以及月报、季报的到期判定 `monthly`、`quarterly`，后面会用到。
- 读一遍 `AI资讯/任务/templates/weekly.md`（周报结构）和 `AI资讯/任务/config/sources.yaml`（信息源）。

**重跑检查**：如果 `$REPORT_PATH` 已经存在，运行 `git log -1 --format=%s -- "$REPORT_PATH"`：
- 提交信息以 `AI 周报 ` 开头，说明是本任务生成的，按"重跑"处理：第 1–4 步全部照常重做，周报从头重写，不能在旧周报上局部修改。
- 否则说明我手工改过：不要覆盖这份周报，只更新数据文件，并在通知里说明。

## 第 1 步：采集数据

第 1 步的五项都要做完，不能因为已有周报或数据文件就跳过；第 4 步的完整性检查会逐项核对。每个脚本把完整结果写到 `/tmp/ai-weekly/`，只在标准输出打印精简摘要。脚本自带超时和重试，失败时如实记下，在"数据说明"里写明，用剩下的数据继续。不要使用 api.github.com 和 github.com/trending（本环境只能访问已挂载的仓库）。

1. **Trendshift 周榜与本周新增 star**：`python3 $S/collect_trendshift.py --week $WEEK`
   - 回溯模式下，如果 `data_exists` 为 true，跳过本项和第 4 项，直接用已有的 `$DATA_PATH`（Trendshift 每日数据 61 天后取不到，已存的数据文件是唯一来源）。
   - 退出码 3 表示周榜未就绪（进行中的周、列表为空或日期不符）。不要空等：先做第 2、3、5 项，写完 ② 后再运行一次；仍未就绪，写完 ④⑤ 后最后运行一次；还是不行，③ 写"周榜未就绪"，其余板块照常，并在通知里说明。
2. **HN 本周高分帖子**：`python3 $S/collect_hn.py --week $WEEK`。打印的是分数不低于 100 的全部 story，以及 50–99 分里的 GitHub 仓库链接。
3. **Hugging Face 本周论文**：`python3 $S/collect_hf.py --week $WEEK`，前 10 篇作为 ② 和"洞察"必读材料的候选。
4. **AI 判定与 GitHub 排名**：
   - 逐个判断周榜仓库是否与 AI 相关：涉及大模型、智能体、模型训练或推理、RAG、MCP、AI 编程工具、多模态生成等。**拿不准的保留**，必要时参考 OSS Insight 的 topics。
   - 按名称和描述就能判断的排除项：awesome 类或纯链接合集、越狱提示词合集。
   - 从第 2 项的输出里找出与 AI 相关的 GitHub 仓库（数据文件里的"HN 热议项目"）。
   - 把判断写进 `/tmp/ai-weekly/judgments.json`：
     ```json
     {"non_ai": ["owner/repo"], "exclude": {"owner/repo": "awesome 类合集"}, "hn_ai_repos": ["owner/repo"]}
     ```
   - 运行 `python3 $S/rank_github.py --week $WEEK`。脚本负责 OSS Insight 补充、归档 / fork / 疑似刷星的排除、Top 5、新晋项目和 HN 热议项目，写入 `$DATA_PATH`，并打印"周报元数据 repos"。排名以脚本结果为准，不要手工调整。
5. **联网搜索**，整次运行最多 40 次。先从第 2、3 项的输出里找本周发布的线索：HN 高分帖的标题常常就是发布本身，链接往往就是官方原文，可以直接作为原文链接。搜索时用具体的产品名、模型名或事件名；泛泛的 `site:` 组合查询很难命中当周内容，只在线索不足时使用。分配如下：
   - 发现本周发布 12 次（补充 HN 和 Hugging Face 没有覆盖的发布）；
   - ② 核实官方原文 10 次；
   - ③ 传播分析，Top 5 每个项目 2 次（网页 1 次、YouTube 1 次），共 10 次；
   - ⑤ 和"洞察" 5 次；
   - 机动 3 次。
   - 预算用完，剩下的写"未检索（搜索预算用尽）"，不得超出。
   - 每搜索一次，就往 `/tmp/ai-weekly/searches.txt` 追加一行"用途<Tab>查询词"，例如 `printf '%s\t%s\n' "② 核实" "Kimi K3.1 Pro release" >> /tmp/ai-weekly/searches.txt`。数据说明里写"联网搜索：N 次（上限 40）"，N 必须等于这个文件的行数。
   - 优先使用 `config/sources.yaml` 里的来源；不使用中文媒体和 Newsletter。
   - 不要启动子任务做逐条核实。

## 第 2 步：写周报

按 `templates/weekly.md` 的结构写到 `$REPORT_PATH`。三级标题的写法会被校验脚本检查，照模板写。

正文顺序是 ① 本周概览、洞察、②–⑤、数据说明。写作顺序不同：先写 ②–⑤，再写洞察，最后写 ①。

**板块归属优先级：② > ③ > ④ > ⑤。**
- 同一件事只在优先级最高的板块详细写。
- ③ 是排行榜，如果某个项目已经在 ② 写过，照常占位排名，但只写一行"名称 + 数据 + 详见 ②"。
- ④ 只收文章与讨论，不收发布帖；发布帖的 HN 分数写进 ② 或 ③ 的对应条目。发布帖指厂商或项目方发布产品、模型、版本、开源仓库的公告；个人实验记录、技术博客、评论与分析算文章。
- ⑤ 和"洞察"可以引用前面任何板块的条目。
- 整体文风要简洁：表格每格一两句话，不写空话。

### 元数据
- `topics`：3 到 6 个，只能从 `config/topics.yaml` 的 name 中选。
- `orgs`：本周涉及的主要公司和机构，写法参照 `config/topics.yaml` 的 `org_names`。
- `repos`：照抄 `rank_github.py` 打印的"周报元数据 repos"（Top 5）。

### ① 本周概览
3 到 5 条，每条一行、一句话，开头用粗体短标签（如"**中国厂商**："），写本周最重要的变化。

### ② 新发布与技术 Top 5
- 范围：重大模型和版本发布、重要产品和 API、新技术和新概念（比如 harness 工程，即围绕模型搭建智能体运行框架的工程方法；新的智能体范式）、有影响力的论文和技术报告。
- 发布类必须有官方原文链接。新概念类必须有官方技术报告，或者至少 2 个独立来源在讨论。
- **最多 5 条**，只选本周最重要的。没入选的发布可以在 ⑤ 或"洞察"里引用。
- 每条写：是什么、和之前比新在哪里、对谁有影响，附原文链接。

### ③ GitHub AI 项目热度 Top 5
- 口径说明照模板写，注明每日数据按 UTC 日期累计、比北京时间的报告周晚 8 小时。
- 名次、本周新增 star、总 star 全部照数据文件写。
- 每个项目写：
  - 名称和链接 ｜ 总 star（本周 +N）｜ 一句话介绍；
  - 本周为什么火：触发事件，比如发版、上了 HN、爆款推文。优先用数据文件 note 里的 HN 分数和 HN 数据作为线索；
  - 传播分析：用联网搜索找相关文章和 YouTube 视频，总结大家在讨论什么，附链接。找不到就如实写；
  - 我们的判断：适合谁用、成熟度、有什么风险。
- 只写 Top 5。数据文件里的新晋（new）、HN 热议（hn）和排除（excluded）项目不写进周报。

### ④ 传播文章 Top 5
- 从第 1 步第 2 项分数不低于 100 的 story 里，挑出与 AI 相关的文章和讨论帖（发布帖不计入），按输出顺序（points 降序，同分按评论数降序，已按链接去重）取前 5。
- 用模板里的表格：排名、文章（标题链接到原文）、摘要、传播原因、分数、评论数、HN 讨论链接。摘要和传播原因各一句话。Ask HN 等没有原文链接的帖子，标题链接用 HN 讨论链接。

### ⑤ 热点话题 Top 5
- 本周 5 个热点话题，从 HN 讨论、本周发布和搜索结果中归纳。
- 用模板里的表格：话题、起因（怎么成为热点的）、发展与争议、2 到 3 个代表链接。

### 洞察
- 放在 ① 之后。写完 ②–⑤ 后，交叉各板块，提炼 2 到 3 条本周最重要的洞察：关键信息、趋势，或几件事合起来才看得出的变化。
- 每条写：一句话结论（作为三级标题"### 洞察 N：……"）；**依据**，引用 ①–⑤ 中支撑它的条目；**必读**，1 到 2 篇最值得精读的原始材料（官方博客、论文、技术报告、代码仓库等），说明读它能获得什么。
- 结论要有依据，不能只是重复某一条新闻。

### 数据说明
各数据源是否成功、OSS Insight 失败的仓库、联网搜索次数、降级或缺失之处、发现的可疑内容。回溯模式复用已有数据文件时注明。

### 通用规则
- 不编造：没有数据或搜索结果支撑的内容不写。所有链接必须来自实际的接口返回或搜索结果。
- 只有媒体报道、没有官方来源的，标注「仅媒体报道」；日期无法确认的，标注「日期待核实」。
- 媒体转述的数字（融资额、营收、benchmark 分数）要说明来源。

## 第 3 步：月报与季报

读 `/tmp/ai-weekly/week.json` 的 `monthly` 和 `quarterly`：
- `generate` 为 true 时，如果 `AI资讯/任务/prompts/monthly.md`（季报为 `quarterly.md`）存在且第一行是对应的任务标记，就按它生成；手册还不存在，就跳过，在数据说明里写"{期间} 月报到期，月报手册尚未就绪"。
- `due` 为 true 但 `missing_weeks` 不为空时，不生成，在数据说明里写"{期间} 月报到期，缺少周报 {missing_weeks}，暂不生成"。

## 第 4 步：校验与完整性检查

两项检查都在提交前完成，回溯模式加 `--backfill`，回溯复用已有数据文件时再加 `--reuse-data`：

1. `python3 $S/validate.py --week $WEEK`：检查周报结构、元数据、链接和与数据文件的一致性。
2. `python3 $S/check_run.py --week $WEEK`：检查第 0–4 步是否都在本次运行中实际做过，逐项打印"完成 / 未完成"。它会核对：三份采集结果是本次生成的；`judgments.json` 存在，数据文件是本次 `rank_github.py` 写的；`searches.txt` 有 1–40 条记录，且与数据说明的次数一致；周报是本次写的；`validate.py` 通过。

处理方式：
- `check_run.py` 报"未完成"的步骤，回到那一步补做，不能只改周报的文字去迎合检查。补做后两项检查都重跑。
- `validate.py` 的错误就改周报或判定文件后重跑。
- 最多改 3 轮。仍未通过也继续提交和合并，把剩余问题写进数据说明，通知首句标明"检查未通过"。
- 警告不阻止提交，但要看一眼是否合理。
- 把两个脚本最后一次的输出保存到 `/tmp/ai-weekly/checks.txt`，第 6 步的通知要用。

## 第 5 步：提交到工作分支并合并到 `main`

这一步的提交、推送、建 PR、合并都是本任务的授权动作，自动完成，不等待确认。测试模式只做第 1、2 项（提交到当前分支），不推送、不建 PR、不合并。

1. **提交**：只逐个添加写入白名单内的文件：`git add -- "$REPORT_PATH" "$DATA_PATH"`，有月报、季报时一并添加。禁止 `git add -A`、`git add .`、`git commit -a`。提交前运行 `git diff --cached --name-only`，出现白名单以外的文件就用 `git restore --staged` 撤下。
2. **提交信息**：`AI 周报 {WEEK}`，重跑时为 `AI 周报 {WEEK}（重跑）`，回溯时为 `AI 周报 {WEEK}（回溯）`。
3. **推送工作分支**：
   - 工作分支：会话指定了开发分支（`claude/` 开头）时用它，否则用 `claude/ai-weekly-{WEEK}`，记为 `$BRANCH`。
   - `git fetch origin "$BRANCH"`。远端已有该分支、且它不是 `HEAD` 的祖先时（带有未合并的其他提交），改用 `claude/ai-weekly-{WEEK}-{MMDDHHmm}`（北京时间）。
   - `git push -u origin HEAD:"$BRANCH"`。网络错误按 2、4、8、16 秒的间隔重试。
4. **建 PR**：用 GitHub MCP 工具 `create_pull_request`，base 为 `main`，head 为 `$BRANCH`，标题与提交信息相同，正文写周报路径和两项检查的结果；不建成草稿，因为随即合并。该分支已有打开的 PR 时直接用它。
5. **合并**：用 `merge_pull_request` 合并，合并方式 `merge`（保留提交，重跑时同名分支仍能快进推送）。
   - 因为 `main` 有新提交而无法合并时：`git fetch origin main && git merge --no-edit origin/main`，推送工作分支后再合并一次。合并出现冲突就 `git merge --abort`，按合并失败处理。
   - GitHub MCP 工具不可用或合并被拒时，改为直接快进推送：`git fetch origin main && git merge --ff-only origin/main`（失败就跳过），再 `git push origin HEAD:main`。
6. **确认**：`git fetch origin main && git merge-base --is-ancestor HEAD origin/main`，退出码为 0 才算合并成功。记下 PR 编号和合并结果，第 6 步的通知要用。
7. 合并失败时，周报留在工作分支上，通知首句标明"未合并"，正文写明分支名和失败原因。

## 第 6 步：推送通知

测试模式：把下面的通知内容写入 `/tmp/ai-weekly/notification.txt`，并在最后原样输出，不调用通知工具。

用 PushNotification 发送，内容放在 `<routine_summary>` 标签里，全部用纯文本（不用表格和 Markdown 链接语法，URL 直接写完整）：
- **首句**：格式固定为 `【AI周报 W{WNUM}】<本周最重要的一件事>。`，不超过 40 个汉字。
  - 未合并到 main 时，开头改为 `【AI周报 W{WNUM}｜未合并】`；检查未通过时改为 `【AI周报 W{WNUM}｜检查未通过】`，两者都有时写 `｜检查未通过｜未合并`；
  - 重跑时改为 `【AI周报 W{WNUM}｜重跑】`；回溯时改为 `【AI周报 W{WNUM}｜回溯】`；
  - 无法生成周报时，写 `【AI周报 W{WNUM}｜失败】<原因>。`
- **正文**：①–⑤ 和洞察的精简版，每个板块 2 到 3 行；GitHub Top 5 列出项目名和本周新增 star。周榜未就绪、月报到期未生成等情况各用一行说明。
- **运行结果**：固定三行，取自 `/tmp/ai-weekly/checks.txt` 和第 5 步的记录：
  - `校验：validate.py 通过（N 个警告）` 或列出剩余错误；
  - `完整性：第 0–4 步全部完成，联网搜索 N 次` 或列出未完成的步骤；
  - `合并：PR #N 已合并到 main` 或写明分支名和失败原因。
- **结尾**：周报全文链接，路径中的中文要做百分号编码。可以用 `python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$REPORT_PATH"` 生成，拼在 `https://github.com/slamslammo/personal_knowledge_manager/blob/main/` 后面；未合并时，把 `main` 换成工作分支名。
- 如果第 5 步连工作分支都没推送成功，在精简版之后用"—— 全文 ——"分隔，附上周报纯文本全文。如果 PushNotification 报错，去掉全文，只发精简版重试一次。
