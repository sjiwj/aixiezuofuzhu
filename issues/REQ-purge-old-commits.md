# GitHub 清除请求：仓库里残留的旧 commit（含客户小说内容）

> 现状：分支 / tag / 搜索索引已干净；但 14 个改 history 前的 commit 仍能凭 SHA 访问，
> 连 codeload 打包下载也返回 200。这部分只能由 GitHub 侧清。

## 提交入口

- 表单：https://support.github.com/contact/private-information
- 备用：https://support.github.com/request （类型选 Repository / Sensitive data）
- 必须用**仓库 owner 账号**（sjiwj）提交，否则不受理

## 已验证仍可达（提交时附上）

```text
GET https://api.github.com/repos/sjiwj/jy/commits/144ad4d          -> 200
GET https://api.github.com/repos/sjiwj/jy/commits/1a66b33          -> 200
GET https://codeload.github.com/sjiwj/jy/tar.gz/144ad4d            -> 200
```

## 英文正文（直接粘进表单）

```text
Subject: Purge unreachable commits that contain private customer novel text

Repository: https://github.com/sjiwj/jy (public, 0 forks)

What happened
Between 2026-11-17 03:10 and 13:59 (+08:00) the repository history contained
private customer content committed by mistake:
  - scripts/fixtures/qc_ok.md and qc_bad.md: verbatim 60-80 character excerpts
    of a customer's unpublished novel
  - config/cliche.json: a customer usage statistic (book title, chapter count,
    character count, measurement date)
  - config/map.json, config/map_bad.json, config/qc_rules.json,
    scripts/structure_anchors.json: real place and character names
  - 73 source files: docstring examples naming the customer's book

What I already did
On 2026-11-17 14:00 (+08:00) I rewrote all history with git filter-branch and
force-pushed refs/heads/main, refs/tags/v1.0.0 and refs/tags/v1.0.1.
A fresh mirror clone plus a per-commit git grep over every reachable commit
now returns zero matches for all of the above strings.

What I need
The following now-unreachable commits are still retrievable by SHA, and
codeload still serves their trees as tarballs. Please run garbage collection /
purge cached objects and cached archives for this repository:

  10cdeeb829c83683463ae8ed0a7dc8afc9b95d11
  144ad4dc450e471ab2940ac847196ddb7a9d9c93
  1a66b33b14f0dce80de48e141850a60116dd9704
  2a003099b74af1df0d885bfebb449acf157a069e
  2d06693fe00f48a5b79d8abd2bdd9111dfe86642
  2e5b167c60742d669f41e089bb07cabfa3537fac
  2ef4ac832bb9c671f6a783e0d0e54b773d82f990
  445e3f4e28de6433e30d4e0d5ec958855cab6aca
  48905e26e4567e98754e784b362f231ccef353c2
  88f0acf84a849176846911a9ecd1fe6efa562bf4
  8e226cc50a78563cffe79e5c4580951b99eed45d
  92dad6cf216000745959242cd5c24dde69d88753
  94fbad0fd061f5a95607c9130d682bd1cd347d71
  a04fb972fe98cd2f87031fd7dd763027c2d54f9c

Evidence they are still served:
  GET /repos/sjiwj/jy/commits/144ad4d                  -> 200
  GET /repos/sjiwj/jy/commits/1a66b33                  -> 200
  https://codeload.github.com/sjiwj/jy/tar.gz/144ad4d  -> 200

Additional context
  - forks_count is 0, so no fork keeps a copy of the old history.
  - The repository has no stars and no release assets that depend on the old
    commits; v1.0.1 was re-pointed to the rewritten tag.
  - The content is a third party's unpublished novel draft; it must not remain
    retrievable.

Thank you.
```

## 中文摘要（自己留档）

- 泄露时间窗：2026-11-17 03:10 ~ 13:59（约 11 小时）
- 泄露性质：客户未发表小说正文片段 + 书名 + 统计 + 地名人物名；**无任何密钥**
- 已做：全仓脱敏、改写 17 个 commit、重建两个 tag、强推、加发布前隐私门禁
- 未做（GitHub 侧）：清除 14 个 unreachable commit 的缓存对象与打包缓存
- 受理后验证：上述三个 URL 全部返回 404

## 附：需清除的 14 个完整 SHA

```text
  10cdeeb829c83683463ae8ed0a7dc8afc9b95d11
  144ad4dc450e471ab2940ac847196ddb7a9d9c93
  1a66b33b14f0dce80de48e141850a60116dd9704
  2a003099b74af1df0d885bfebb449acf157a069e
  2d06693fe00f48a5b79d8abd2bdd9111dfe86642
  2e5b167c60742d669f41e089bb07cabfa3537fac
  2ef4ac832bb9c671f6a783e0d0e54b773d82f990
  445e3f4e28de6433e30d4e0d5ec958855cab6aca
  48905e26e4567e98754e784b362f231ccef353c2
  88f0acf84a849176846911a9ecd1fe6efa562bf4
  8e226cc50a78563cffe79e5c4580951b99eed45d
  92dad6cf216000745959242cd5c24dde69d88753
  94fbad0fd061f5a95607c9130d682bd1cd347d71
  a04fb972fe98cd2f87031fd7dd763027c2d54f9c
```