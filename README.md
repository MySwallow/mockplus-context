# mockplus-context

> 通用的 Mockplus(摹客)设计稿抓取工具 —— shell + Python,**无任何外部依赖**。
> 把 idoc 的原始结构化数据 + 切图,通过 URL / 分组 ID 一键拉到本地。

`mockplus-context` 是一个**纯抓取 CLI**:输入 URL 或 APP_ID/GROUP_ID,
输出本地文件(JSON / PNG / SVG)。**不做 spec 转换、不做代码生成**——
怎么用拉下来的数据(交给 LLM / 自己渲染 / 写自定义脚本)是上层的事。

兼容场景:

- 任何编辑器 / 终端 / CI
- 任何 LLM(把 `data.json` 内容当 prompt context)
- 其他 AI 工具链(只要能读本地文件即可消费输出)

## 为什么需要它

- Mockplus 没有官方 MCP,也没有公开 API
- 浏览器 F12 能看到设计稿其实是从 CDN 拉一个 Sketch 导出的 JSON,字段非常完整
- 一旦把这份 JSON + 切图拉下来,任何下游(LLM / 渲染器 / 代码生成器)就拿到了
  **所有真值**(位置、尺寸、颜色、字体、圆角、阴影、切图),不再需要看 PNG 猜
- 对标 Figma 的 figma-context,但针对 Mockplus 的 idoc

## 三大能力

1. **基于 URL 一键拉取**:`mockplus fetch <URL>` 自动判断是单页还是分组,补齐 `_index.json`
2. **分组批量**:`mockplus group <APP_ID> <GROUP_ID>` 把一个分组下所有页面一次拉完
3. **Cookie 全生命周期**:`set/test/status/clear/path`,自动 `chmod 600`,30 天到期提醒

## 安装

只要有 `bash` + `python3` + `curl`(macOS / Linux / Git Bash for Windows / WSL 都满足):

```bash
git clone https://github.com/<you>/mockplus-context.git
cd mockplus-context
./bin/mockplus help               # 直接跑
```

加到 PATH(可选):

```bash
export PATH="$PWD/bin:$PATH"
mockplus help
```


## 5 分钟上手

### 1. 配 cookie(一次)

浏览器登录 `app.mockplus.cn` → F12 → Application → Cookies → `app.mockplus.cn`,把所有
cookie 拼成一行(`key=val; key=val; ...`),粘贴给:

```bash
mockplus cookie set        # 交互式粘贴
mockplus cookie test 5gAIPn9LE   # 任意你能访问的 APP_ID
mockplus cookie status     # 看到期时间
```

Cookie 有效期 ~30 天,过期重新 `set`。详见 [docs/cookie.md](docs/cookie.md)。

### 2. 拉数据

```bash
# 智能(最常用):URL 是单页就拉单页,是分组就批量拉
mockplus fetch 'https://app.mockplus.cn/app/5gAIPn9LE/develop/design/0-ITsFIbmL'

# 看项目目录结构
mockplus tree 5gAIPn9LE

# 单页
mockplus page 5gAIPn9LE 0-ITsFIbmL

# 整个分组(递归)
mockplus group 5gAIPn9LE <GROUP_ID>

# 只补切图(已下载的会跳过)
mockplus assets ./mockplus-cache/5gAIPn9LE/pages/0-ITsFIbmL
```

### 3. 输出目录布局

```
./mockplus-cache/
└── 5gAIPn9LE/                       APP_ID
    ├── _index.json                  原始 design API 响应
    ├── _pages.json                  扁平化的 pages + groups 列表
    ├── groups/<GROUP_ID>/
    │   ├── _meta.json               分组信息(名称/路径/页数)
    │   └── _page-ids.txt            该分组下所有 page id
    └── pages/<PAGE_ID>/
        ├── page-meta.json           从 _pages.json 抽出的页面元信息
        ├── data.json                Mockplus/Sketch 原始结构化数据
        ├── design.png               整页截图(@2x)
        ├── assets-manifest.json     切图清单(hash → name/url/尺寸)
        └── assets/
            ├── <hash>.png
            └── <hash>.svg
```

## 命令一览

| 命令 | 说明 |
|---|---|
| `mockplus cookie set [--from-file PATH]` | 写入 cookie(stdin/文件),chmod 600 |
| `mockplus cookie test <APP_ID>` | 用一个 APP_ID 调一次 API 验证 |
| `mockplus cookie status` | 路径 / 权限 / 设置时间 / 剩余天数 |
| `mockplus cookie clear` | 删除 cookie 文件 |
| `mockplus cookie path` | 打印 cookie 文件路径 |
| `mockplus url <URL>` | 解析 URL → APP_ID + TARGET_ID |
| `mockplus index <APP_ID>` | 拉 `_index.json` + `_pages.json` |
| `mockplus tree <APP_ID>` | 树形打印项目层级 |
| `mockplus page <APP_ID> <PAGE_ID>` | 拉单页(data.json + design.png + 切图) |
| `mockplus group <APP_ID> <GROUP_ID>` | 批量拉一个分组下所有页面 |
| `mockplus assets <PAGE_DIR>` | 只补该 page 目录的切图 |
| `mockplus fetch <URL>` | 智能(自动判断 page/group/app) |

详见 [docs/api-reference.md](docs/api-reference.md)。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MOCKPLUS_COOKIE` | (空) | 若设置,优先于文件(适合 CI/临时会话) |
| `MOCKPLUS_COOKIE_FILE` | `<repo_root>/config/cookie` | 覆盖默认 cookie 文件位置 |
| `MOCKPLUS_OUT_ROOT` | `./mockplus-cache` | 默认输出根目录 |
| `MOCKPLUS_DEBUG` | (空) | `=1` 时打印每个请求的 URL |

## 网络要求

- `app.mockplus.cn`(API,Cloudflare)和 `img02.mockplus.cn`(CDN,华为云华东机房)
  在中国大陆境内可访问,**境外节点经常超时**——必要时挂回国代理
- 没有依赖任何浏览器/Playwright,纯 `curl + python3`

## 文档

| 文档 | 内容 |
|---|---|
| [docs/cookie.md](docs/cookie.md) | Cookie 获取 / 配置 / 更新 / 安全 |
| [docs/api-reference.md](docs/api-reference.md) | 所有命令的完整签名 + 示例 |
| [docs/architecture.md](docs/architecture.md) | 模块划分 / 数据流 / 关键 API |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 按现象分类的故障排查 |
| [docs/examples.md](docs/examples.md) | 真实使用场景示例 |

## 与 figma-context / flutter-visual-loop 的关系

`mockplus-context` 是数据源,职责单一:**拉数据**。
下游想怎么用都可以:

- 给 LLM 直接读 `data.json` 还原 UI
- 给 `flutter-visual-loop` 作为设计稿输入,跑 UI 还原循环
- 自己写脚本把 `data.json` 转 spec.md / Figma JSON / Sketch 文档等

**功能耦合度故意做低**——不做 spec 转换、不做代码生成、不做截图对比。

## 许可证

MIT — 见 [LICENSE](LICENSE)。
