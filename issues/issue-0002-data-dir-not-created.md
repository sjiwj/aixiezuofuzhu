# [bug] 首次启动不会创建数据目录，与 README「首次会建数据目录」不符

> GitHub issue #1  https://github.com/sjiwj/jy/issues/1

## 环境

- Windows 11 26100
- Python 3.15.1
- 起法：`python core\server.py <port> --no-browser`（全新克隆，仓库 546 文件）
- 模拟全新用户：把 `APPDATA` 指到一个不存在的空目录

## 复现

1. 克隆仓库到干净目录
2. 设 `APPDATA=<空目录>`，起后端
3. 读 `/api/health`

## 期望 vs 实际

- 期望（README「三步起壳」第 2 步写的）：**首次会在 `%APPDATA%\novelapp-desktop\data` 下建数据目录**
- 实际：启动后 `data_dir` 与 `projects` 都不存在

```text
1) 启动后 data_dir 存在: False  projects 存在: False
   data_dir = ...\AppData\Local\Temp\appdata-repro\novelapp-desktop\data
2) /api/tree -> 200 {"tree": [], "root": "D:\\_startup-test"}
3) /api/setup/status -> 200 configured = False
4) 新建项目 -> 200 {"ok": true, "path": "projects/我的第一本书", "created": true}
   projects 目录出现: True ['我的第一本书']
5) 新建后 /api/tree -> 200 树节点数 = 1
```

## 影响

- 服务能起、能新建项目，**不是致命问题**；
- 但 `/api/health` 会报 `projects: false`，与 README 描述不符；
- 用户若想手动把已有文稿放进 `projects/`，目录还不存在，需要先点「新建项目」；
- 首次启动时若执行依赖 `data_dir` 的操作（日志、配置写入），会走各自的分支，可能出现「日志写不进去就算了」这类静默降级。

## 建议

启动时确保 `data_dir` 与 `data_dir/projects` 存在（`os.makedirs(..., exist_ok=True)`），
或者把 README 改成「首次新建项目时才会建目录」。

