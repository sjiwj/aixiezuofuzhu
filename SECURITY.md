# 安全说明

## 报告漏洞

请用 GitHub Security Advisory（仓库 → Security → Report a vulnerability）或提 issue 时勾选"安全"标签。
**不要**在公开 issue 里贴可直接利用的 PoC。

## 威胁模型

本应用是**本地桌面程序**：只监听 `127.0.0.1`，数据在 `%APPDATA%\novelapp-desktop\data`，模型走用户自己的 key。

保护目标：①用户稿件不被任意网页读写；②用户模型额度不被盗用；③本地配置文件（含网关令牌）不被外带。

**不在保护范围**：已获得本机 shell 的攻击者（那已经越过边界）；Windows 账户级隔离。

## 红队自测与修复状态（v1.0.0 发现 → v1.0.1 修复）

| 编号 | 严重度 | 问题 | 原复现（v1.0.0，本机） | 状态 |
|---|---|---|---|---|
| N1 | 高 | 未校验 `Host` 头 → DNS rebinding：攻击者域名解析到 127.0.0.1 后可同源读写接口 | `curl -H "Host: evil.example" http://127.0.0.1:8770/api/config` → 200 | **已修**：非回环 Host → 403 |
| N2 | 高 | 未校验 `Origin` 且写接口接受任意 Content-Type → CSRF 写文件 | `curl -H "Origin: https://evil.example" -H "Content-Type: text/plain" -d '{"path":"projects/x.md","content":"y"}' /api/save` → 200，文件落地 | **已修**：跨站 Origin → 403；非 `application/json` → 403；文件不落地 |
| N3 | 中 | `/api/chat` 未要求令牌，未登录也能打上游 | 未登录 POST `/api/chat` → 200 SSE | **已修**：无 `X-Novelapp-Token` → 401 |
| N4 | 低 | `OPTIONS` 返回 501（无预检处理） | `curl -X OPTIONS /api/save` → 501 | 保留：不发 CORS 头，浏览器预检失败即不放行，无需伪造成功预检 |
| N5 | 低 | `/api/tree?path=..` 静默归一化到 projects，而非报错 | `curl "/api/tree?path=.."` → 200 | **已修**：越界 → 400 |

已确认**不存在**：目录穿越读写（`..%2F..`、`../../`、绝对路径全部 400）；`/api/setup/save` 非法载荷 400。

## 复验

```powershell
cd D:\NovelApp
python scripts\_poc_n1n2.py        # 12 项，全 PASS 才算修好
python scripts\regression_auth.py  # 8/8（token 模式）
pwsh -NoProfile -File scripts\_repro.ps1 -Case polish -Port 8797
pwsh -NoProfile -File scripts\_check_keys.ps1
```

## 入口防护实现（v1.0.1）

- `H._guard()` 在鉴权之前执行，顺序固定：`Host` 白名单 → `Origin` 同源 → 写请求 `application/json`。
- Host 白名单：`127.0.0.1` / `localhost` / `::1`；额外主机用 `NOVELAPP_ALLOW_HOSTS`（逗号分隔）显式开白。
- Origin 校验只作用于 POST/PUT/PATCH/DELETE：`Origin` 缺省放行（curl、CI、`_repro.ps1` 照旧可用）；存在则必须是 `http(s)://回环主机:本端口`；`Sec-Fetch-Site: cross-site` 直接拒。
- `/api/chat` 令牌：`NOVELAPP_BACKEND_TOKEN` 优先，否则用进程内随机令牌，由 `_index()` 注入到页面（`window.__NVL_TOKEN__`），页面所有 `/api/` 请求自动带 `X-Novelapp-Token`。

## 收窄攻击面的建议（给使用者）

1. 不要把应用端口暴露到局域网（默认只绑 127.0.0.1，别改；确需跨机访问，用 `NOVELAPP_ALLOW_HOSTS` 精确开白）。
2. `%APPDATA%\novelapp-desktop\data\config\user_token.json` 与 `data\config\ads.json` 不要发给别人。
3. 关掉应用再去逛不明站点，仍是最省事的第二道防线。
