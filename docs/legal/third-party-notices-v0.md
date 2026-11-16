# 第三方组件与许可证清单 v0

> 生成日期：2026-11-17
> 适用范围：`D:\NovelApp\发布桌面版\`（PyInstaller 打包产物：`NovelAppDesktop.exe` 6,408,029 字节 + `_internal\`）
> 取证方式：只读实读 `_internal\` 下的 `*\dist-info\METADATA`、`*\dist-info\licenses\*`、`deps.json`、DLL 版本信息；**版本与许可证名一律来自实读，读不到写 UNKNOWN 并列出找过的路径**。
> 前置事实：`_internal\` 与 `NovelAppDesktop.exe` 内递归名搜索 `dsh|asar|LICENSE-deepseek-harness` 命中 **0**（见"底座结论"第 1 条），即当前发布包**不再分发 dsh 代码**。

---

## 一、组件表（Name / Version / License / 证据路径）

| # | Name | Version | License | 证据路径（实读） |
|---|---|---|---|---|
| 1 | cryptography | 50.0.2 | **Apache-2.0 OR BSD-3-Clause**（METADATA `License-Expression` 原文） | `_internal\cryptography-50.0.2.dist-info\METADATA` → `Name: cryptography` / `Version: 50.0.2` / `License-Expression: Apache-2.0 OR BSD-3-Clause` / `License-File: LICENSE` `LICENSE.APACHE` `LICENSE.BSD` |
| 2 | MarkupSafe | 3.0.4 | **BSD-3-Clause** | `_internal\markupsafe-3.0.4.dist-info\METADATA` → `Name: MarkupSafe` / `Version: 3.0.4` / `License-Expression: BSD-3-Clause`；`licenses\LICENSE.txt` 首行 `Copyright 2010 Pallets` |
| 3 | pyreadline3 | 3.5.6 | **BSD**（METADATA `License: BSD`，许可正文自称 "BSD-type license"） | `_internal\pyreadline3-3.5.6.dist-info\METADATA` → `Name: pyreadline3` / `Version: 3.5.6` / `License: BSD`；`licenses\LICENSE.md` → `Copyright (c) 2020 Bassem Girgis` |
| 4 | pythonnet（程序集 `Python.Runtime`） | 3.2.1 | **UNKNOWN** | `_internal\pythonnet\runtime\Python.Runtime.deps.json` → `"Python.Runtime/3.2.1"`；`Python.Runtime.dll` VersionInfo `ProductVersion: 3.2.1`；**无 dist-info、无 METADATA、无 LICENSE 文件** |
| 5 | pywebview | **UNKNOWN** | **UNKNOWN** | 目录 `_internal\webview\`（`js\*.js`、`lib\runtimes\win-*\native\WebView2Loader.dll`、`lib\Microsoft.Web.WebView2.*.dll`、`pywebview-android.jar`）存在；**无 dist-info / 无 METADATA / 无 LICENSE**；`.py` 与版本串在 PyInstaller 归档内，`_internal` 层读不到 |
| 6 | clr_loader | **UNKNOWN** | **UNKNOWN** | `_internal\clr_loader\ffi\dlls\amd64\ClrLoader.dll`（10,752 B）、`x86\ClrLoader.dll`（10,752 B）；**无元数据文件** |
| 7 | setuptools | **UNKNOWN** | **UNKNOWN** | 仅残留 `_internal\setuptools\_vendor\jaraco\text\Lorem ipsum.txt`；**无 `setuptools-*.dist-info`、无 METADATA** |
| 8 | CPython 运行时 | 3.15.1 | **UNKNOWN**（版权串已实读，许可证文件未随包） | `_internal\python315.dll` VersionInfo → `FileVersion: 3.15.1`、`LegalCopyright: Copyright © 2001 Python Software Foundation. Copyright © 2000 BeOpen.com. ...`；`_internal\` 内**未见 `LICENSE.txt` / `PYTHON-LICENSE`** |
| 9 | Microsoft WebView2 SDK（`Microsoft.Web.WebView2.Core.dll` / `.WinForms.dll` / `WebView2Loader.dll`） | **UNKNOWN** | **UNKNOWN** | `_internal\webview\lib\Microsoft.Web.WebView2.Core.dll`（649,800 B）、`...WinForms.dll`（39,016 B）、`lib\runtimes\win-{arm64,x64,x86}\native\WebView2Loader.dll`；**包内无微软许可文件** |
| 10 | VC++ 运行时（`VCRUNTIME140.dll` / `VCRUNTIME140_1.dll` / `ucrtbase.dll`） | **UNKNOWN** | **UNKNOWN** | `_internal\VCRUNTIME140.dll`（178,616 B）、`_internal\VCRUNTIME140_1.dll`（50,112 B）、`_internal\ucrtbase.dll`（1,124,152 B）；**包内无许可文件** |

### UNKNOWN 项找过的路径（全部实读，均无结果）

```
_internal\*\METADATA                                  （仅 3 个包有：cryptography / markupsafe / pyreadline3）
_internal\*\PKG-INFO                                  （0 个）
_internal\*\licenses\*                                （仅上述 3 个包）
_internal\webview\                                     （只有 js/ lib/，无 __init__.py、无元数据）
_internal\clr_loader\                                  （只有 ffi\dlls\，无元数据）
_internal\setuptools\                                  （只剩 _vendor\jaraco\text\Lorem ipsum.txt）
D:\NovelApp 下 pywebview*/clr_loader*/setuptools* 的 dist-info / egg-info（深 4 层递归，0 个）
D:\NovelApp 下的 venv / .venv / site-packages 目录      （0 个）
NovelAppDesktop.exe 内 ASCII 与 UTF-16 串 'pywebview' / 'clr_loader' / 'setuptools' 带版本号模式 （0 命中）
```

---

## 二、三条合规义务结论（按实读到的许可正文写，不按印象）

### 结论 1：二进制分发必须"随包携带许可证全文 + 版权行"，且**不许在打包脚本里删 dist-info**

实读依据：

- `cryptography\licenses\LICENSE`：`This software is made available under the terms of *either* of the licenses found in LICENSE.APACHE or LICENSE.BSD.` —— 即**二选一**，选哪份就带哪份全文。
- `cryptography\licenses\LICENSE.BSD`：`Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.`
- `markupsafe\licenses\LICENSE.txt`：`Redistributions of source code must retain the above copyright` … 第 2 条同样要求二进制形式复制版权声明、条件与免责声明到文档或随附材料。
- `pyreadline3\licenses\LICENSE.md`：`pyreadline3 is released under a BSD-type license.` + `Copyright (c) 2020 Bassem Girgis`。

落地要求：

1. `_internal\cryptography-50.0.2.dist-info\`、`_internal\markupsafe-3.0.4.dist-info\`、`_internal\pyreadline3-3.5.6.dist-info\` **三个目录必须原样保留在发布包里**（它们就是"随附材料"），打包脚本删任何 `*.dist-info` 都等于违约。
2. 安装目录根下一份人类可读的 `THIRD-PARTY-NOTICES.txt`（由本文件生成），列出上表 1–10 项并附 1–3 项许可证全文。
3. cryptography 建议选定 **BSD-3-Clause** 路径（`LICENSE` + `LICENSE.BSD` 两份都带即可覆盖二选一），因为 Apache-2.0 还要另附 NOTICE 与修改声明，成本更高。

### 结论 2：不得用上游作者/组织名义为自家产品背书

实读依据：

- `cryptography\licenses\LICENSE.BSD` 第 3 条：`Neither the name of PyCA Cryptography nor` … （后接 the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission）。
- `markupsafe\licenses\LICENSE.txt`：版权人为 `Copyright 2010 Pallets`；`pyreadline3\licenses\LICENSE.md`：版权人为 `Copyright (c) 2020 Bassem Girgis`。

落地要求：

1. 对外文案禁止出现"PyCA / Pallets / pythonnet 团队 / pywebview 作者 官方支持、联合开发、推荐、背书"这类措辞（与 `宣传与合规.md` 既有的"不能说 DeepSeek 官方/合作/授权"同一口径，只是对象从 DeepSeek 换成组件作者）。
2. 可以说的是"使用了开源组件 X（许可证 Y）"，这是事实陈述，不是背书暗示。

### 结论 3：当前包内**缺 7 项许可证文本**，发布前必须补齐，否则"随二进制复制许可"这条通行要求不满足

实读状态：

- 已有：cryptography、MarkupSafe、pyreadline3（3 项，带 METADATA + licenses 目录）。
- **缺失**：pythonnet(4)、pywebview(5)、clr_loader(6)、setuptools(7)、CPython 运行时(8)、WebView2 SDK(9)、VC++ 运行时(10)——**包内一个许可文件都没有**（`_internal` 递归 `LICENSE*` / `COPYING*` / `NOTICE*` 只命中上面 3 个包的 licenses 目录）。

落地要求：

1. 构建期从各自上游取许可证全文，落到 `安装根\licenses\` 下（文件名 `<组件>-<版本>-LICENSE.txt`），并在 `THIRD-PARTY-NOTICES.txt` 索引。
2. CPython 3.15.1 的 PSF License 尤其不能漏：`python315.dll` 的 `LegalCopyright` 已实读为 `Copyright © 2001 Python Software Foundation.`，PSF 许可要求保留该声明。
3. 第 4/5/6/7 项在补齐前，对外文案**不得**声称"第三方组件许可齐全 / 合规已闭环"——只能写"第三方组件清单见 THIRD-PARTY-NOTICES（部分组件许可证待补）"。

---

## 三、底座结论（与 `宣传与合规.md` 修订配套）

1. **发布包已无 dsh**：`发布桌面版\` 递归名搜索 `dsh|asar|LICENSE|THIRD`，命中仅 `_internal\*\dist-info\licenses\*` 三项（cryptography / markupsafe / pyreadline3），**无 `LICENSE-deepseek-harness.txt`、无 `LICENSES.chromium.html`、无 `app.asar*`、无 `@deepseek-ai`**。→ MIT 二次开发的**分发义务在当前产物上不成立**（因为没分发 dsh 代码）。
2. **开发树仍留有 dsh 痕迹**：`D:\NovelApp\dsh-src\` 存在；`core\*.py` 大小写敏感统计 `dsh` 17 处、`DSH` 13 处、`asar` 2 处、`Electron` 2 处，分布在 `coordinator.py` / `server.py` / `stages.py` / `test_api.py` / `review_history.py` / `text_index.py`。其中 `server.py:1272 def launch_dsh()` / `:2617 /api/account/dsh-env` / `:2886 /api/account/dsh/launch` 是**可执行代码路径**（读 `config.dsh.command` 启动 DSH 子进程），与"放弃 dsh 底座"的决定存在张力。→ 属实现层待决策项，本文件只记录不改（`core\` 禁写）。
3. **`web\index.html` 无任何许可/底座表述**：`dsh|DSH|asar|electron|Electron|MIT|许可|版权` 逐词大小写敏感检索均为 **0**；仅 `deepseek` 出现在模型服务商配置（`:332`、`:340`、`:1241`、`:1242`、`:1640`），那是 API 供应商名，不是底座声明，**不建议改**。

---

## 四、未验证项（明确标注，不冒充已核）

- pywebview / clr_loader / setuptools 的**版本号与许可证名**：包内无元数据、exe 归档未解包 → UNKNOWN。
- WebView2 SDK 与 VC++ 运行时的**许可证条款**：包内无许可文件，未联网取上游条款 → UNKNOWN。
- pythonnet 的许可证类型（MIT 系）**未从包内任何文件读到**，表内不得写成 MIT → 保持 UNKNOWN。
- `pyreadline3\licenses\LICENSE.md` 自述 `Some files may be licensed under different conditions.` → 是否存在非 BSD 文件，未逐文件核对。
- `NovelAppDesktop.exe` 内 PyInstaller 归档（PYZ）里的模块清单未解包，因此"发布包无 dsh 代码"的依据是**目录/文件名层递归搜索 + exe 内字符串检索**，不是归档内容枚举。
