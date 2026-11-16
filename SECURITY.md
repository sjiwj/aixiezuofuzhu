# 安全说明

## 报告漏洞

请用 GitHub Security Advisory（仓库 → Security → Report a vulnerability）或提 issue 时勾选"安全"标签。
**不要**在公开 issue 里贴可直接利用的 PoC。

## 威胁模型

本应用是**本地桌面程序**：只监听 `127.0.0.1`，数据在 `%APPDATA%\novelapp-desktop\data`，模型走用户自己的 key。

保护目标：①用户稿件不被任意网页读写；②用户模型额度不被盗用；③本地配置文件（含网关令牌）不被外带。

**不在保护范围**：已获得本机 shell 的攻击者（那已经越过边界）；Windows 账户级隔离。

## 已知问题（2026-11-17 红队自测，v1.0.0）

| 编号 | 严重度 | 问题 | 复现（本机） | 临时缓解 |
|---|---|---|---|---|
| N1 | 高 | **未校验 `Host` 头** → DNS rebinding：攻击者域名解析到 127.0.0.1 后可同源读写应用接口 | `curl -H "Host: evil.example" http://127.0.0.1:8770/api/config` → 200 | 用应用时别开不可信网页；或把端口改成非常用值 |
| N2 | 高 | **未校验 `Origin`** 且写接口接受任意 Content-Type → CSRF 写文件 | `curl -H "Origin: https://evil.example" -H "Content-Type: text/plain" -d '{"path":"projects/x.md","content":"y"}' /api/save` → 200，文件落地 | 同上 |
| N3 | 中 | `/api/chat` 未要求登录态，返回 200 并回显上游错误原文 | 未登录 POST `/api/chat` → 200 SSE，含 `HTTPError: ... 500` | 有令牌时别在浏览器里开应用的同时访问不可信站点 |
| N4 | 低 | `OPTIONS` 返回 501（无预检处理） | `curl -X OPTIONS /api/save` → 501 | 无需处理 |
| N5 | 低 | `/api/tree?path=..` 静默归一化到 projects，而非报错 | `curl "/api/tree?path=.."` → 200 | 无需处理 |

已确认**不存在**：目录穿越读写（`..%2F..`、`../../`、绝对路径全部 400）；`/api/setup/save` 非法载荷 400。

## 修复计划

N1/N2 的修法（约 30 行，进入 v1.0.1）：`Host` 白名单（`127.0.0.1` / `localhost` / `[::1]`）+ 所有 POST 校验 `Origin`（缺省或同源放行）+ 写接口强制 `application/json`。

N3：`/api/chat` 无令牌返回 401；N5：`..` 直接 400。

## 收窄攻击面的建议（给使用者）

1. 不要把应用端口暴露到局域网（默认只绑 127.0.0.1，别改）。
2. `%APPDATA%\novelapp-desktop\data\config\user_token.json` 与 `data\config\ads.json` 不要发给别人。
3. 关闭应用后再浏览不明站点，是当前最省事的缓解。
