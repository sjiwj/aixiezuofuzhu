# scripts/fixtures —— L1-L4 质检测试样本

由 task-3 / task-4（质检）维护。用于验证 scripts/l1_l2_check.py 与 scripts/l3_l4_check.py，可重复执行。

## CLI 约定（两个脚本一致）

```
python scripts/<script>.py <章节文件> [--rules config/qc_rules.json] [--json [路径]] [--strict]
```

| 参数 | 行为 |
|---|---|
| 无参数 | 打印人类可读报告；l1_l2 另写 reports/<章名>.json，l3_l4 不落盘 |
| `--json` | stdout 只输出合法 JSON（结构 `{"file","stats","issues"}`），不打印报告 |
| `--json PATH` | 同上，并额外写入 PATH |
| `--strict` | 存在 error 级 issue 时退出码 1，否则 0 |
| `--rules PATH` | 指定阈值文件；文件缺失/损坏时用内置兜底并在 stderr 提示，不崩 |
| `--map PATH` | 仅 l3_l4：指定地图 JSON |

issues 统一为五键：`rule / severity(error|warn|info) / line(可为 null) / message / snippet`。

行号策略（task-5）：`dash_count`（首个破折号）、`quote_pairs`（首个不成对引号）、`paragraph_length`、`arabic_number`、`dialogue_tag` 在 JSON 里带行号；`word_count`、`pronoun_density`、`repeated_phrase` 属全章属性，line 为 null。**这些行号只进 JSON，人类报告文本对 dash_count / quote_pairs 仍不打印行号**（保持历史文本逐字不变）。

## 样本清单

| 文件 | 用途 | 期望结果 |
|---|---|---|
| qc_ok.md | 路线/速度/物候全部正确 | l3_l4 0 error；--strict 退出码 0 |
| qc_bad.md | 四处故意错误（行 1/3/5/7） | l3_l4 4 条 error；--strict 退出码 1 |
| l1_bad.md | 破折号 + 引号不成对 + 字数不足 | l1_l2 2 error（dash_count、quote_pairs）+ warn；--strict 退出码 1 |
| rules_tight.json | 收紧阈值（步行 30-40、字数下限 5000、主角改乙、3 行物候窗） | 同一份 ch001.md 输出明显变化，证明配置真的被读取 |
| season_cross.md | 蝉在第 1 段、雪在第 2 段（跨一个空行） | 默认 adjacent 检出 `L4-season-conflict`（行 3）；改用 rules_paragraph.json 后不再检出 |
| season_far.md | 蝉 / 中性段 / 雪 三段（隔一段） | adjacent 不报（窗口只覆盖相邻两段）；rules_lines.json（6 行窗）能报 |
| rules_paragraph.json | 把物候窗口切回 paragraph | season_cross.md 0 条（复现旧行为） |
| rules_lines.json | 物候窗口 lines / 6 行 | season_far.md 检出（行 5） |
| rules_bom.json | 带 UTF-8 BOM 的最小配置（l2.protagonist=乙） | l1_l2 能读到（主角名 2 次），stderr 无告警 |
| chapter_bom.md | 带 UTF-8 BOM 的章节（同 l1_bad.md） | 行号仍为 dash=1 / quote=3，与无 BOM 版一致 |
| README.md | 本文件 | - |

qc_bad.md 的四条错误：

1. 行 1 - 往东一百二十里到示例滩 -> `L3-route-distance`（路线表 300 里）
2. 行 3 - 步行两天走三百里 = 150 里/天 -> `L4-speed-mismatch`（合理 40-60）
3. 行 5 - 盛夏蝉声 + 薄雪 -> `L4-season-conflict`（夏 vs 冬）
4. 行 7 - 往南五里到雷公地 -> `L3-route-direction`（路线表为西）

## L4 物候窗口模式（config/qc_rules.json → season.window）

| 模式 | 含义 | 特点 |
|---|---|---|
| `paragraph` | 每个段落各自成一个窗口，同段才比较 | 最严格、误报最少，但跨段矛盾查不到（旧默认） |
| `adjacent` | 段落 i 与 i+1 合成一个窗口，步长 1 段（**当前默认**） | 覆盖「上一段蝉声、下一段落雪」这类最常见写法；隔一段以上不覆盖 |
| `lines` | 每 `window_lines` 行一个窗口，步长 1 行 | 最宽松，分段被打散或矛盾隔得远时用；误报风险最高 |

矛盾行号取两处词里更晚的那一行，消息里同时给出双方行号；滑动窗口对同一对矛盾只报一次（按行号去重）。

## 回归命令（在 D:\\NovelApp 下）

```powershell
$py = "C:\Python315\python.exe"

# L1/L2：ch001.md 必须与迁移前逐字一致（0 错误 / 1 警告 repeated_phrase 了一遍×4）
& $py scripts\l1_l2_check.py samples\ch001.md
& $py scripts\l1_l2_check.py samples\ch001.md --strict   # 期望 0
& $py scripts\l1_l2_check.py scripts\fixtures\l1_bad.md --strict  # 期望 1

# L3/L4
& $py scripts\l3_l4_check.py samples\ch001.md --strict            # 期望 0
& $py scripts\l3_l4_check.py scripts\fixtures\qc_bad.md --strict # 期望 1，行 1/3/5/7
& $py scripts\l3_l4_check.py samples\ch001_bad.md --map config\map.json      # 2 条 L3-route-distance（行 227/249）
& $py scripts\l3_l4_check.py samples\ch001_bad.md --map config\map_bad.json  # 无 routes 时退回旧逻辑（2 条 info）

# 物候窗口模式对比
& $py scripts\l3_l4_check.py scripts\fixtures\season_cross.md                           # adjacent：报（行 3）
& $py scripts\l3_l4_check.py scripts\fixtures\season_cross.md --rules scripts\fixtures\rules_paragraph.json  # paragraph：不报
& $py scripts\l3_l4_check.py scripts\fixtures\season_far.md --rules scripts\fixtures\rules_lines.json        # lines 6 行：报（行 5）

# 统一 JSON
& $py scripts\l1_l2_check.py samples\ch001.md --json
& $py scripts\l3_l4_check.py samples\ch001_bad.md --json
```

## 配置根定位（NOVELAPP_ROOT / 打包）

两个脚本都按下面的优先级找 `config/`（第一个「目录里确实有 config/」的候选获胜）：

| 优先级 | 来源 | 用在哪 |
|---|---|---|
| 1 | 环境变量 `NOVELAPP_ROOT` | 打包/部署时由启动器注入，指向含 `config/` 的项目根 |
| 2 | frozen 时 `sys.executable` 所在目录 | PyInstaller 打包后，配置放 exe 同级；`__file__` 指向 `_MEIPASS` 不可用 |
| 3 | 源码 `__file__` 上两级 | 开发态（D:\NovelApp） |

都不含 `config/` 时用候选首位拼路径；配置真的缺失时两个脚本都会往 stderr 打 `[warn] 配置不存在，使用内置兜底: <路径>`，不再静默退化。命令行传相对路径时仍先按 cwd 找，找不到才拼配置根（老约定不变）。

```powershell
# 开发态（任意 cwd，绝对路径即可）
cd C:\temp
& $py D:\NovelApp\scripts\l3_l4_check.py D:\NovelApp\samples\ch001.md

# 打包/部署：脚本挪到别处，靠环境变量指项目根
$env:NOVELAPP_ROOT = 'D:\NovelApp'
& $py C:\deploy\l3_l4_check.py D:\NovelApp\samples\ch001.md
```

`--json` 的 `stats.root` / `stats.rules` 会回报实际用到的根与配置文件，打包后先看这两个字段就能判断有没有找错地方。

## UTF-8 BOM 兼容（记事本 / PowerShell 5.1 另存）

客户用记事本、Notepad++ 或 PowerShell 5.1 的 `Set-Content -Encoding UTF8` 另存配置，文件会带 BOM（`EF BB BF`）。用 `encoding='utf-8'` 读会让 `json.load` 抛 `Expecting value: line 1 column 1`，脚本**静默退回内置默认阈值**——阈值改了等于没改。

现在两个脚本的所有**读取**都走 `utf-8-sig`（自动吞掉 BOM，无 BOM 文件行为完全不变）：

| 位置 | 读取对象 |
|---|---|
| `l1_l2_check.load_cfg` | `config/qc_rules.json` |
| `l3_l4_check.load_rules` | `config/qc_rules.json` |
| `l3_l4_check.load_map` | `config/map.json` |
| 两脚本 main | 章节正文 |

写出（reports JSON）仍是 `utf-8`，不带 BOM。`qc_rules.json` 缺失或 JSON 语法坏掉时，两个脚本都会在 stderr 打 `[warn] ...使用内置兜底: <路径>` 后继续跑（不静默）。`map.json` 坏掉则直接抛 `JSONDecodeError` 退出（L3 没有兜底可言，宁可显式失败）。

```powershell
# 造带 BOM 的配置（等价 PS 5.1 的 Set-Content -Encoding UTF8；PS 7 的 -Encoding UTF8 默认无 BOM）
$bom = New-Object System.Text.UTF8Encoding($true)
[IO.File]::WriteAllText("$PWD\scripts\fixtures\rules_bom.json", '{"l2": {"protagonist": "乙"}}', $bom)

# 期望：主角名 2 次、stderr 为空
& $py scripts\l1_l2_check.py samples\ch001.md --rules scripts\fixtures\rules_bom.json
& $py scripts\l1_l2_check.py scripts\fixtures\chapter_bom.md --json
```

## 阈值所在

全部在 `config/qc_rules.json`：l1（破折号/阿拉伯数字/段落长度/字数区间）、l2（主角名/密度/重复短语/对话标签/白名单）、l3（距离与路线容差、上下文窗口）、l4（速度表、容差、最短天数）、season（物候词分组与互斥对、窗口）。脚本内只保留兜底默认值。
