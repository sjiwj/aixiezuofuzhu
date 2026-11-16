# CHANGELOG

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
