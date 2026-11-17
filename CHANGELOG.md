# CHANGELOG

## 1.0.2 — 2026-11-17

开箱即用版。两条主线：**新用户不再需要自建网关**，以及把「三循环四保险」从模板落成代码。

### 修复

- **首次启动不建数据目录**（issue #1，来自真实反馈）：`serve()` 启动即创建 `data`、`data/projects`、`data/config`。此前要等用户点「新建项目」才建，与 README「首次会建数据目录」不符。
- **出厂默认不再是「走网关」**：仓库里的 `config/coordinator.json` 原来带 `gateway.enabled: true`，所有下载者继承它——不自己搭 3000 端口就写不了字。现在默认 `false`，打开设置填自己的 key 即可写作。
- **用户配置不再落进代码仓库**：`load_cfg()` 改为数据目录优先（`data/config/coordinator.json`），写配置永远写数据目录。此前改设置会改到仓库里那份，`git status` 变脏、下次 pull 冲突。
- **`triage.py` 认「期望 vs 实际」型缺陷**：原来 `repro_ready` 只认 `Traceback` / `HTTP 4xx`，像 issue #1 这种「没有报错、只是行为与文档不符」的缺陷一律判成 `human`。现在期望/实际成对出现、或正文含输出块，也算有证据。

### 新增（三循环四保险，可独立验证）

- **写前粗筛 `core/precheck_input.py`**（第 2 保险）：调模型之前拦住注定写不好的输入——章号非 3 位、找不到本章大纲、占位残留（`{topic}` / `TODO` / `待补` / 空括号）。软缺（一句话章纲、分场块不全、覆盖定稿）只提示不阻；`force=true` 可越过。
- **写盘红线 `core/redline.py`**（第 3 保险）：隐藏路径（`.stages.json` / `.layers/` / `.trash/`）一律拒；已定稿章节被覆盖或被删需 `force=true`。此前能从 Web 写接口直接改 `.stages.json`，把定稿改回 draft。
- **任务队列 `core/task_queue.py`**（任务循环）：`GET /api/queue` 出待办全表（章号 / 状态 / 有无章纲 / 是否待修 / 分数与理由），`POST /api/queue/next` 给「下一个该处理哪章」，跳过定稿、不自动调模型。分数可解释：错题本 +100、有章纲 +40、有正文可续 +20、有章纲无正文 +10、已定稿 −50。
- **发布前总检 `scripts/_pre_publish_check.py`**：密钥形态、`C:\Users\<名>` 用户目录、客户统计、具体书名、fixtures 正文、凭据文件、`.gitignore` 覆盖，一次查完；带 NFKC + URL 解码，全角与 `%2D%2Dbook` 写法也能命中。
- **pre-push 红线 hook `.githooks/pre-push`**：对 github.com 的推送强制跑总检，不通过即阻断。安装：`git config core.hooksPath .githooks`。
- **issue 关单写错题本 `scripts/_issue_recorder.py`**：同类根因累计 3 次，`loop_log.proposals()` 给出「升级为硬门禁」提案。

### 文档

- README「模型怎么接」改为「直连厂商（默认）/ 自建网关（可选）」；附录 B 重写——原文假定人人跑网关，且写了作者本机路径。
- 新增 `issues/REQ-purge-old-commits.md`（旧 commit 清除请求模板）。

### 验证

12 个验收脚本全 PASS：`_poc_n1n2` 14/14、`regression_auth` 8/8、`_verify_redline` 11/11、`_verify_precheck_input` 12/12、`_verify_queue` 13/13，以及 `_verify_triage`、`_verify_entries_api`、`_verify_err_msgs`、`_verify_no_private_data`、`_repro` ×3、`_smoke_entries`、`_check_keys`。

## 1.0.1 — 2026-11-17

安全修复版。只动入口防护与版本号，写作逻辑、API 契约、界面操作流程都没变。

### 修复

- **N1（高）Host 头伪造 → DNS rebinding**：入口只接受回环 Host（`127.0.0.1` / `localhost` / `[::1]`），伪造 Host 一律 403。局域网部署用 `NOVELAPP_ALLOW_HOSTS` 显式开白，默认不放。
- **N2（高）跨站 Origin + 任意 Content-Type → CSRF 写文件**：所有写请求校验 `Origin` 必须同源（缺省放行，供 curl/脚本用），`Sec-Fetch-Site: cross-site` 直接 403，且 `Content-Type` 必须是 `application/json`。跨站表单 + `text/plain` 的落地写文件路径已封。
- **N3（中）`/api/chat` 无令牌**：无 `X-Novelapp-Token` 返回 401。页面由服务端注入进程内令牌（`_index()` 替换占位符），界面不用改、照常能写。
- **N5（低）`/api/tree?path=..`**：带 `path` 时走统一 `safe_rel` 校验，越界返回 400，不再静默归一化。
- **错误文案普通话化**：界面不再出现 `KeyError:`、`TypeError:`、`JSONDecodeError:` 这类英文异常名。新增 `core/errors.py` 统一映射（缺字段 / 格式不对 / 网络不通 / 文件不存在 / 权限 / 编码 / 超时 / 上游 4xx-5xx / 磁盘），`server.py` 69 处、7 个模块 20 处错误出口改为中文；英文原文与堆栈只写 `<data_dir>/logs/errors.log`。
- **大纲 / 设定库专用 API**：新增 `GET /api/outline|/api/settings`（不带 `name` 列目录，带 `name` 读单篇）与 `POST /api/outline|/api/settings`（写单篇）。章纲在写盘前按 `docs/架构-通用版/08-章纲分场规范.md` 校验：场次表 4 列、≥2 场、必须做到 ≥3 条、不许做 ≥1 条、文风锚点（本章推进可选）；不合格返回 400 且文件不动，`force=true` 可人工越过。全书大纲 / 分卷大纲不做章纲校验。9 入口的 `missing` 从 2 降到 0。
- **`/api/entries` 增加发布包过期判定**（issue-0001）：返回 `shipped_stale` 与 `shipped_note`。此前只报 `shipped_present: true`，会把 11-05 的 56KB 旧包当成本次发布物——那个包不含 N1/N2 修复。
- **`triage.py` 修误判**：`## 环境` 小节不再参与分类。此前 issue 模板里写了"网关 / Python 版本"，任何 bug 都会被判成 `env`。
- **`_repro.ps1` 支持 `-Assert`**：把断言写进复现器（目前支持 `shipped-judged`），供流水线自动判红绿，而不是靠人眼看输出。

### issue 流水线（可跑通一条）

`scripts\_issue_pipeline.ps1`：triage → 先红（`_repro` 必须 exit 1）→ 改一个文件 → 转绿（exit 0）→ `_check_keys` + `_smoke_entries` → 写 `repro\PR-<n>.md`（**不自动 push**）。

端到端样例（本次真跑了三遍，可复现）：

```
issue   issues\issue-0001-shipped-stale.md
修复    scripts\_fix_shipped_stale.py（幂等；--revert 可回滚）
产物    issues\PR-0001.md（入库；repro/ 是可重生成产物，仍被 .gitignore 忽略）
判定    改前 exit=1 FAIL entries  →  改后 exit=0 PASS entries
实测    shipped_stale=True note='发布包是旧版（56858 字节 vs 源码 262793 字节，仅 22%），含已知安全修复缺失，先重新构建再用'
```

### 发布物（本地成稿，未发）

| 文件 | 用途 |
|---|---|
| `release/1.0.1.md` | GitHub Release 正文，可直接粘 |
| `release/posts/zhihu-01.md` | 知乎首帖（四组对照 + 方法 + 仓库） |
| `release/posts/xiaohongshu-01.md` | 小红书首帖（痛点 + 三个数 + 7 图脚本 + 标签） |
| `release/posts/bilibili-01.md` | B站 3 分 10 秒分镜与口播稿 |
| `release/plan-12w.md` | 12 周判据（stars ≥150 或 周活 ≥100）与不达标处置 |
| `issues/weekly.md` | 12 行检查表骨架，每周填四个数 |

校验：`python scripts/_verify_release_copy.py` —— 文案引用的每个指标都能反查到 README / CHANGELOG / `posts/01`；Release 说明提到的 `shipped_stale`、`NOVELAPP_ALLOW_HOSTS`、`safe_rel`、`__NVL_TOKEN__`、`force=true` 都在代码里真实存在；仓库地址与 `git remote` 一致。

### 校验

新增 `python scripts/_poc_n1n2.py`（14 项，先红后绿）：假 Host → 403、跨站 Origin + `text/plain` → 403 且文件不落地、无令牌 `/api/chat` → 401、`?path=..` → 400、页面令牌注入无自伤；同时覆盖四条正常调用回归（同源 POST、无 Origin POST、正常 tree、正常 config）。

新增 `python scripts/_verify_err_msgs.py`（26 项）：A 映射表 13 种异常 → 中文且不含英文类名；B 源码断言 `type(e).__name__` 只出现在日志行；C 起后端打 27 个接口，响应体不得出现英文异常名。

新增 `python scripts/_verify_entries_api.py`（14 项）：入口状态 wired、列目录、读单篇带 `check`、不合规章纲 400 且文件未改写、`force=true` 可存、合规章纲落盘一致、`name=../../` 400、不存在的书 `exists=false` 而非 500。

新增 `python scripts/_verify_triage.py`（8 项）：四类分诊 + 环境段剔除 + `repro_ready` 三要素。

配套回归：`scripts\regression_auth.py` 8/8、`scripts\_repro.ps1` 三用例（polish/entries/billing）PASS、`scripts\_smoke_entries.ps1` 0 fail、`scripts\_check_keys.ps1` SUMMARY PASS。

### 兼容

- 不带 `Origin` 的旧客户端（curl、CI 脚本、`_repro.ps1`）行为不变。
- 需要跨机访问时：设 `NOVELAPP_ALLOW_HOSTS=192.168.1.10`，并让页面 `Origin` 指向同一主机。

## 1.0.0 — 2026-11-17

首个公开版本。**开源免费：无订阅、无充值、无按章计费、无额度。**

### 新增

- **9 个入口**（书架 / 开书 / 写 / 大纲 / 设定库 / 拆书 / 质检 / 文风 / 账单），不新增第十个。
- **拍级预算**：一章拆 8 拍，每拍强制写清「人物 / 物件 / 数字 / 动作 / 地点 / 不许发生」，再交给模型。
- **四关质检**：格式 / 跨章 / 空间 / 时间，交「位置 + 原句 + 改法」清单，不交分数。
- **单拍重跑**：某一拍写坏只重跑那一拍，不用整章重来。
- **拆书**：导入参考书，按 14 维拆解，产物可勾进开书。
- **文风**：5 条预设 + 左右对照；只改你贴进来那段，不落盘、不改章节状态。
- **成本遥测**：每次调用记 `prompt/completion tokens + 估算成本`；账单页只显示「花了多少」，不显示「欠多少」。
- **本地优先**：稿子在本机 `%APPDATA%\novelapp-desktop\data\projects`；模型走你自己的 key 或自建网关。

### 修复

- `/api/polish` 真实 SSE 首帧后 `NameError: send_or_die`（缩进错位成了死代码）——文风改写此前拿不到结果。
- `/api/breakdown/import` 相对路径在打包后必挂（裸 `isfile` 依赖进程 CWD）→ 改为按 projects 根解析。
- 关闭 `thinking` 前，模型会把 `max_tokens` 全烧在 reasoning 上、正文为空（实测 2600 tokens / 0 字 / ¥0.012）。现默认 `thinking.type=disabled`。
- 拍级字数不受控（实测模型超预算 2.2–3.8 倍）→ 按句界截断到 ≤282 字，并记录 `output_raw_chars` 与 `truncated`。

### 移除

- **付费墙**：第 4 章起 402 拦截已删除；`/api/billing/topup|refund` 返回 410；`/api/billing/status` 返回 `{"mode":"free","billing":"disabled"}`。
- **广告位默认关闭**（`data/config/ads.json` 里 `enabled:false`；可关闭、不追踪、不遮正文）。
- **dsh 运行时通道**：`launch_dsh` / `dsh_env` / 两条 `/api/account/dsh*` 路由已删除（发布包内不再含 dsh）。

### 已知限制

- 「大纲」「设定库」两个入口目前走通用文件读写（`/api/tree`、`/api/file`、`/api/save`），**没有专用 API**。
- 第三方组件 7 项许可文本待补（pythonnet / pywebview / clr_loader / setuptools / CPython / WebView2 / VC++ 运行时），清单见 `docs/legal/third-party-notices-v0.md`。
- 只在 Windows + WebView2 验证；macOS/Linux 未测。

### 它凭什么（可复算）

同题四组对照（对照数据不随仓库发布；下表是实测值，方法见 README「它凭什么」）：

| 组 | 输入 | 字数 | 句长 | 段长 | 对话 | 解释句 | 名/他 |
|---|---|---:|---:|---:|---:|---:|---:|
| A | 背景 + plot + 角色卡 | 859 | 10.9 | 17.2 | **0.275** | 0 | 1.27 |
| B | 8 拍模板（旧流水线） | 860 | **15.1** | 22.6 | **0.043** | **3** | **0.00** |
| C | 只有 226 字背景 | 969 | 10.5 | 16.4 | 0.183 | 3 | 0.69 |
| D | 同 C + 我方风格，出整章 | 2025 | 9.9 | 12.1 | **0.273** | **1** | 0.72 |

结论：**B 组的崩不是模型不行，是上游没写情节**（名/他 0.00、对话 0.043）；同一批模型，给了 226 字背景（C）就变成 0.69 / 0.183。

一次真实调用的完整记录（格式如下；原文件在作者本地数据目录，不随仓库发布）：

```
prompt_chars=2900  prompt_tokens=1820  completion_tokens=456  cost=¥0.00365  latency=4.18s
output_chars=280   output_raw_chars=625  truncated=true  usage_source=api
```
