# Troubleshooting

按"看到什么现象 → 怎么修"组织。

## Cookie 类

### `ERR: 未找到 cookie(运行:mockplus cookie set)`

`exit 10`。本机既无 `MOCKPLUS_COOKIE` 环境变量,也无 `<repo_root>/config/cookie` 文件。

```bash
mockplus cookie set      # 交互式粘贴
mockplus cookie status   # 验证文件已写入
```

### `ERR: cookie 文件 ... 没有有效内容`

`exit 10`。文件存在但只有注释或空白。重新写入即可:

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
- Cloudflare 大概率不挡 `curl`,但若挡了会返回 403 HTML

---

## URL / 节点查找类

### `ERR: URL 缺少 /app/<APP_ID>/ 段`

URL 不是 Mockplus 设计稿链接。合法格式:`https://app.mockplus.cn/app/<APPID>/...`。

### `ERR: page id=xxx not in _pages.json`

`exit 31`。`_pages.json` 里没有该 PAGE_ID。常见原因:
- URL 中的 ID 是 group 而不是 page → 用 `mockplus fetch` 智能分发,或 `mockplus group`
- 设计稿被移动/删除/重命名了 → `_index.json` 缓存过期:
  ```bash
  rm <out_root>/<APP_ID>/_index.json
  mockplus fetch <URL>
  ```

### `ERR: group id=xxx not found`

`exit 41`。同上,删 `_index.json` 重拉。

### `TARGET_ID=xxx 不在 _index.json 树里`

`exit 42`(`fetch` 子命令)。同上。

---

## 切图 / 下载类

### `WARN: design.png 不是合法 PNG`

不影响主流程。Mockplus 偶尔会给一个占位 PNG(text/html 或空)。`data.json` 仍然正确。

### `切图:下载 0,跳过 N,失败 M`

CDN(`img02.mockplus.cn`)对应 IP 临时不通。重跑 `mockplus assets <PAGE_DIR>` 一般会自愈
(脚本会跳过已下载的)。

仍失败:
- 检查 `MOCKPLUS_DEBUG=1 mockplus assets ...` 看具体 URL
- 浏览器直接打开那个 URL,看是 404 / 403 / 超时
- 境外节点先翻墙

### 整个 `data.json` 下载失败或为空

`exit 33`。同上,先 curl 那个 dataURL 看到底是什么响应:

```bash
URL="$(python3 -c "import json;print(json.load(open('mockplus-cache/<APPID>/pages/<PID>/page-meta.json'))['dataURL'])")"
curl -v "$URL" 2>&1 | head -30
```

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

### `ERR: 缺少工具:curl python3`

`exit 3`。

```bash
# macOS
brew install curl python3

# Ubuntu / Debian
apt-get install curl python3
```

### `bash: bin/mockplus: Permission denied`

```bash
chmod +x bin/mockplus scripts/validate.sh tests/smoke.sh
```

---

## CI 类

### shellcheck 报 SC1091 / SC2034

非阻塞,validate.sh 已用 `-e SC1091,SC2034 -S warning` 排除。
新引入的警告需要修复或加入排除列表。

### macOS 上 `stat` 命令不同

`cookie status` 已用 `stat -f '%Sp' 2>/dev/null || stat -c '%A'` 双系统兼容。

---

## 不在本表里?

提 issue,贴:
- 完整命令(打码 cookie / APP_ID)
- 完整 stderr 输出(`MOCKPLUS_DEBUG=1` 加上)
- `mockplus cookie status` 输出
- macOS / Linux 版本
