# API Reference

所有命令的完整签名 + 退出码 + 示例。

## 全局

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `MOCKPLUS_COOKIE` | (空) | 优先于文件 |
| `MOCKPLUS_COOKIE_FILE` | `<repo_root>/config/cookie` | 覆盖默认 cookie 文件位置(见 docs/cookie.md) |
| `MOCKPLUS_OUT_ROOT` | `./mockplus-cache` | 默认输出根 |
| `MOCKPLUS_DEBUG` | (空) | `=1` 时 stderr 打印每个请求 URL |

退出码规约:
- `0` 成功
- `1` 通用错误
- `2` CLI 参数错(未知命令 / 缺参数)
- `3` 依赖缺失(curl / python3)
- `10` cookie 未配置
- `11-15` cookie 子命令错(详见下)
- `21` index API 响应非 success
- `31-33` page 子命令错
- `41` group 子命令错
- `42-43` fetch 子命令错

---

## `mockplus cookie set [--from-file PATH]`

写入 cookie。

| 来源 | 触发条件 |
|---|---|
| stdin(TTY) | 默认,显示提示后读一行 |
| stdin(管道) | `echo '...' \| mockplus cookie set` |
| 文件 | `mockplus cookie set --from-file /path/to/cookie` |

写入后自动:
- `chmod 700` 父目录、`chmod 600` cookie 文件
- 文件首部加注释行:`# set_at:`、`# expires_at:`(估算 30d)

退出码:
- `0` 写入成功
- `2` 未知参数
- `11` `--from-file` 指定的文件不存在
- `12` cookie 为空

---

## `mockplus cookie test <APP_ID>`

调一次 `/api/v1/app/module/<APP_ID>/design` 验证 cookie 有效。

参数:
- `APP_ID` 必填,任意一个你能访问的 Mockplus 项目 ID(URL `/app/XXX/`)

退出码:
- `0` API 返回 `code == 0`
- `13` 缺 APP_ID
- `14` HTTP 层失败(网络不通)
- `15` API 返回 `code != 0`

---

## `mockplus cookie status`

打印:文件路径 / 文件权限 / 设置时间 / 预估到期 / 剩余天数。

不存在时:打印 `Status: 未配置(运行 mockplus cookie set)`,退出 `0`(无 cookie 也不算错)。

---

## `mockplus cookie clear`

删除 cookie 文件。文件不存在也返回 `0`(幂等)。

---

## `mockplus cookie path`

打印 cookie 文件路径(stdout)。可被脚本捕获:`COOKIE="$(mockplus cookie path)"`。

---

## `mockplus url <URL>`

解析 URL,**输出 shell 可 eval 的两行**:

```bash
$ mockplus url 'https://app.mockplus.cn/app/5gAIPn9LE/develop/design/0-ITsFIbmL'
APP_ID=5gAIPn9LE
TARGET_ID=0-ITsFIbmL

# 用法:
eval "$(mockplus url '<URL>')"
echo "$APP_ID $TARGET_ID"
```

如果 URL 没有具体 page/group(如 `/app/<APPID>`),`TARGET_ID` 为空字符串。

退出码:
- `0` 解析成功
- `1` URL 格式不对

---

## `mockplus index <APP_ID> [out_root]`

GET `/api/v1/app/module/<APP_ID>/design`,生成:

| 文件 | 内容 |
|---|---|
| `<out_root>/<APP_ID>/_index.json` | 原始 API 响应 |
| `<out_root>/<APP_ID>/_pages.json` | 扁平化 `{pages:[], groups:[]}` |

`out_root` 默认 `$MOCKPLUS_OUT_ROOT`(`./mockplus-cache`)。

stdout 打印 `<out_root>/<APP_ID>` 路径,方便脚本捕获。

退出码:
- `0` 成功
- `21` API 返回 `code != 0`(常见:cookie 过期、APP_ID 无权限)

---

## `mockplus tree <APP_ID> [out_root]`

树形打印项目层级。会自动调用 `index`(若 `_index.json` 不存在或 >24h)。

```
📁 v1  [g-root]
  📁 采购模块  [g-sub1]
    📄 申请页  [p-001]  (375x812)
    📄 审批页  [p-002]  (375x812)
  📄 首页  [p-003]  (375x812)
```

`📁` 是 group,`📄` 是 page;后跟节点 ID;page 还显示尺寸。

---

## `mockplus page <APP_ID> <PAGE_ID> [out_root]`

拉单页,产物:

```
<out_root>/<APP_ID>/pages/<PAGE_ID>/
├── page-meta.json          从 _pages.json 抽出的元信息
├── data.json               Mockplus/Sketch 原始结构化数据
├── design.png              整页截图(@2x)
├── assets-manifest.json    切图清单
└── assets/
    ├── <hash>.png
    └── <hash>.svg
```

自动调用 `assets` 子流程。

stdout 打印 page 目录路径。

退出码:
- `0` 成功(切图部分失败不算 fatal)
- `31` PAGE_ID 不在 `_pages.json`
- `32` `data.json` 缺失
- `33` `data.json` 下载失败或为空

---

## `mockplus group <APP_ID> <GROUP_ID> [out_root]`

批量拉一个分组下所有页面(递归)。

产物:

```
<out_root>/<APP_ID>/
├── groups/<GROUP_ID>/
│   ├── _meta.json          { groupId, name, path, pageCount, pages:[{id,name}] }
│   └── _page-ids.txt       该 group 下所有 page id,每行一个
└── pages/<PAGE_ID>/        每个 page 跟 `mockplus page` 一样
    └── ...
```

逐个 page 调 `cmd_page`,某 page 失败不阻塞后续。最终打印 `成功 X / 失败 Y / 总 Z`。

退出码:
- `0` 完成(即使部分 page 失败)
- `41` GROUP_ID 不在 `_index.json` 树里

---

## `mockplus assets <PAGE_DIR>`

只补该 page 目录的切图。前提:`<PAGE_DIR>/data.json` 已存在。

幂等:已下载且非空的切图自动跳过。

退出码:
- `0` 成功(单个切图失败不算 fatal,只打印 `FAIL` 行)
- `32` `data.json` 缺失

---

## `mockplus fetch <URL> [out_root]`

智能分发:解析 URL → 在 `_index.json` 树里判断 TARGET_ID 是 page / group / 不存在,
然后调对应子命令。

| TARGET_ID 类型 | 行为 |
|---|---|
| `page` | 调 `cmd_page` |
| `group` | 调 `cmd_group` |
| 空 | 只更新 `_index.json`,提示用户下一步 |
| `notfound` | 报错(URL 错或缓存过期) |

退出码:
- `0` 成功
- `42` TARGET_ID 不在树里
- `43` 无法判断类型(理论上不会发生)
