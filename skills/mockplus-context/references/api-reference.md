# API Reference

所有命令的完整签名 + 退出码 + 示例。

## 全局环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MOCKPLUS_COOKIE` | (空) | 优先于文件 |
| `MOCKPLUS_COOKIE_FILE` | `skills/mockplus-context/config/cookie` | cookie 文件位置(基于 `_cookie.py` 所在的 skill 目录,**不是仓库根**) |
| `MOCKPLUS_OUT_ROOT` | `~/.cache/mockplus-context` | API 响应 cache 根 |

## 退出码

- `0` 成功
- `2` CLI 参数错
- `10` cookie 未配置
- `11` `--from-file` 文件不存在
- `12` cookie 为空
- `14` HTTP 层失败
- `15` API code != 0(cookie 测试场景)
- `21` index API code != 0
- `22` TARGET_ID 误判 / 与子命令不匹配
- `50` 输出 schema 校验失败

---

## `mockplus get-data <URL> [--refresh]`

拉单页 sketch JSON → 转结构化 JSON → 输出到 stdout。

参数:
- `<URL>`: 完整 Mockplus develop 页 URL 或 `<APP_ID>:<PAGE_ID>` 短形式
- `--refresh`: 跳过 cache,强制重新拉

stdout: 结构化 JSON(字段速览见 `../SKILL.md` "## 输出 JSON 速览" 章节)。

---

## `mockplus tree <APP_ID> [--format text|json] [--refresh]`

树形打印项目结构。

`--format text`(默认): 含 emoji 的层级文本。
`--format json`: 结构化树,每节点 `{id, name, kind: "group"|"page", device?, size?, children?}`。

孤儿 page(parentID 指向不存在 group)通过 stderr 警告。

---

## `mockplus download-assets --downloads '[...]' --local-path <DIR>`

并发下载 CDN 切图(无 cookie 依赖)。

`--downloads`: JSON 数组,每项 `{ "url": "...", "fileName": "..." }`。

校验:
- `url` 必须 `img(01|02).mockplus.cn` host
- `url` 与 `fileName` 必须 `.png` 结尾
- 文件已存在(size > 0) skip(`cached: true`)

并发上限 8。失败的 URL 不重试。

stdout: `{ downloaded: [...], failed: [...] }`

---

## `mockplus inspect <URL> [--refresh]`

拉单页 + transform,只输出统计:

```json
{ "nodes", "styles", "sharedStyles", "typesSeen", "assets", "unhandledFields", "warnings" }
```

用于回归检测(检查 Mockplus 是否升级了 sketch schema)。

---

## `mockplus cookie set [--from-file PATH]`

写 cookie。stdin / TTY / 文件。自动 `chmod 600`,文件首部加 `# set_at:` `# expires_at:` 注释。

---

## `mockplus cookie test <APP_ID>`

调一次 design API 验证 cookie 有效。退出码 0 = ok, 15 = API 拒绝。

---

## `mockplus cookie status`

打印路径 / 权限 / 设置时间 / 剩余天数。未配置也返回 0。

---

## `mockplus cookie clear`

删 cookie 文件(幂等)。

---

## `mockplus cookie path`

打印 cookie 文件路径(stdout)。
