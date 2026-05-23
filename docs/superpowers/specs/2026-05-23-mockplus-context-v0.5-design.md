# mockplus-context v0.5.0 设计 — 合并最强子集

- **状态**：approved（用户在 brainstorming 阶段已逐节认可）
- **日期**：2026-05-23
- **作者**：xiandan7045@gmail.com + Claude（Opus 4.7）
- **目标分支**：`refactor/merge-best-subset`
- **后续**：进入 writing-plans 出实施计划

---

## 1. 背景

仓库目前有两份并存的 `mockplus-context` skill：

| 位置 | 形态 | 状态 |
|---|---|---|
| `~/.claude/backups/mockplus-context.backup.20260523-183712/` | bash + 2 个 Python(`to-yaml.py` / `to-spec.py`) | 个人备份,YAML 输出 + 设计师语义 token key + `all`/`spec` 一站式 |
| `skills/mockplus-context/`（仓库 main 分支 v0.4.0） | 纯 Python,7 个 `_*.py` 模块 + `references/` | 公开发布,JSON 输出 + hash token key,有 `tree`/`cookie`/`unhandledFields` |

用户实际使用备份版且已经验证体验更顺手（YAML 紧凑、一站式 `all` 命令、按 hash 选切图），但备份版缺 `tree`（URL 指向 group 时只能死掉）和 `cookie` 管理子命令。直接覆盖会丢能力，保留 v0.4 又丢体验。

## 2. 目标

把两个版本的"最强子集"合并到 v0.5.0，**保留 Python 实现路线**，但把备份版的用户体验全部移植过来。接受 v0.5 breaking change（CI / CHANGELOG / fixtures / README / docs/ 一起更新）。

### 2.1 非目标

- 不切回 bash 实现（v0.4 已经 Python 化,且 README 公开宣传"Python skill"）
- 不输出人眼 Markdown spec（备份版 `spec` 命令砍掉,信息跟 YAML 完全重复）
- 不为 v0.4 旧用户保留 `get-data` / `download-assets` 老命令名（重命名,Migration 段写映射）
- 不做端到端 `all` 命令的网络测试（依赖真 cookie + 真 CDN,作为手动 smoke）

## 3. 整体决策（brainstorming 阶段已认可）

| 维度 | 决策 |
|---|---|
| 整体方向 | 保留 Python 路线,移植备份版体验,v0.5 breaking |
| 目标分支 | `refactor/merge-best-subset` |
| download 接口 | `download <URL> --nodes all\|h1,h2 [--out DIR] [--include-design]` |
| token key 命名 | textStyle 用设计师语义名(sharedStyle.name);fill/layout/stroke/effect 仍 hash key |
| 输出格式 | 默认 YAML,保留 `--format json` |
| CLI 命令名 | `data / download / all / tree / cookie`;`inspect` 合并为 `data --stats` |
| SKILL.md 形态 | 短 SKILL.md(~130 行) + `references/`(progressive disclosure,v0.4 延续) |
| cookie 路径 | 系统级 `~/.config/mockplus/cookie`,`cookie` 子命令封装 chmod |
| cache 路径 | `~/.cache/mockplus/<APP_ID>/`(跟 cookie 风格一致) |
| Python 模块 | 合并到 4 个:`mockplus.py` / `cli.py` / `transform.py` / `io.py` |
| fixtures expected | 全重生为 YAML,废除 JSON expected |
| spec 子命令 | **不做**(信息跟 YAML 重复,LLM 不需要) |

## 4. 架构

### 4.1 模块拆分

```
skills/mockplus-context/scripts/
├── mockplus.py        # 入口 + argparse + 子命令 dispatch（~80 行）
├── cli.py             # 各 action 实现:data/download/all/tree/cookie（~220 行）
├── transform.py       # sketch JSON → YAML(token 表 + 设计师命名)（~400 行）
└── io.py              # API/cookie/CDN 下载/cache 路径管理（~300 行）
```

合并对应关系：

| v0.4 模块 | v0.5 归属 | 备注 |
|---|---|---|
| `mockplus.py` | `mockplus.py` | argparse 重写,子命令名换 |
| `_api.py` | `io.py` | API 调用 + cache |
| `_cookie.py` | `io.py` | cookie set/test/status/clear/path |
| `_assets.py` | `io.py` | CDN 下载,接口改 `--nodes` |
| `_transform.py` | `transform.py` | 输出层重写(YAML / 设计师 key) |
| `_tree.py` | `cli.py`(action_tree) | 逻辑短,合进 cli |
| `_schema.py` | **砍掉** | 输出校验降级为 transform 内部 assert |
| `_explore.py` | **砍掉** | 调试工具,不属于 runtime |
| `__init__.py` | **删除** | 不需要 |

### 4.2 模块依赖

```
mockplus.py  →  cli.py  →  transform.py
                       \→  io.py
```

`cli.py` 是唯一引入命令行 IO 的层(stdout/stderr/exit code)。
`transform.py` / `io.py` 是纯函数 + 显式 IO,可被 tests 直接调用。

## 5. CLI 接口契约

```bash
mockplus data <URL> [--out PATH] [--format yaml|json] [--stats] [--refresh]
mockplus download <URL> [--nodes all|h1,h2] [--out DIR] [--include-design] [--png-scale 1|2]
mockplus all <URL> [<OUT_DIR>]                  # = data + download(all + design)
mockplus tree <APP_ID> [--format text|json] [--refresh]
mockplus cookie {set|test|status|clear|path}
```

### 5.1 关键参数语义

- `data <URL>`:默认 YAML 输出到 stdout;`--out` 写文件;`--stats` 额外打印 nodes/styles/assets/unhandledFields 统计到 stderr(替代老 `inspect`);`--refresh` 跳 cache 重拉
- `download <URL>`:默认 `--nodes all`(下所有切图)、`--out ./mockplus-assets/<PAGE_ID>/`;`--nodes h1,h2` 只下指定 hash;`--include-design` 加整页截图 `design.png`;`--png-scale` 备用(目前固定 @2x)
- `all <URL>`:一站式 = `data --out <OUT>/data.yaml` + `download --nodes all --include-design --out <OUT>/`;默认 `<OUT> = ./mockplus-cache/<APP_ID>/<PAGE_ID>/`
- `tree <APP_ID>`:text 含 emoji + 缩进;json 输出 `{id, name, kind: "group"|"page", device?, size?, children?}`;孤儿 page stderr 警告
- `cookie set`:stdin 交互式粘贴,自动 `chmod 600`,文件头加 `# set_at:` / `# expires_at:` 注释
- `cookie test <APP_ID>`:打一次 design API 验证 cookie 有效
- `cookie status`:打印路径 / 权限 / 设置时间 / 剩余天数

### 5.2 路径约定

| 用途 | 默认 | 覆盖环境变量 |
|---|---|---|
| cookie 文件 | `~/.config/mockplus/cookie` | `MOCKPLUS_COOKIE_FILE` |
| API/cache 根 | `~/.cache/mockplus/<APP_ID>/` | `MOCKPLUS_CACHE_DIR` |
| 直接传 cookie | (无) | `MOCKPLUS_COOKIE` |
| `download` 输出 | `./mockplus-assets/<PAGE_ID>/` | `--out` |
| `all` 输出 | `./mockplus-cache/<APP_ID>/<PAGE_ID>/` | 第 2 个位置参数 |

### 5.3 产物目录结构

`download` 单独调用时,切图平铺到 `--out` 目录:

```
./mockplus-assets/<PAGE_ID>/
├── <hash1>.png
├── <hash1>.svg        # 若 CDN 有 SVG 版本
├── <hash2>.png
├── <hash2>.svg
├── ...
└── assets-manifest.json   # 本次 download 的目标清单(去重 hash 列表 + 元信息)
```

`all` 输出时,把 yaml/截图与切图分开,放 `assets/` 子目录避免混在一起:

```
./mockplus-cache/<APP_ID>/<PAGE_ID>/
├── data.yaml
├── design.png
└── assets/
    ├── <hash1>.png
    ├── <hash1>.svg
    └── ...
```

`--include-design` 单独跟 `download` 用时,把 `design.png` 写到 `--out` 同级(不进 `assets/`)。

### 5.4 退出码（兼容 v0.4）

```
0   成功
2   CLI 参数错
10  cookie 未配置
11  --from-file 文件不存在
12  cookie 为空
14  HTTP 层失败
15  cookie test API 拒绝
21  index API code != 0
22  TARGET_ID 误判(URL 指向 group / app 而非 page)
```

废弃:`50`(`_schema.py` 砍了,不再有 schema 校验失败码)。

## 6. 输出 YAML 形态（核心契约）

```yaml
metadata:
  name: Sample Page
  path: Module / Module Subgroup / Sample Page
  pageId: pgA1bC2X3
  appId: <APPID>
  device: ios1x
  size: { width: 375, height: 812 }
  backgroundColor: '#f5f5f5ff'
  components:                          # SymbolInstance 反推
    <libId>/<path>: { id, name, libraryName }

nodes:
  - id: <UUID>
    name: Submit Action
    type: TEXT                         # FRAME/TEXT/INSTANCE/RECTANGLE/ELLIPSE/VECTOR
    layout: layout_000007              # 引用 globalVars.styles
    fills: fill_000001                 # 可选
    strokes: stroke_000001             # 可选
    effects: effect_000001             # 可选
    borderRadius: 8px                  # 可选
    opacity: 0.5                       # 可选（< 1 才输出）
    text: "Submit Action"                 # TEXT
    textStyle: Body/16px/Semibold/Center Style   # 设计师命名
    componentId: <libId>/<componentName>                # INSTANCE
    children: [...]

globalVars:
  styles:
    fill_000001:                       # 单色填充
      - '#FFFFFF'
    fill_000002:                       # 渐变
      - type: GRADIENT_LINEAR
        gradient: linear-gradient(180deg, #FF83DA 0%, #FFCECE 100%)
    fill_000003:                       # 切图填充
      - type: IMAGE
        imageRef: 2b417ea8...          # ← LLM 拿这个 hash 调 download --nodes
        scaleMode: FILL
    layout_000007:
      mode: none                       # Mockplus 没 AutoLayout
      sizing: { horizontal: fixed, vertical: fixed }
      locationRelativeToParent: { x: 266, y: 737 }
      dimensions: { width: 80, height: 22 }
    Body/16px/Semibold/Center Style:             # key 用设计师命名
      fontFamily: PingFang SC
      fontWeight: 600
      fontSize: 16
      lineHeight: 22px
      textAlignHorizontal: CENTER
      color: '#262626'

_meta:
  transformVersion: "0.5.0"
  sketchPluginVersion: "..."
  documentVersion: "..."
  inputFieldsTotal: 1234
  unhandledFields: []                  # Mockplus schema 升级时这里会列出
  warnings: []
```

### 6.1 token key 命名规则

| 类型 | key 形态 | 例子 |
|---|---|---|
| fill | `fill_NNNNNN` | `fill_000003` |
| stroke | `stroke_NNNNNN` | `stroke_000001` |
| effect | `effect_NNNNNN` | `effect_000001` |
| layout | `layout_NNNNNN` | `layout_000007` |
| textStyle(有 sharedStyle) | sharedStyle.name 原样 | `Body/16px/Semibold/Center Style` |
| textStyle(无 sharedStyle) | `textStyle_NNNNNN` | `textStyle_000001` |

**特殊字符处理**:sharedStyle.name 保留原文(含中文 / 中文标点 / 空格 / 斜杠等),只在 YAML 序列化时按 YAML 规则 quote。冲突场景(两个 sharedStyle 同名):后到的加 `_2`/`_3` 后缀。

### 6.2 切图 hash → download 工作流

LLM 看到 fill 数组里有 `imageRef: <hash>` 即知该节点需要切图,直接调:

```bash
mockplus download <URL> --nodes <hash1>,<hash2> --out ./assets
# 产物:./assets/<hash>.png + <hash>.svg(若 CDN 有 SVG 版本)
```

### 6.3 unhandledFields 探针

`transform.py` 维护 `LAYER_HANDLED` / `BASIC_HANDLED` 字段集合白名单。每次 transform 完一个节点,把没消费的字段路径塞进 `_meta.unhandledFields`(去重)。Mockplus 升级 sketch schema 时,新字段会立刻出现在这个列表,提示需要更新 transform。

**断言策略(替代砍掉的 _schema.py)**:transform 输出 dict 后,用 `assert` 检查关键字段(`metadata.pageId`, `nodes` is list, `globalVars.styles` is dict),失败抛 ValueError 让 cli 转 exit 2。

## 7. 测试改造

### 7.1 砍掉

- `tests/test_schema.py`(`_schema.py` 砍了)
- `tests/fixtures/expected/*.json`(5 份,改成 YAML)

### 7.2 改造

| 文件 | 改动 |
|---|---|
| `tests/fixtures/expected/*.yaml` | 5 份重新生成;验证 token key 用设计师命名 |
| `tests/test_transform.py` | 加载 YAML 对比 transform 输出;断言 `_meta.unhandledFields == []` |
| `tests/test_assets.py` | 适配新接口 `--nodes all\|h1,h2`,去掉 `--downloads` JSON 数组 |
| `tests/test_tree.py` | 保持(只改 import 路径:`from cli import _tree_text/_tree_json`) |
| `tests/requirements.txt` | 加 `PyYAML>=6` |

### 7.3 新增

- `tests/test_token_naming.py` — 验证 sharedStyle.name 作为 key 的逻辑(中文、特殊字符、同名冲突 → `_2` 后缀)
- (可选)`tests/test_cli_dispatch.py` — 验证 `mockplus data` 等命令的 argparse 拼装

### 7.4 不做

- 不加 `test_all_command.py` 端到端(依赖真 cookie + 真 CDN,作为手动 smoke)
- 不加 mock HTTP server(测 transform 纯函数已经覆盖核心)

## 8. 文档与发布

### 8.1 README.md(根)

- 第一句改成:「从 Mockplus(摹客)设计稿抓取**结构化 YAML + 切图**,LLM 直接消费。Python 实现,YAML 优先,按需下载。」
- 去掉"Python 单文件 skill,无运行时外部依赖"(因为现在依赖 PyYAML)
- "仓库布局"图更新(`config/` 不再在 `skills/mockplus-context/` 下,改 `~/.config/mockplus/`)
- "5 分钟上手"步骤全部改 v0.5 命令(`mockplus data <URL>` 替代 `mockplus get-data <URL>`)
- 加 v0.4 → v0.5 升级提示(链接到 CHANGELOG Migration)

### 8.2 CHANGELOG.md

新增 v0.5.0 章节,Keep a Changelog 格式:

```markdown
## v0.5.0 — 2026-05-23

**合并最强子集:YAML 优先输出 + 一站式 all 命令 + 系统级 cookie。**

### Breaking
- 输出默认从 JSON 改 YAML(可用 `--format json` 切回)
- CLI 命令重命名:`get-data` → `data`、`download-assets` → `download`、`inspect` → `data --stats`
- cookie 文件默认路径从 `skills/mockplus-context/config/cookie` 迁到 `~/.config/mockplus/cookie`
- download 接口从 `--downloads '[{url,fileName},...]'` 改 `--nodes all|h1,h2`
- 删除 `inspect` / `_explore.py` / `_schema.py` / `__init__.py`
- 删除 `references/api-reference.md`(并入 SKILL.md)
- token key 命名:textStyle 改用 sharedStyle.name(原 `text_001`),其他 fill/layout/stroke/effect 改 6 位序号(原 `fill_001` → `fill_000001`)
- 退出码 `50`(schema 校验失败)废弃

### Added
- `all` 子命令:一站式 = data + download(all + design)
- `download --include-design` 同时下整页截图 design.png
- `data --stats`:统计输出(替代 `inspect`)
- `download --nodes` 按 hash 选切图,直接对接 YAML 里的 `imageRef`

### Changed
- Python 模块从 7 个合并到 4 个:`mockplus.py / cli.py / transform.py / io.py`
- SKILL.md 重写,~130 行(短 SKILL.md + references/)
- cache 路径 `~/.cache/mockplus-context/` → `~/.cache/mockplus/`
- fixtures `expected/*.json` → `expected/*.yaml`(5 份重生)
- `tests/requirements.txt` 加 `PyYAML>=6`

### Removed
- `inspect` 命令(合并到 `data --stats`)
- `_explore.py` / `_schema.py` / `__init__.py`
- `references/api-reference.md`(并入 SKILL.md)

### Migration

旧命令 → 新命令:

| v0.4 | v0.5 |
|---|---|
| `mockplus get-data <URL>` | `mockplus data <URL>`(默认 YAML;要 JSON 加 `--format json`) |
| `mockplus inspect <URL>` | `mockplus data <URL> --stats` |
| `mockplus download-assets --downloads '[...]' --local-path X` | `mockplus download <URL> --nodes h1,h2 --out X` |
| (无) | `mockplus all <URL>`(新一站式) |

cookie 迁移:

\`\`\`bash
# 把 v0.4 仓库内 cookie 迁到系统级
mkdir -p ~/.config/mockplus && chmod 700 ~/.config/mockplus
mv skills/mockplus-context/config/cookie ~/.config/mockplus/cookie
chmod 600 ~/.config/mockplus/cookie
# 或者重跑一次 cookie set
mockplus cookie set
\`\`\`
```

### 8.3 docs/architecture.md

重写为 4 模块新架构描述。涵盖:模块职责、依赖图、token 表实现策略、`unhandledFields` 探针机制。

### 8.4 docs/cookie.md

- cookie 路径改 `~/.config/mockplus/`
- 保留浏览器抓 cookie 步骤
- 加 v0.4 → v0.5 cookie 迁移命令

### 8.5 .github/workflows/ci.yml

- Python 矩阵 3.8 / 3.11 / 3.12 保持
- 加 `pip install PyYAML`(在 `pytest tests/` 之前)
- 检查 `tests/requirements.txt` 安装链路

### 8.6 references/

- `examples.md`:更新端到端调用样例(全 v0.5 命令)
- `troubleshooting.md`:错误码表更新(去掉 50,加 `data --stats` 说明),保留诊断思路
- `api-reference.md`:**删除**(内容并入 SKILL.md CLI 速查表)

### 8.7 SKILL.md(给 LLM)

重写至 ~130 行,章节:

1. 触发场景(URL 形式 / 关键词)
2. cookie 前置(`cookie set` / 系统级路径)
3. LLM 工作流(5 步:确认 cookie → tree(可选) → data → 看 imageRef → download)
4. CLI 速查表(5 个命令 + 主要参数)
5. 输出 YAML 速览(metadata / nodes / globalVars / `_meta`)
6. 常见失败(7 个错误码 + 处理)
7. references/ 索引(只列 examples.md + troubleshooting.md)

### 8.8 版本号

v0.5.0(不是 v1.0,0.x 可以 breaking)。

## 9. 风险与不做的事

### 9.1 风险

| 风险 | 缓解 |
|---|---|
| token key 用 sharedStyle.name 含中文/特殊字符,某些 YAML 解析器可能不友好 | 序列化时按 YAML 规则 quote;tests 覆盖 |
| 设计师改 sharedStyle.name 后 LLM 已经基于老 key 生成的代码失效 | 这是设计取舍:语义化 > diff 稳定。在 SKILL.md 明确写 |
| 砍 `_schema.py` 后 transform 输出错误更难定位 | transform 内部 assert + 单元测试覆盖核心字段 |
| v0.4 用户升级需要重写命令调用 | CHANGELOG Migration 段提供命令映射表 |
| 中国境外节点跑 CDN 切图下载超时 | `troubleshooting.md` 保留这一条 |

### 9.2 明确不做

- 不输出 spec.md(信息跟 YAML 重复)
- 不保留 v0.4 老命令名(`get-data` 等),只在 Migration 段列映射
- 不做 `download` 多页批量(单页一次调用,LLM 自己循环)
- 不做 GUI / web UI(skill 是 CLI)
- 不引入新外部依赖(只加 PyYAML,标准库 + curl 等已有)

## 10. 实施大致顺序（writing-plans 阶段细化）

1. 重写 `transform.py`(YAML 输出 + 设计师 token key + unhandledFields)
2. 重写 `io.py`(合并 _api/_cookie/_assets,cookie 路径系统级)
3. 写 `cli.py`(5 个 action,含 `all`)
4. 重写 `mockplus.py`(argparse + dispatch)
5. 重生 `fixtures/expected/*.yaml`
6. 改 `tests/test_*.py`(适配新 import + 新格式)
7. 加 `tests/test_token_naming.py`
8. 删 `_explore.py` / `_schema.py` / `__init__.py` / `references/api-reference.md`
9. 重写 SKILL.md / README.md / docs/architecture.md / docs/cookie.md / CHANGELOG.md
10. 更新 `.github/workflows/ci.yml`(加 PyYAML)
11. 本地跑 `pytest tests/` 全绿;手动 smoke `mockplus all <真实 URL>`
12. commit 推 `refactor/merge-best-subset`,开 PR 自审 / 让用户 review

## 11. 验收标准

- `pytest tests/` 全绿,Python 3.8/3.11/3.12 矩阵
- 手动 smoke:对一个真实 Mockplus URL 跑 `mockplus all <URL>`,产物含 `data.yaml`(YAML 格式 + 设计师 token key + `_meta.unhandledFields == []`) + `design.png` + 切图若干
- `mockplus cookie status` 显示系统级路径 + 剩余天数
- `mockplus tree <APP_ID>` 树形输出 + 孤儿 page 警告(若有)
- README / CHANGELOG / SKILL.md 三处的命令示例互相一致
- 无 v0.4 老命令(`get-data` / `download-assets` / `inspect`)残留在代码或文档
