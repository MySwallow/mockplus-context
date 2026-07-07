# Changelog

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## v0.6.0 — 2026-07-07

**包含树重建:子控件真正嵌套进视觉容器,`locationRelativeToParent` 名副其实。**

Sketch/Mockplus 原始数据只有画布绝对坐标,且"标题压在导航条上"在树里是平级兄弟。
v0.6 在转换管线末端加独立后处理 pass(`relayout.py`),按几何包含重建父子并改写相对坐标。
设计决策经 5 页真实语料(1582 节点)实证:不变量全绿、可逆性位级精确、与算法原型指派 100% 一致。

### Breaking
- **`locationRelativeToParent` 语义修正**:v0.5 存画布绝对坐标(历史命名 bug),v0.6 起为真·相对父坐标。新旧文件用 `_meta.coordinateSpace` 区分(`parent-relative` / `absolute-artboard`);消费旧缓存文件前先看这个标记
- **nodes 树形变化**:视觉上被兄弟背景/卡片包含的节点重挂为其子节点(授权分组是硬边界,只在组内兄弟间嵌套;真实页约 8~16% 节点被重挂)
- **layout token 全量重编号**:相对化后去重率更高(真实页 205 → 158,-23%),token id 与 v0.5 不连续
- 回滚通道:`mockplus data/all --coords absolute` 保留 v0.5 绝对坐标语义(过渡期一个版本周期);`transform(coords=...)` 对非法值快失败(ValueError),不静默翻转语义

### Added
- `relayout.py`:作用域化包含树重建 —— 最小面积包含者 + ε_contain=1.0 / ε_stack=0.5(堆叠判定独立紧容差)+ z 过滤(数组前=顶层,作用域内方向证据 <80% 自动禁用并告警)+ 满幅背景豁免 + 确定性 tie-break;内置不变量校验(无环/全覆盖/几何包含/位级可逆),任一失败**或任何未预期异常**自动回退 v0.5 语义并写 `_meta.warnings`(重建缺陷绝不升级为导出失败)
- **容器节点级 `absolutePosition`**:任意叶子的画布绝对位置 = 最近容器 absolutePosition + 自身 rel,一次加法
- **INSTANCE 内部冻结、不收养**:组件实例结构与组件定义保持一致;跨界收养仅限授权分组,节点打 `adoptedBy: geometry` 标记
- `_meta.relayout` 统计:reparented / adopted / ambiguousTies / keptViolations / zFilter / zEvidence
- `REAL_TYPE_TO_V5` 补 `mask` → `MASK`(真实语料发现的裁剪蒙版层;relayout 冻结处理),`basic.maskType` 纳入已处理字段
- client 离线回退:非 `--refresh` 时网络/cookie 失败自动回退过期缓存并告警(transform 升级后可离线重转本地缓存);仅接受 ≤7 天旧且可完整解析的缓存,超龄/损坏走原错误路径

### Fixed
- `REAL_TYPE_TO_V5` 补 `Image` → `IMAGE`、`MSSliceLayer` → `SLICE`,消除 13 个 `_UNKNOWN_IMAGE` / `_UNKNOWN_MSSLICELAYER` 误标(切图数据本来就已正确提取,此次仅修正节点 `type` 标签)。

### Tests
- 新增 `tests/test_relayout.py`(36 用例):黄金用例(兄弟→父子 rel=(155,12)、实例内部冻结 rel=(266,19)、INSTANCE 不收养)+ 全夹具不变量(位级可逆 / ε 包含 / 节点集不变 / 确定性 / 幂等)+ `--coords absolute` 回滚语义 + mask 映射 + 安全网分支(校验失败回退、未预期异常兜底、zFilter 自动禁用、平局 tie-break、keptViolations、悬空 token、空页、token 撞名防护、收养层叠序、coords 非法值快失败)
- 新增 `tests/test_client.py`(7 用例):离线回退 ≤7 天命中 / 超龄拒绝 / 损坏缓存拒绝 / `--refresh` 不回退 / cookie 缺失回退 / 页面数据两侧边界
- 新增 `tests/test_cli_args.py`(2 用例):`--coords` 在 `data` 与 `all` 两个入口的参数面契约
- 5 份 `expected/*.yaml` 快照按 v0.6 语义重生成

## v0.5.0 — 2026-05-23

**合并最强子集:YAML 优先输出 + 一站式 all 命令 + 系统级 cookie。**

### Breaking
- 输出默认从 JSON 改 YAML(可用 `--format json` 切回)
- CLI 命令重命名:`get-data` → `data`、`download-assets` → `download`、`inspect` → `data --stats`
- cookie 文件默认路径从 `skills/mockplus-context/config/cookie` 迁到 `~/.config/mockplus/cookie`
- `download` 接口从 `--downloads '[{url,fileName},...]'` 改为 `--nodes all|h1,h2`(从 YAML 里 `imageRef` 直取)
- 删除 `inspect` 命令、`_explore.py`、`_schema.py`、`__init__.py`、`references/api-reference.md`(并入 SKILL.md)
- token key 命名:textStyle 改用 sharedStyle.name(原 `text_001`);其他 fill/layout/stroke/effect 改 6 位序号(原 `fill_001` → `fill_000001`)
- 节点字段:`bounds` 改为 `layout` 引用 + `globalVars.styles.layout_NNNNNN`;`text` 嵌套结构改为 `text + textStyle` 平铺;切图节点 `asset` 字段改为在 `fills` 数组里加 IMAGE fill
- 退出码 `50`(schema 校验失败)废弃
- cache 路径 `~/.cache/mockplus-context/` → `~/.cache/mockplus/`

### Added
- `all` 子命令:一站式 = data + download(all + design)
- `download --include-design` 同时下整页截图 `design.png`
- `data --stats`:nodes/styles/assets/unhandledFields 统计输出(替代 `inspect`)
- `download --nodes hash,...`:按 hash 选切图,直接对接 YAML 里 `imageRef`
- 颜色 alpha < 1 时输出 `rgba(r, g, b, a.xx)`(原 v0.4 是 `#RRGGBB (alpha=0.5)`)
- REAL_TYPE_TO_V5 覆盖 `Path` / `path` / `MSShapeGroup`(统一映射为 VECTOR)
- `sharedStyle.type` 大小写不敏感判断(实际值是 `TextStyle` 而非 `text`)

### Changed
- Python 模块从 7 个合并到 4 个:`mockplus.py` / `cli.py` / `transform.py` / `client.py`(注:spec 原写 `io.py`,实际改名为 `client.py` 避开 Python 标准库 `io` 模块冲突)
- SKILL.md 重写至 ~120 行(短 SKILL.md + `references/`)
- fixtures `expected/*.json` → `expected/*.yaml`(5 份重生)
- `tests/requirements.txt`:`pytest>=7` + `PyYAML>=6`(去掉 `jsonschema>=4`)

### Removed
- `inspect` 命令(合并到 `data --stats`)
- v0.4 的 8 个老模块:`_api.py` / `_cookie.py` / `_assets.py` / `_transform.py` / `_tree.py` / `_schema.py` / `_explore.py` / `__init__.py`
- `references/api-reference.md`(并入 SKILL.md)
- `tests/test_schema.py`(对应砍掉的 `_schema.py`)

### Added Tests
- `tests/test_token_naming.py`:7 个用例覆盖 6 位序号、sharedStyle.name 命名、同名冲突后缀(`_2`/`_3`)、fingerprint 去重、layout 输出形态

### Migration

旧命令 → 新命令:

| v0.4 | v0.5 |
|---|---|
| `mockplus get-data <URL>` | `mockplus data <URL>`(默认 YAML;要 JSON 加 `--format json`) |
| `mockplus inspect <URL>` | `mockplus data <URL> --stats` |
| `mockplus download-assets --downloads '[...]' --local-path X` | `mockplus download <URL> --nodes h1,h2 --out X` |
| (无对应) | `mockplus all <URL>`(新一站式) |

Cookie 迁移:

```bash
mkdir -p ~/.config/mockplus && chmod 700 ~/.config/mockplus
mv skills/mockplus-context/config/cookie ~/.config/mockplus/cookie
chmod 600 ~/.config/mockplus/cookie
# 或者重跑一次 cookie set
python3 skills/mockplus-context/scripts/mockplus.py cookie set
```

## v0.4.0 — 2026-05-22

**skill 目录纯化:只保留 LLM runtime 直接消费的内容。**

### Changed
- **Breaking**: skill 内部目录精简,`skills/mockplus-context/` 下只保留 LLM 直接消费的资产:
  - `SKILL.md` — LLM 入口
  - `scripts/` — Python CLI
  - `references/` — LLM 按需深读的进阶参考(api / examples / troubleshooting)
  - `config/` — 运行时 cookie(gitignored)
- 开发期产物移出 skill:
  - `tests/` 移到 repo root(开发者跑 pytest)
  - `docs/architecture.md` 移到 repo root(给开发者读懂模块拆分)
  - `docs/cookie.md` 移到 repo root(给真人用户配 cookie)
- SKILL.md 改写遵循 progressive disclosure:删 "## 资源指引" 索引清单,改为正文内**按需就地**指引(`references/api-reference.md` / `examples.md` / `troubleshooting.md`)
- `references/` 内文件互引用从 `docs/xxx.md` 改为同级文件名

### Removed
- `skills/mockplus-context/config/README.md`(SKILL.md 已覆盖 cookie 管理说明)

### Migration
- pytest 跑法:`python3 -m pytest tests/` (从 repo root)
- 命令路径不变:`python3 skills/mockplus-context/scripts/mockplus.py <cmd>`

## v0.3.0 — 2026-05-22

**仓库结构标准化 + 文案聚焦清理。**

### Changed
- **Breaking**: 仓库结构调整,所有 skill 内容迁入 `skills/mockplus-context/` 子目录,自包含完整:`SKILL.md` + `scripts/` + `docs/` + `tests/` + `config/`(运行时)
- 命令调用路径:
  - 老: `python3 scripts/mockplus.py <cmd>`
  - 新: `python3 skills/mockplus-context/scripts/mockplus.py <cmd>`
  - **强烈建议设 alias**: `alias mockplus='python3 /path/to/repo/skills/mockplus-context/scripts/mockplus.py'`
- Cookie 文件默认位置:`<repo_root>/config/cookie` → `<repo_root>/skills/mockplus-context/config/cookie`(env `MOCKPLUS_COOKIE_FILE` 可覆盖)
- SKILL.md 重写为标准 progressive disclosure 格式,description 更聚焦使用场景

### Removed
- 所有面向用户文档中的外部工具对照说明,保持 skill 单一聚焦
- 开发期 spec/plan 历史文档 `docs/specs/` 与 `docs/plans/`(代码已落地,git 历史可查)

### Migration
- 老用户:`git pull` 后用 alias 屏蔽路径变化,或把 cookie 文件手动移到新位置
- pytest 跑法:`cd skills/mockplus-context && python3 -m pytest tests/ -v`

## v0.2.0 — 2026-05-22

**Breaking change: 整体重构为 Python skill,bash CLI 移除。**

### Added
- Python 单文件 skill (`scripts/mockplus.py`),4 个主子命令(get-data / tree / download-assets / cookie *)+ `inspect` 辅助
- 结构化 JSON 输出:`metadata` + `globalVars` + `nodes` + `_meta` 四段式分层契约
- `SKILL.md` LLM 入口
- `_meta.unhandledFields` 字段追踪,Mockplus 改 schema 立刻可见
- 测试覆盖: transform 黄金对照(5 fixture)、schema 校验、tree/assets 单元测试,共 18 个测试

### Changed
- 子命令重命名:
  - `page <APP> <PAGE>` → `get-data <URL>`(JSON 到 stdout,不再落文件)
  - `assets <PAGE_DIR>` → `download-assets --downloads ... --local-path ...`
  - `index` / `url` / `fetch` 不再暴露(内部 module)
- `group <APP> <GROUP>` **不再保留**,group 浏览改用 `tree` 浏览 + LLM 循环调 `get-data`
- API cache 默认路径: `./mockplus-cache/` → `~/.cache/mockplus-context/`(env `MOCKPLUS_OUT_ROOT` 覆盖)
- `config/cookie` 路径保留兼容,老用户 cookie 不失效

### Removed
- `bin/mockplus` 及全部 `lib/*.sh`、`scripts/validate.sh`、`tests/smoke.sh`
- SVG 切图下载(首版 PNG-only,后续可加)

### Migration
- 老用户的 `config/cookie` 沿用,不用重配
- 切图 cache 默认位置变了,旧的 `./mockplus-cache/` 想保留 → `export MOCKPLUS_OUT_ROOT=./mockplus-cache`
- 脚本里 `./bin/mockplus xxx` 调用全部换为 `python3 scripts/mockplus.py xxx`

## [0.1.0] - 2026-05-22

初始版本。从早期内嵌实现抽出来,独立成 GitHub 仓库,
重构成 `bin/mockplus` + `lib/*.sh` 模块化结构。

### Added

- `mockplus cookie` 子命令族:`set` / `test` / `status` / `clear` / `path`
  - cookie 文件位置:**`<repo_root>/config/cookie`**(已在 `.gitignore` 排除)
  - 自动 `chmod 600`(Windows NTFS 上是 no-op,fallback `|| true`)
  - 文件内嵌注释:`set_at` / `expires_at`(估算 30 天)
  - `MOCKPLUS_COOKIE` 环境变量优先于文件,适合 CI / 临时会话
  - 想存别处:`MOCKPLUS_COOKIE_FILE=/path mockplus cookie set`
- `mockplus fetch <URL>`:智能 URL 分发,自动判断单页 / 分组 / 仅 app
- `mockplus group <APP_ID> <GROUP_ID>`:**新增** 分组批量拉取,递归该 group 下所有页面
- `mockplus tree <APP_ID>`:**新增** 树形打印项目层级(group/page + 节点 ID)
- `_pages.json` 扩展:同时输出 `groups[]` 列表(name / path / pageCount / parentId)
- `scripts/validate.sh`:CI 入口(bash -n / shellcheck / smoke test)
- `.github/workflows/ci.yml`:Ubuntu + bash + python3 + shellcheck CI
- 完整文档:`docs/{cookie,architecture,api-reference,troubleshooting,examples}.md`

### Removed

- ~~`to-spec.py`~~ — spec 转换器移除,**本工具只负责拉数据,职责单一**
- ~~`mockplus.sh spec` 子命令~~ — 同上
- ~~`mockplus.sh all` 子命令~~ — 被 `mockplus fetch` 取代,语义更清晰

### Changed

- 单文件 `mockplus.sh` → 模块化 `bin/mockplus` + 7 个 `lib/*.sh`
  - `lib/common.sh`:日志 / 错误 / 依赖检查
  - `lib/http.sh`:`http_app` / `http_cdn` 封装
  - `lib/cookie.sh`:cookie 全生命周期
  - `lib/api.sh`:URL 解析 + index 拉取 + 树形打印 + 节点类型查询
  - `lib/page.sh`:单页 + 切图
  - `lib/group.sh`:分组批量
  - `lib/fetch.sh`:智能分发
- Cookie 文件位置从 `~/.config/mockplus/cookie` 改到 `<repo_root>/config/cookie`
  (放仓库内,每个 clone 自带独立 cookie;`.gitignore` 已硬编码 `/config/cookie`)
  **老 cookie 文件不会自动迁移**——重新 `mockplus cookie set` 即可
- 项目重定位:**通用 Mockplus 抓取 CLI 工具**,不绑任何 IDE / LLM / 工具链
  (任何能读本地文件的下游都能消费输出)
- 删除 `scripts/install` 和 `SKILL.md`(避免给人"必须在某个 IDE 里用"的错觉)
- `die` 函数:用 `$1` 而非 `$*`,避免 exit code 被拼进错误消息

### Fixed

- `cookie status` 时 `stat` 命令在 Linux/macOS 差异(自动 fallback)

### Windows 兼容

- PNG magic 校验从 `xxd` 改为 python 标准库(Git Bash 默认无 xxd)
- `chmod` 调用全部加 `|| true`,NTFS 上 no-op 不报错
- 在 Git Bash for Windows / WSL / MSYS2 下应都能跑(未做完整 CI 验证)
