# Changelog

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## Unreleased

### Fixed
- CI 工作流(`.github/workflows/ci.yml`)从 v0.2 bash 实现的遗留路径(`bin/mockplus`、`scripts/validate.sh`、`tests/smoke.sh`)更新为 v0.4 Python 实现的 `pytest tests/`,并加 Python 3.8 / 3.11 / 3.12 矩阵测试
- README 安装步骤的 git clone URL 从占位符 `<you>` 改为真实 `MySwallow`
- `references/api-reference.md` 中 `MOCKPLUS_COOKIE_FILE` 默认值从模糊的 `<repo>/config/cookie` 改为精确的 `skills/mockplus-context/config/cookie`,并说明是基于 skill 目录而非仓库根

### Changed
- README 添加 CI / License / Python 版本 badges
- README "5 分钟上手" 步骤 4 补充 `<hash>` 切图 URL 的来源说明 + jq 示例
- README "开发 / 测试" 说明 `jsonschema` 的可选用途
- README 新增 "贡献" 章节(分支约定、commit 规范、breaking change 流程)
- `SKILL.md` 输出 JSON 速览前增加"概念示意"说明,引导查 fixtures 看真实样例
- `SKILL.md` 给 `inspect` 命令加场景注释(CI 回归检测)

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
