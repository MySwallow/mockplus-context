# Changelog

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
