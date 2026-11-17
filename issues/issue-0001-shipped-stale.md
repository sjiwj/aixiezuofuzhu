# [bug] `/api/entries` 说发布包"存在"，但那是 11-05 的旧包（56KB），会误导人直接用

## 环境

- Windows 版本：Windows 11 26100
- Python 版本（`python -V`）：Python 3.15.1
- 起壳方式：`python core\server.py 8770 --no-browser`（也试过 `core\desktop.py --dev`）
- 网关：自建 new-api v1.0.0-rc.47，`http://127.0.0.1:3000/v1`

## 复现步骤

1. 起后端：`python core\server.py 8770 --no-browser`
2. 读入口报告：`curl -s http://127.0.0.1:8770/api/entries`
3. 看返回里的 `shipped_present` / `shipped_bytes` / `server_source_bytes`

## 期望 vs 实际

- 期望：发布包比源码旧时，报告里要能看出来（比如 `shipped_stale: true` + 一句"别用这个包"），
  因为交接单第 4 节明确写了「不要用 `发布桌面版\NovelAppDesktop.exe`：11-05 的旧包（server.py 56KB），今天的修复都不在」。
- 实际：`shipped_present: true`，`shipped_bytes: 56858`，`server_source_bytes: 253296`，
  没有 `shipped_stale` 字段，也没有任何"过期"提示。光看这一行会以为发布包是最新的。

实测证据：

```text
$ curl -s -w "\nHTTP %{http_code}\n" http://127.0.0.1:8770/api/entries | tail -2
HTTP 200

$ curl -s http://127.0.0.1:8770/api/entries | python -c "import sys,json;d=json.load(sys.stdin);print({k:d[k] for k in ('shipped_present','shipped_bytes','server_source_bytes','shipped_path')})"
{'shipped_present': True, 'shipped_bytes': 56858, 'server_source_bytes': 253296, 'shipped_path': 'D:\\NovelApp\\发布桌面版\\core\\server.py'}
```

比例：source/shipped = 4.45x。也就是说这个"发布包"少了 78% 的代码（含 v1.0.1 的 N1/N2 修复）。

## 影响

- 拿 `/api/entries` 当期报告做验收的人，会以为发布包已同步；
- 实际把它发给用户 = 发一个**已知有 Host rebinding / CSRF 两个高危**的版本。

## 期望行为

`/api/entries` 增加过期判定，建议判据：

```
shipped_stale = shipped_present and shipped_bytes < server_source_bytes * 0.8
```

并附 `shipped_note`，值为「发布包是旧版（56KB vs 253KB），先重新构建再用」。

## 自检结果

```powershell
pwsh -NoProfile -File scripts\_check_keys.ps1
# SUMMARY PASS
```
