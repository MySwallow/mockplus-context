# Troubleshooting

按"看到什么现象 → 怎么修"组织。退出码完整列表见 `docs/api-reference.md`。

## Cookie 类

### `ERR: 未找到 cookie(运行:mockplus cookie set)`

`exit 10`。本机既无 `MOCKPLUS_COOKIE` 环境变量,也无 `<repo_root>/config/cookie` 文件。

```bash
mockplus cookie set      # 交互式粘贴
mockplus cookie status   # 验证文件已写入
```

### `ERR: cookie 文件 ... 没有有效内容`

`exit 12`。文件存在但只有注释或空白。重新写入即可:

```bash
mockplus cookie clear
mockplus cookie set
```

### `cookie test`:`✗ cookie 无效或权限不足(code=4xxx)`

`exit 15`。两种可能:
1. **cookie 真的过期**(最常见,约 30 天):
   ```bash
   mockplus cookie set   # 浏览器重登 → 拷 cookie → 重新粘贴
   ```
2. **APP_ID 你无权限**:换个你能在浏览器打开的项目 ID 重试。

### `cookie status` 显示 `Days remaining: ?`

`expires_at` 注释行缺失(老格式 cookie 文件)。重新 `cookie set` 一次。

### `cookie test`:`请求失败(网络或 HTTP 层)`

`exit 14`。
- 检查网络:`curl -sS -v -I https://app.mockplus.cn/ 2>&1 | head -20`
- 境外节点经常被丢包,挂回国代理
- Cloudflare 大概率不挡 `urllib`,但若挡了会返回 403 HTML

---

## URL / 节点查找类

### `ERR: URL 缺少 /app/<APP_ID>/ 段`

URL 不是 Mockplus 设计稿链接。合法格式:`https://app.mockplus.cn/app/<APPID>/...`。

### `ERR: URL 指向 group,先用 tree 浏览`

`exit 22`。URL 中的 ID 是 group 或 app,而不是单页。先用 `tree` 浏览,挑出具体 page id:

```bash
mockplus tree <APP_ID>
# 或
mockplus tree <APP_ID> --format json | jq -r '.. | objects | select(.kind=="page") | "\(.id) \(.name)"'
```

然后:

```bash
mockplus get-data <APP_ID>:<PAGE_ID>
```

### `ERR: index API code != 0`

`exit 21`。`_index.json` 拉不到,常见原因:
- cookie 过期 → `mockplus cookie set`
- 项目被冻结 / 删除 / 无权限

若怀疑 cache 过期:

```bash
mockplus get-data <URL> --refresh
mockplus tree <APP_ID> --refresh
```

---

## 输出 schema / transform 类

### `_meta.unhandledFields` 不为空

Mockplus 升级了 sketch schema,有新字段没消费。
- 短期无影响(transform 仅丢弃未识别字段,不报错)
- 长期需要更新 `_transform.py` 里的 `LAYER_HANDLED` / `BASIC_HANDLED` 集合,反馈 issue

### `exit 50`:输出 schema 校验失败

transform 输出不符合契约。多半是新字段触发的 bug。带 `--refresh` 重拉一次,贴 stderr 提 issue。

### nodes 里出现 `type: "error"` 占位节点

单节点 transform panic,容错降级输出占位。其他节点不受影响。带相关 `data.json` 提 issue。

---

## 切图下载类

### `download-assets`:`invalid host`

`exit 2`。URL 不在 `img01.mockplus.cn` 或 `img02.mockplus.cn`。Mockplus CDN 切图地址固定,其他 host 不接受。

### `download-assets`:`unsupported format`

`exit 2`。`url` 或 `fileName` 不是 `.png` 结尾。首版仅支持 PNG。

### `download-assets` 失败一部分 URL

`failed` 数组里会列出失败的 URL 与原因。常见:
- CDN 临时 5xx → 重跑 `download-assets`(已下载的会以 `cached: true` 跳过)
- 境外节点丢包 → 挂回国代理

---

## API 响应类

### `ERR: API code=4001 message=未登录`

Cookie 完全无效。`mockplus cookie set` 重新写。

### `ERR: API code=4030 message=无权访问该项目`

cookie 是别人的账号 / 该账号被踢出项目。换正确账号的 cookie。

### `ERR: API code=非 0 message=...`

直接看 message,通常是限流 / 项目被冻结等业务错误。

---

## 安装 / 执行类

### `python3: command not found`

需要 Python 3.8+。

```bash
# macOS
brew install python3

# Ubuntu / Debian
apt-get install python3
```

### `ImportError: cannot import name '_xxx'`

确保从仓库根目录调用 `python3 scripts/mockplus.py`,或把 `scripts/` 加入 `PYTHONPATH`。

---

## 不在本表里?

提 issue,贴:
- 完整命令(打码 cookie / APP_ID)
- 完整 stderr 输出
- `mockplus cookie status` 输出
- macOS / Linux 版本 + Python 版本
