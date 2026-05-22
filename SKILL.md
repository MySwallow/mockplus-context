---
name: mockplus-context
description: 从 Mockplus(摹客 app.mockplus.cn)设计稿抓取结构化数据 + 切图。**触发场景**:用户给出 Mockplus develop 页 URL(形如 `https://app.mockplus.cn/app/<APPID>/develop/design/<PAGEID>`)、要求"读 Mockplus 设计稿"、"按 Mockplus 还原 UI"、"导出 Mockplus 切图"等。返回 figma-context 风格的分层 JSON(metadata + globalVars + nodes),LLM 不再需要解析 raw sketch JSON。
---

# Mockplus Context

把 Mockplus develop URL 转换为结构化 JSON + 本地切图。
**接口对齐 figma-context MCP 心智模型**,LLM 用法一致。

启动时声明:**"Using mockplus-context to extract <PAGE_ID> from Mockplus."**

## 何时使用

- 输入是 Mockplus develop URL: `https://app.mockplus.cn/app/<APPID>/develop/design/<TARGET_ID>`
- 要"读 Mockplus 设计稿"、"按 Mockplus 还原 UI"、"导出切图"等

**不要用于**:
- Figma URL → 用 `figma-context` MCP
- 单张 PNG → 让用户先找到对应 Mockplus 页面

## 前置条件: cookie 配置(用户一次性)

```bash
python3 scripts/mockplus.py cookie set
# 浏览器(已登录 mockplus.cn) F12 → Application → Cookies → app.mockplus.cn
# 把所有 cookie 拼成一行粘贴
```

Cookie 有效期 ~30 天,过期重新 `set`。详见 `docs/cookie.md`。

## LLM 工作流(收到 URL 时按这个顺序)

1. 不知道 page id 或 URL 指向 group/app: `python3 scripts/mockplus.py tree <APP_ID>` 浏览结构,从中挑出具体 page id
2. URL 是 page: `python3 scripts/mockplus.py get-data <URL>` 拿结构化 JSON
3. 扫 nodes,找 `asset.url` + `metadata.pageImage.url`
4. 语义化命名,`python3 scripts/mockplus.py download-assets --downloads '[...]' --local-path <DIR>`
5. 进入下游(还原 Vue/Flutter/小程序 等)

## 命令参考(4 个主子命令 + inspect 辅助)

```bash
mockplus.py get-data <URL>                       # 单页结构化 JSON 到 stdout
mockplus.py tree <APP_ID> [--format text|json]   # 项目结构(text emoji 或 json 树)
mockplus.py download-assets --downloads '[...]' --local-path <DIR>
mockplus.py cookie {set|test|status|clear|path}  # cookie 管理(user-only)
mockplus.py inspect <URL>                        # 统计 + 异常(辅助,回归检测用)
```

## 输出 JSON schema 速览(get-data)

```json
{
  "metadata": { "appId", "pageId", "name", "device", "canvas", "backgroundColor",
                "artboardScale", "pluginVersion", "pageImage" },
  "globalVars": {
    "styles": { "fill_001": {...}, "text_001": {...}, "shadow_001": {...}, "stroke_001": {...} },
    "sharedStyles": { "<uuid>": { "displayName", "kind", "stylesRef": [...] } }
  },
  "nodes": [
    { "id", "name", "type", "realType", "bounds": {"top","left","width","height"},
      "fills", "strokes", "radius", "shadows", "sharedStyle", "text",
      "sourceComponent", "library", "symbol", "asset", "children" }
  ],
  "_meta": { "transformVersion", "sketchPluginVersion", "documentVersion",
             "inputFieldsTotal", "unhandledFields", "warnings" }
}
```

详见 `docs/specs/2026-05-22-skill-redesign-design.md` §5。

## 常见失败

| 现象 | 处理 |
|---|---|
| `cookie 未配置` (exit 10) | 跑 `mockplus.py cookie set` |
| `API code != 0` (exit 21) | cookie 过期 → `mockplus.py cookie set` 重配 |
| `URL 指向 group,先用 tree 浏览` (exit 22) | URL 指向 group/app,先用 `tree` 找具体 page id |
| `_meta.unhandledFields` 不为空 | Mockplus 升级了 schema,反馈 issue |
| 切图下载 `invalid host` / `unsupported format` | URL 不在 img(01\|02).mockplus.cn 或不是 .png |

## 隐私 & 安全

- cookie 只读取,不上传;`config/cookie` 自动 chmod 600
- API 响应 cache 在 `~/.cache/mockplus-context/`,user 自决是否清理
- 切图保存到 `--local-path` 指定目录,user 自管
