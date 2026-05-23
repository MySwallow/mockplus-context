---
name: mockplus-context
description: 从 Mockplus(摹客 app.mockplus.cn)设计稿抓取结构化 JSON 与切图。用于以下场景,即使用户没明说"用 Mockplus 工具":粘贴 `https://app.mockplus.cn/app/<APPID>/develop/design/<PAGEID>` 形式的 URL、要求"读 Mockplus 设计稿"、"按 Mockplus 还原 UI"、"导出 Mockplus 切图"、"把这个 Mockplus 页面变成 Vue/Flutter/小程序",或者从 Mockplus URL 推断页面 ID/项目结构。LLM 拿到分层 JSON(metadata + globalVars + nodes)即可直接还原,无需解析 sketch 原生 JSON。
---

# Mockplus Context

把 Mockplus develop URL 转换为结构化 JSON + 本地切图。

启动时声明:**"Using mockplus-context to extract <PAGE_ID> from Mockplus."**

## 何时触发

- 用户给出 Mockplus develop URL:`https://app.mockplus.cn/app/<APPID>/develop/design/<TARGET_ID>`
- 用户要"读 Mockplus 设计稿"、"按 Mockplus 还原 UI"、"导出 Mockplus 切图"
- 用户要把 Mockplus 页面转 Vue / Flutter / 小程序 / 任意前端代码

**不触发**:
- 输入只是一张孤立 PNG → 让用户先找到对应 Mockplus 页面 URL
- 输入不是 mockplus.cn 域 → 此 skill 不适用

## 前置:cookie 配置(用户一次性)

```bash
python3 scripts/mockplus.py cookie set
# 浏览器(已登录 mockplus.cn) F12 → Application → Cookies → app.mockplus.cn
# 把全部 cookie 拼成一行粘贴
```

Cookie 有效期约 30 天,过期重新 `set`。详细的浏览器抓 cookie 步骤是给真人用户看的,不在 LLM 范围。

## LLM 工作流(收到 URL 时按这个顺序)

1. **不确定 page id**(URL 指向 group 或只有 APP_ID):跑 `python3 scripts/mockplus.py tree <APP_ID>` 浏览结构,从树中选出具体 page id。
2. **URL 指向 page**:跑 `python3 scripts/mockplus.py get-data <URL>` 拿结构化 JSON。
3. **扫输出 JSON 的 nodes**,收集所有 `asset.url`(切图)和 `metadata.pageImage.url`(整页效果图)。
4. **语义化命名后下载**:`python3 scripts/mockplus.py download-assets --downloads '[...]' --local-path <DIR>`。
5. 进入下游(代码生成、还原对照等)。

## 命令参考

```bash
mockplus.py get-data <URL>                       # 单页结构化 JSON 到 stdout
mockplus.py tree <APP_ID> [--format text|json]   # 项目结构(text emoji / json 树)
mockplus.py download-assets --downloads '[...]' --local-path <DIR>
mockplus.py cookie {set|test|status|clear|path}  # cookie 管理(只给真人用,LLM 不调)
mockplus.py inspect <URL>                        # 统计 + 异常(CI 回归检测;Mockplus 升级 schema 时立刻可见)
```

> Mockplus API 的物理约束:只能按 **整页(page)** 拉数据。Group/sub-group 没有节点级 API,所以 `get-data` 只接受 page URL;group 浏览靠 `tree`。

## 输出 JSON 速览(`get-data`)

> 以下是**字段名概念示意**(不是合法 JSON,只列每段会出现哪些 key)。真实输出样例跑 `mockplus inspect <URL>` 自检,或读 `tests/fixtures/expected/*.json`。

```jsonc
{
  "metadata": {
    "appId", "pageId", "name", "device", "canvas", "backgroundColor",
    "artboardScale", "pluginVersion", "pageImage"
  },
  "globalVars": {
    "styles": {
      "fill_001":   { "type": "color", "color": "#rrggbbaa" },
      "text_001":   { "fontFamily", "fontSize", "fontWeight", "lineHeight", "color" },
      "shadow_001": { "color", "offsetX", "offsetY", "blur", "spread" },
      "stroke_001": { "color", "width", "position" }
    },
    "sharedStyles": {
      "<uuid>": { "displayName", "kind", "stylesRef": ["fill_001", "text_002", ...] }
    }
  },
  "nodes": [
    {
      "id", "name", "type", "realType",
      "bounds": { "top", "left", "width", "height" },
      "fills", "strokes", "radius", "shadows", "sharedStyle",
      "text", "sourceComponent", "library", "symbol", "asset",
      "children": [...]
    }
  ],
  "_meta": {
    "transformVersion", "sketchPluginVersion", "documentVersion",
    "inputFieldsTotal", "unhandledFields", "warnings"
  }
}
```

命令完整签名与字段映射规则查 `references/api-reference.md`。端到端调用样例查 `references/examples.md`。遇到错误信息查 `references/troubleshooting.md`。

## 关键设计

- **bounds 沿用 Sketch 原生** `{top, left, width, height}`,LLM 写 CSS 直觉一致
- **type / realType 双轨**:`type` 粗类(group/text/rect/...,LLM 用来选标签),`realType` 细类(Artboard/SymbolInstance/...,LLM debug 用)
- **globalVars 去重**:fill/text/shadow/stroke 用指纹合并,nodes 引用 `fill_001` 而非内联,token 占用大幅下降
- **`_meta.unhandledFields`**:Mockplus 升级 schema 时立刻可见,不会静默丢字段

## 常见失败

| 现象 | 处理 |
|---|---|
| `cookie 未配置` (exit 10) | 跑 `mockplus.py cookie set` |
| `API code != 0` (exit 21) | cookie 过期 → `mockplus.py cookie set` 重配 |
| `URL 指向 group,先用 tree 浏览` (exit 22) | URL 不是 page,先 `tree` 找具体 page id |
| `_meta.unhandledFields` 不为空 | Mockplus 改 schema 了,反馈 issue |
| 切图下载报 `invalid host` / `unsupported format` | URL 不在 `img(01\|02).mockplus.cn` 或不是 `.png` |

## 隐私 & 安全

- cookie 只读取,不上传;`config/cookie` 自动 `chmod 600`
- API 响应缓存在 `~/.cache/mockplus-context/`,由用户自行清理
- 切图保存到 `--local-path` 指定目录,由用户自管
