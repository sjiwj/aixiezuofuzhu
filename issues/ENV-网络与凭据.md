# 本机环境：GitHub 访问、凭据与代理（2026-11-17 实测）

> 用途：下次 push 失败时先看这份，别重复排查。

## 一、代理（这是 403 之外的另一半原因）

```
DNS       github.com → 198.18.3.93   （fake-ip，本机 TUN 代理段）
现象      git push/ls-remote 卡在 schannel 握手 step 2/3，21 秒超时
          curl 同一域名 200（2.16s）—— 两条栈路径不同
可用代理  http://127.0.0.1:10968     （进程 llg-network-core）
```

已写进全局配置，只作用于 github.com：

```powershell
git config --global http.https://github.com/.proxy http://127.0.0.1:10968
```

**不要**改成全局 `http.proxy`，会影响其它仓库和本地服务。

如果 10968 变了：`netstat -ano | findstr LISTENING` 配合进程名 `llg-network-core` 重新找端口。

## 二、凭据（两种，别混）

| 类型 | 前缀 | 能力 | 现状 |
|---|---|---|---|
| fine-grained PAT | `github_pat_`（93 字符） | 只读：能读 API、读分支保护 403、push 403 | 已不在使用 |
| OAuth（GitHub CLI 设备流） | `gho_`（40 字符） | scope `repo`，push 已验证 | **当前生效** |

`gho_` 是 OAuth token，不是 PAT：
- 撤销位置：GitHub → Settings → Applications → Authorized OAuth Apps → GitHub CLI → Revoke
- 存在 Windows 凭据管理器 `LegacyGeneric:target=git:https://github.com`
- 清除：`cmdkey /delete:LegacyGeneric:target=git:https://github.com`

## 三、重新授权（凭据失效时）

```powershell
cd D:\NovelApp
$env:HTTPS_PROXY = 'http://127.0.0.1:10968'
$env:HTTP_PROXY  = 'http://127.0.0.1:10968'

python scripts\_auth_device_flow.py --start     # 打印 USER_CODE
# 浏览器打开 https://github.com/login/device 输入代码并 Authorize
python scripts\_auth_device_flow.py --poll      # 换 token → 验 push → 存凭据
```

`--poll` 成功时最后一行是 `READY=1`。

## 四、验证三连（凭据或代理动过就跑）

```powershell
git ls-remote origin HEAD                              # 能读到 144ad4d...
git push --dry-run origin main                         # 不能出现 403 Permission denied
git push --dry-run origin HEAD:refs/heads/__permcheck__ # 应显示 [new branch]，远端不会真多分支
```

## 五、坑

1. `git ls-remote` 走匿名只能读 public 仓库，**不能证明有写权限**；必须用 `HEAD:refs/heads/xxx` 的 dry-run。
2. `credential.helper=manager` 会把旧凭据一直吐出来；换 token 后若仍 403，先 `cmdkey /delete` 再重试。
3. 本机 git 的 libcurl 是 debug build（日志会打 `WARNING: This is a debug build of libcurl`），TLS 行为与系统 curl 不同，别拿 curl 通不通判断 git 通不通。
