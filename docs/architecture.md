# Architecture

## 一张图

```
USER
  │
  │  mockplus fetch <URL>
  ▼
┌─────────────────────────────────────────────┐
│  bin/mockplus  (CLI dispatcher)             │
│  - 加载 lib/*.sh                            │
│  - 派发到 cmd_* / cookie_*                  │
└─────────┬───────────────────────────────────┘
          │
          │ source 顺序: common → http → cookie → api → page → group → fetch
          ▼
┌───────────────────────────────────┐
│  lib/common.sh                    │  日志 / 错误 / 依赖检查
│  lib/http.sh                      │  curl_app / curl_cdn 封装
│  lib/cookie.sh                    │  cookie 生命周期
│  lib/api.sh                       │  URL 解析 + index 拉取 + 树查询
│  lib/page.sh                      │  单页 + 切图
│  lib/group.sh                     │  分组批量(调 page.sh)
│  lib/fetch.sh                     │  智能分发(URL → page / group)
└─────────┬─────────────────────────┘
          │ curl + python3
          ▼
┌───────────────────────────────┐    ┌───────────────────────────┐
│  app.mockplus.cn              │    │  img02.mockplus.cn        │
│  (Cloudflare + REST API)      │    │  (华为云华东 CDN)         │
│                               │    │                           │
│  /api/v1/app/module/<APPID>   │    │  /idoc/.../<hash>.json    │
│    /design                    │    │  /idoc/sketch/<h>/x.png   │
│                               │    │  /idoc/sketch/<h>/x.svg   │
└───────────────────────────────┘    └───────────────────────────┘
          │                                    │
          │ JSON: { code, payload.pages[] }    │ raw Sketch JSON / PNG / SVG
          ▼                                    ▼
┌─────────────────────────────────────────────┐
│  ./mockplus-cache/<APPID>/                  │
│    _index.json         原始 API 响应         │
│    _pages.json         扁平 pages + groups   │
│    groups/<GID>/                            │
│      _meta.json                             │
│      _page-ids.txt                          │
│    pages/<PID>/                             │
│      page-meta.json                         │
│      data.json         (Sketch 结构)         │
│      design.png        (整页 @2x)            │
│      assets-manifest.json                   │
│      assets/<hash>.png / .svg               │
└─────────────────────────────────────────────┘
```

## 模块职责

| 模块 | 行数 | 职责 | 依赖 |
|---|---|---|---|
| `bin/mockplus` | ~55 | CLI dispatch,加载 lib | 全部 lib |
| `lib/common.sh` | ~20 | `die` / `info` / `debug` / `require_tools` | — |
| `lib/http.sh` | ~25 | `http_app` / `http_cdn` curl 封装 | common, cookie |
| `lib/cookie.sh` | ~150 | cookie set/test/status/clear/path/load | common, http(test 用) |
| `lib/api.sh` | ~120 | URL 解析 / index 拉取 / tree 打印 / 节点类型查询 | common, http |
| `lib/page.sh` | ~95 | 单页 data.json + design.png + 切图 | common, http, api |
| `lib/group.sh` | ~70 | 分组批量(调 cmd_page) | common, api, page |
| `lib/fetch.sh` | ~40 | 智能 URL 分发 | common, api, page, group |

总计 ~575 行 shell + 嵌入的 python3 heredoc。

**为什么 Python 嵌在 shell heredoc 里?** 因为只用标准库(json / urllib / datetime / re),
不引入独立 `.py` 文件,部署只需复制整个仓库,无 PYTHONPATH 顾虑。Bash 处理子进程 +
Python 处理 JSON 的组合,比纯 bash 用 jq + python 切换更直观。

## 数据流(以 `mockplus fetch` 为例)

```
URL
 │
 │ cmd_url (lib/api.sh)
 ▼
APP_ID + TARGET_ID
 │
 │ ensure_index (lib/api.sh) → cmd_index(若 _index.json 缺失或 >24h)
 │   ├─ http_app /api/v1/app/module/<APPID>/design
 │   ├─ 校验 code == 0
 │   ├─ 保存 _index.json
 │   └─ 扁平化 → _pages.json (pages[] + groups[])
 ▼
_index.json + _pages.json
 │
 │ tree_kind (lib/api.sh) → 在 _index.json 递归查 TARGET_ID
 ▼
"page" or "group" or "notfound"
 │
 ├─ "page"  → cmd_page (lib/page.sh)
 │             ├─ 找 PAGE_ID in _pages.json → page-meta.json
 │             ├─ http_cdn dataURL → data.json
 │             ├─ http_cdn imageURL → design.png (+ PNG magic 校验)
 │             └─ cmd_assets (lib/page.sh):遍历 data.json 找 slice → 下载到 assets/
 │
 └─ "group" → cmd_group (lib/group.sh)
              ├─ 找 GROUP_ID in _index.json,递归收集所有 dataURL 页 id
              ├─ 写 _meta.json + _page-ids.txt
              └─ 逐个调 cmd_page
```

## 关键 Mockplus API

### `GET /api/v1/app/module/<APPID>/design`

| Header | 值 |
|---|---|
| `Accept` | `application/json` |
| `X-MOCKPLUS-APP` | `idoc-for-web|1.41.0-cn|macOS` |
| `x-mockplus-lang` | `zh-cn` |
| `Referer` | `https://app.mockplus.cn/` |
| `Cookie` | (用户的会话 cookie) |

响应:
```json
{
  "code": 0,
  "message": "ok",
  "payload": {
    "pages": [/* 嵌套 group/page 树 */]
  }
}
```

树节点结构:
```json
{
  "_id": "0-ITsFIbmL",
  "name": "申请页",
  "isGroup": false,
  "parentId": "g-sub1",
  "size": {"width": 375, "height": 812},
  "backgroundColor": "#ffffffff",
  "device": "ios1x",
  "dataURL": "https://img02.mockplus.cn/idoc/.../xyz.json",
  "imageURL": "https://img02.mockplus.cn/idoc/sketch/aaa/wbyrvwvvlh.png",
  "slicesCount": 3,
  "children": []
}
```

`isGroup: true` 节点没有 `dataURL`,只有 `children[]`。

### CDN

`dataURL` 指向 Sketch 从 Mockplus 导出的原始结构化 JSON。
关键字段见 [api-reference.md](api-reference.md) 和 Mockplus 官方文档。

`imageURL` 指向 `@2x` 整页 PNG。

切图 URL 在 `data.json` 的递归 `layers.children[].slice.bitmapURL/svgURL`,
形如 `https://img02.mockplus.cn/idoc/sketch/<hash>/wbyrvwvvlh.png`。
我们用 `<hash>` 段做文件名(同一切图的 PNG/SVG 共享 hash)。

## 缓存策略

| 文件 | 何时刷新 |
|---|---|
| `_index.json` | mtime > 24h 时自动重拉;`rm` 后强制刷新 |
| `_pages.json` | `cmd_index` 跑时一并重生成 |
| `pages/<PID>/data.json` | 不自动检测过期;`rm` 后重跑 `page` |
| `pages/<PID>/design.png` | 同上 |
| `assets/<hash>.{png,svg}` | 已存在且非空则跳过;清空文件或 `rm` 后重拉 |

## 与下游的边界

mockplus-context **只产数据**:

```
mockplus-context  ←─→  ./mockplus-cache/  ←─→  下游(任意)
        ↑                    ↑
        │                    │
   API + CDN              文件系统
```

下游可以:
- LLM 直接读 `data.json` 推断 UI
- 自定义 spec 转换器把 `data.json` 转任意格式(spec.md / Figma 兼容 JSON / Sketch 原 doc)
- 渲染器把 `data.json` + `assets/` 拼成 HTML/Canvas 预览
- UI 还原循环工具(如 `flutter-visual-loop`)消费 `data.json` + `design.png` + `assets/`

**本仓库故意不实现以上任何一个**——保持职责单一,便于组合。
