# 小说创作工作台（NovelApp）

> 本地优先的 AI 小说创作工作台。**开源免费**：没有订阅、没有按章计费、没有额度。
> 稿子存在你自己电脑上；模型用你自己的 key（或自建本地网关）。

## 三步起壳

```powershell
# 1) 依赖（Python 3.13+；WebView2 运行时 Windows 10/11 自带）
pip install pywebview pythonnet cryptography

# 2) 起壳（首次会在 %APPDATA%\novelapp-desktop\data 下建数据目录）
$env:NOVELAPP_PORT = '8770'
python core\desktop.py --dev

# 3) 浏览器/窗口里打开 http://127.0.0.1:8770 ，按向导填模型 key
```

> 仓库**不带示例书**（`projects/` 不随仓库发布）：首次打开是空状态，按「开书」向导建第一本即可。

> 仓库**不带示例书**（`projects/` 不随仓库发布）：首次打开是空状态，按「开书」向导建第一本即可。

## 模型怎么接

两条路，任选：

1. **自建网关（推荐，成本可核）**：本机跑一个兼容 OpenAI 的网关，监听 `127.0.0.1:3000`，
   应用默认指向 `http://127.0.0.1:3000/v1`。
2. **直连厂商**：在设置里把 base 改成厂商地址并填自己的 key。

> 关键：**模型费用由你自己付给厂商或网关，本项目不代收、不加价**。账单页显示的是
> 你自己的用量与估算成本（`cost_cny`），不是收费单。

## 九个入口

书架 / 开书 / 写 / 大纲 / 设定库 / 拆书 / 质检 / 文风 / 账单——不新增第十个。

- **写**：一章拆 8 拍，每拍先写清「谁、拿什么、多少钱、在哪、做什么、不许做什么」，再交给模型；写坏了只重跑那一拍。
- **质检**：格式 / 跨章 / 空间 / 时间四关，交「位置 + 原句 + 改法」清单，不交分数。
- **文风**：5 条预设 + 左右对照，只改你贴进来的那段，不落盘、不改章节。
- **拆书**：导入一本参考书，按 14 维拆解，产物可直接进开书。
- **账单**：逐次调用明细（tokens / 模型 / 估算成本），只读本地账本。

## 它凭什么（三条可复算的证据）

### 1. 同一批模型，崩的是上游不是模型

同题四组对照（同一段设定、同一批模型，只换上游输入；**对照数据不随仓库发布**，方法是公开的）：

| 组 | 输入 | 字数 | 句长 | 段长 | 对话 | 解释句 | 名/他 |
|---|---|---:|---:|---:|---:|---:|---:|
| A | 背景 + plot + 角色卡 | 859 | 10.9 | 17.2 | **0.275** | 0 | 1.27 |
| B | 8 拍模板（旧流水线） | 860 | **15.1** | 22.6 | **0.043** | **3** | **0.00** |
| C | 只有 226 字背景 | 969 | 10.5 | 16.4 | 0.183 | 3 | 0.69 |
| D | 同 C + 我方风格，出整章 | 2025 | 9.9 | 12.1 | **0.273** | **1** | 0.72 |

**B 组名/他 0.00、对话 0.043**：模型不是不会写人物，是上游只给了「第一次受阻 / 代价或损失」这种标签，它只能自己编。

### 2. 自己的硬线，自己先过

一章成品实测（`tools/review_panel.py` 在**你自己的书**上复算，命令见下）：

```
字数 3418   段数 154   平均段长 22.2   平均句长 13.6
对话占比 0.178   最长段 109   破折号 1
```

对 `meta/style-anchor.md` 的 5 条硬线：句长过、段长过、**最长段 109 不过（≤100）**、**对话 0.178 不过（≥0.25）**、**破折号 1 不过（0）**。
把不过的地方写出来，比说「文风好」有用——这也是 1.0.0 的已知缺口，`CHANGELOG` 里同样列着。

### 3. 一次真实调用，成本可核到分

一次真实调用的样例（原文件在你自己的数据目录，格式如下）：

```
prompt_chars=2900   prompt_tokens=1820   completion_tokens=456
cost=¥0.00365   latency=4.18s   output_chars=280   output_raw_chars=625   truncated=true
```

复算命令：

```powershell
cd D:\NovelApp
# 换成你自己项目里任意一章
python -X utf8 -c "import sys;sys.path.insert(0,'tools');import review_panel as R;t=R.read(r'projects/<书名>/章节/<文件>.md');print(R.metrics(t))"

# 出一份拍级任务单（同样换成你自己的书）
python -X utf8 tools\prompt_render.py --book "projects\<书名>" --chapter 2 --style plain-clean --requirement coherent-continue --beat 1
```

## 免费到什么程度

全部功能免费，无功能墙。仓库里没有付费闸：`GET /api/billing/status` 返回
`{"mode":"free","billing":"disabled"}`，`/api/billing/topup|refund` 返回 410。

广告位代码在、**默认关闭**（`data/config/ads.json` 里 `enabled:false`）：可关闭、不追踪、不遮正文。

## 现在怎么活（热度期：暂不收费）

当前不卖任何东西：无订阅、无充值、无按章计费、无额度。

以后的路径是公开的：赞助 / 一次部署服务 / 小班培训 / 固定包位广告。
但**先有热度再谈钱**——现在只关心一件事：有人真的用它写完一章，并且愿意提 issue。

## 许可与商标

- 代码：**Apache License 2.0**（`LICENSE` 全文；`NOTICE` 为版权与第三方说明）。
- **名称与 Logo 不随代码授权**（Apache-2.0 §6）：可以 fork、可以改、可以商用，
  但不要用「小说创作工作台 / NovelApp」的名字与图标去分发，也不要暗示作者背书。
- 随包第三方组件各受其许可证约束，见 `docs/legal/third-party-notices-v0.md`。

## 贡献

- 质量口径看两个地方：`CHANGELOG.md` 的「已知限制」，以及 `tools/review_panel.py` 的实际实现（指标就是代码里那几个公式）。
- 第三方许可见 `docs/legal/third-party-notices-v0.md`。
- 改动请附「命令 + 输出」证据；本仓库不接受只有描述没有复现的 PR。
- 不接：平台币/双轨账务、社区、多端、多模态、任何「绕过平台审核」的功能。

## 免责

本软件按「现状」提供，不附带担保。生成内容的合规性（含平台对 AI 生成内容的标注要求）、
著作权与发布风险由使用者负责。导出时自动附「正文可能包含 AI 辅助生成内容，发布前请自行核验」。

---

## 附录 A · 冷启动自检（新机器，3 分钟）

```powershell
# 1) 依赖（装到全局或 venv；见附录 E 的坑）
python -m pip install pywebview pythonnet cryptography

# 2) 起壳
$env:NOVELAPP_PORT = '8770'
python core\desktop.py --dev

# 3) 自检三条（另开一个窗口）
curl.exe -s http://127.0.0.1:8770/api/health
curl.exe -s http://127.0.0.1:8770/api/entries
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8770/
```

通过标准（2026-11-17 实测，干净目录 + 空数据目录）：

| 检查 | 期望 |
|---|---|
| `/api/health` | `{"ok": true, "root": "...\\novelapp-desktop\\data", "projects": false, ...}`（`projects:false` 表示还没有书，正常） |
| `/api/entries` | `{"counts": {"wired": 2, "ui_only": 5, "missing": 2}}`（9 个入口） |
| `GET /` | `200`，约 121k 字符 |
| 首启耗时 | ≤ 2 秒（实测 1 秒） |

## 附录 B · 网关 3000 不通（最常见）

症状：写章/润色报 `URLError [WinError 10061] 由于目标计算机积极拒绝`，或 `key_source` 为空。

```powershell
Test-NetConnection 127.0.0.1 -Port 3000 -InformationLevel Quiet
netstat -ano | findstr :3000
Get-Process new-api -ErrorAction SilentlyContinue | Select-Object Id,StartTime
pwsh -NoProfile -File D:\relay\start-new-api.ps1
curl.exe -s -H "Authorization: Bearer <你的sk-key>" http://127.0.0.1:3000/v1/models
```

| 现象 | 原因 | 处理 |
|---|---|---|
| 端口 False、无进程 | 没人拉起（自启只在登录触发一次） | 手动跑启动脚本；或加计划任务每 5 分钟探测 |
| 端口 True 但 401 | key 不对/不是同一个网关 | 见附录 D |
| `EADDRINUSE` | 已有实例或别的程序占了 3000 | `netstat -ano` 找 PID，确认后结束或改端口 |
| 日志报 `TRUSTED_PROXIES is unset` | 只是警告 | 忽略；要反代再配 |

## 附录 C · 网关数据库（SQLite）

看启动日志里的两行：

```
system is already initialized at: <时间>     → 已有库，直接起
database migration started                    → 正在迁移，等它结束
```

| 现象 | 处理 |
|---|---|
| `database is locked` | 先关掉所有 new-api 进程，再起；迁移期间不要双开 |
| 迁移卡住/报错 | 备份 `new-api.db` 后重启；仍失败再考虑还原备份 |
| 目录只读（装在 Program Files） | 把 `SQLITE_PATH`/`LOG_DIR` 指到可写路径 |
| 想换库/清库 | **先备份**：`Copy-Item new-api.db new-api.db.bak-<日期>`；本应用不碰这个库 |

## 附录 D · key 无效（401/403）

本应用有**两套不同的凭据**，别混：

| 凭据 | 位置 | 用途 | 失效表现 |
|---|---|---|---|
| 网关 sk 令牌 | `%APPDATA%\novelapp-desktop\data\config\user_token.json` | 调模型 | 写章报 401 |
| new-api 账号会话 | 网关自己的登录态 | 余额/用量 | 余额页 401，**不影响写作** |

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" -H "Authorization: Bearer <sk-key>" http://127.0.0.1:3000/v1/models
```

余额/用量 401 时，应用自动回退本地账本（`source: "local_ledger"`），账单页仍可看自己的消耗。

## 附录 E · 依赖与运行时（两个真实踩过的坑）

1. **`ModuleNotFoundError: No module named 'webview'`**
   依赖装在**用户级** `site-packages`（`%APPDATA%\Python\Python3xx\site-packages`）。
   把 `APPDATA` 指到别处（换用户/做冷启动实验），这个路径也跟着变，包就找不到。
   - 正解：用 venv（`python -m venv .venv` 后 `.venv\Scripts\python core\desktop.py`）；
   - 临时：设 `PYTHONUSERBASE` 指回原用户目录，再起壳。
2. **窗口白屏/起不来，但 HTTP 200**
   缺 WebView2 运行时（老 Win10）。装 Microsoft Edge WebView2 Evergreen Runtime 后重开。

## 附录 F · 端口被占

```powershell
netstat -ano | findstr :8770
$env:NOVELAPP_PORT = '8799'   # 换个端口，不用改代码
```
