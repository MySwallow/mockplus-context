# Troubleshooting

按"看到什么现象 → 怎么修"组织。完整退出码见 [`../SKILL.md`](../SKILL.md)。

## Cookie 类

### `ERR: cookie 未配置,运行 mockplus cookie set`

`exit 10`。本机既无 `MOCKPLUS_COOKIE` 环境变量,也无 `~/.config/mockplus/cookie` 文件。

```bash
mockplus cookie set      # 交互式粘贴
mockplus cookie status   # 验证文件已写入
```

### `ERR: cookie 为空`

`exit 12`。stdin / 文件没有有效内容(只有注释或空白)。重新写入即可:

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

### `cookie status` 显示损坏的时间戳

`expires_at` 注释行格式错误或缺失(老格式 cookie 文件)。重新 `cookie set` 一次。

### `cookie test`:`ERR: 网络错误 ... `

`exit 14`。
- 检查网络:`curl -sS -v -I https://app.mockplus.cn/ 2>&1 | head -20`
- 境外节点经常被丢包,挂回国代理
- Cloudflare 大概率不挡 `urllib`,但若挡了会返回 403 HTML

---

## URL / 节点查找类

### `ERR: URL 缺少 /app/<APP_ID>/ 段`

URL 不是 Mockplus 设计稿链接。合法格式:`https://app.mockplus.cn/app/<APPID>/...`。

### `ERR: URL 指向 group,先用 mockplus tree ...`

`exit 22`。URL 中的 ID 是 group 或 app,而不是单页。先用 `tree` 浏览,挑出具体 page id:

```bash
mockplus tree <APP_ID>
# 或
mockplus tree <APP_ID> --format json | jq -r '.. | objects | select(.kind=="page") | "\(.id) \(.name)"'
```

然后:

```bash
mockplus data '<URL>'   # 注意:必须是 page URL,不是 group
```

### `ERR: API code != 0`

`exit 21`。`_index.json` 拉不到,常见原因:
- cookie 过期 → `mockplus cookie set`
- 项目被冻结 / 删除 / 无权限

若怀疑 cache 过期:

```bash
mockplus data '<URL>' --refresh
mockplus tree <APP_ID> --refresh
```

---

## 输出 schema / transform 类

### `_meta.unhandledFields` 不为空

Mockplus 升级了 sketch schema,有新字段没消费。
- 短期无影响(transform 仅丢弃未识别字段,不报错)
- 长期需要更新 `transform.py` 里的 `LAYER_HANDLED` / `BASIC_HANDLED` 集合,反馈 issue

### `ERR: transform 输出校验失败`

`exit 2`。transform 输出不符合契约(`metadata.pageId` / `nodes` / `globalVars.styles` 类型不对)。多半是新字段触发的 bug。带 `--refresh` 重拉一次,贴 stderr 提 issue。

### nodes 里出现 `type: "_ERROR"` 占位节点

单节点 transform panic,容错降级输出占位。其他节点不受影响。带相关 `data.json` 提 issue。

### nodes 里出现 `type: "_UNKNOWN_<TYPE>"` 占位

`REAL_TYPE_TO_V5` 映射不覆盖该类型。看 `_meta.warnings` 找具体 realType,在 `transform.py` 加映射或反馈 issue。

---

## 切图下载类

### `mockplus download`:`目标切图: 0 个`

`extract_slices` 没在 data.json 里找到 slice 节点。可能原因:
- 该页没有切图(纯矢量/纯文字)
- `--nodes hash1,hash2` 中的 hash 不匹配 — 检查 `data.yaml` 里的 `imageRef` 字段是否一致

### `mockplus download` 失败一部分 URL

stderr 列出 FAIL 的 hash + 错误消息。常见:
- CDN 临时 5xx → 重跑 `download`(已下载的会自动跳过)
- 境外节点丢包 → 挂回国代理
- 文件权限错误 → 检查 `--out` 目录可写

---

## API 响应类

### `ERR: API code=4001 msg=未登录`

Cookie 完全无效。`mockplus cookie set` 重新写。

### `ERR: API code=4030 msg=无权访问该项目`

cookie 是别人的账号 / 该账号被踢出项目。换正确账号的 cookie。

### `ERR: API code=非 0 msg=...`

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

### `ModuleNotFoundError: No module named 'yaml'`

PyYAML 没装:

```bash
pip install PyYAML
# 或
pip install -r tests/requirements.txt
```

### `ImportError: cannot import name 'client'`

确保 cwd 在仓库根目录调用 `python3 skills/mockplus-context/scripts/mockplus.py`,或把 skill 内 `scripts/` 加入 `PYTHONPATH`。

---

## 不在本表里?

提 issue,贴:
- 完整命令(打码 cookie / APP_ID)
- 完整 stderr 输出
- `mockplus cookie status` 输出
- macOS / Linux 版本 + Python 版本
