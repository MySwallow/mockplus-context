---
name: mockplus-context
description: 从 Mockplus(摹客 / mockplus.cn / app.mockplus.cn / idoc)设计稿抓取**结构化 YAML + 切图**,LLM 拿到分层 YAML(metadata + nodes + globalVars.styles)可直接生成 Vue / React / Flutter / 小程序代码,无需解析 sketch 原始 JSON,比让 LLM 看 PNG 截图精度高一个数量级。**只要用户的输入或意图涉及 Mockplus/摹客设计稿,就应该用这个 skill,即使他们没明确说"用 mockplus-context"或"用工具"** —— 触发场景包括:粘贴 `https://app.mockplus.cn/app/<APPID>/develop/design/<PAGEID>` 形式的 URL、提到"摹客/Mockplus 设计稿/原型/标注/切图/idoc"、说"按 Mockplus 还原 UI / 对照 Mockplus 改 / 把这个 Mockplus 页面转成 [前端框架]"、或单纯抛出一个 Mockplus 域名链接让你"看看"/"按这个做"/"参考这个"。
---

# Mockplus Context (v0.5.0)

把 Mockplus develop URL 转换为**结构化 YAML**,LLM 直接消费。

启动时声明:**"Using mockplus-context to extract <PAGE_ID> from Mockplus."**

## 何时触发

- 用户给的输入是 `https://app.mockplus.cn/app/<APPID>/develop/design/<TARGET_ID>` 形式的 URL
- 用户要"读 Mockplus 设计稿"、"按 Mockplus 还原 UI"、"导出 Mockplus 切图"
- 任何后续要基于 Mockplus 数据生成代码(Vue / React / Flutter / 小程序)的前置步骤

**不触发:**
- 输入是 Figma URL(用 `figma-context` MCP)
- 输入只是一张孤立 PNG(让用户先找到对应 Mockplus 页面 URL)

## 前置条件(用户一次性配置 cookie)

```bash
python3 skills/mockplus-context/scripts/mockplus.py cookie set
# 浏览器(已登录 mockplus.cn)F12 → Application → Cookies → app.mockplus.cn
# 把全部 cookie 拼成一行粘贴,回车结束
```

Cookie 默认存到 `~/.config/mockplus/cookie`,有效期约 30 天。401 时让用户 `cookie set` 重配。

## LLM 工作流(收到 URL 时按这个顺序)

1. **检查 cookie**:`mockplus cookie status`,未配置则引导用户 `cookie set`
2. **若 URL 不确定是 page**(指向 group / 只有 APP_ID):`mockplus tree <APP_ID>` 浏览,从树里挑出具体 page id
3. **拿 YAML 数据**:`mockplus data <URL> --out page.yaml`(默认 YAML)
4. **扫 YAML 找切图**:看 `globalVars.styles` 里 `type: IMAGE` 的 fill,收集 `imageRef: <hash>`
5. **按需下切图**:`mockplus download <URL> --nodes <hash1>,<hash2> --out ./assets`
6. **进入下游**(代码生成 / 对照还原等)

要视觉对照?加 `--include-design` 或直接 `mockplus all <URL>` 一站式拿齐。

## 命令速查

```bash
mockplus data <URL> [--out PATH] [--format yaml|json] [--stats] [--refresh]
mockplus download <URL> [--nodes all|h1,h2] [--out DIR] [--include-design]
mockplus all <URL> [<OUT_DIR>]              # = data + download(all + design)
mockplus tree <APP_ID> [--format text|json] [--refresh]
mockplus cookie {set|test|status|clear|path}
```

> Mockplus API 物理约束:只能按**整页(page)** 拉数据。Group/sub-group 没有节点级 API,所以 `data` 只接受 page URL,group 浏览靠 `tree`。

## 输出 YAML 速览(`data` 产物)

```yaml
metadata:
  name: 采购申请单列表（老板）
  pageId: -hKyUPiOs
  device: ios1x
  size: { width: 375, height: 812 }
  backgroundColor: '#f5f5f5'
  components:                          # SymbolInstance 反推
    <libId>/<path>: { id, name, libraryName }

nodes:
  - id: <UUID>
    name: 合并转采购
    type: TEXT                         # FRAME/TEXT/INSTANCE/RECTANGLE/ELLIPSE/VECTOR
    layout: layout_000007              # 引用 globalVars.styles
    fills: fill_000001                 # 可选
    text: "合并转采购"
    textStyle: 01文字色1/16px/semibold/居中对齐 Style   # 设计师命名
    children: [...]

globalVars:
  styles:
    fill_000003:                       # 切图填充
      - type: IMAGE
        imageRef: 2b417ea8...          # ← LLM 拿这个调 download
        scaleMode: FILL
    layout_000007:
      mode: none
      locationRelativeToParent: { x: 266, y: 737 }
      dimensions: { width: 80, height: 22 }
    01文字色1/16px/semibold/居中对齐 Style:
      fontFamily: PingFang SC
      fontWeight: 600
      fontSize: 16

_meta:
  unhandledFields: []                  # Mockplus schema 升级时这里会列字段
```

**关键设计:**
- Token 复用:相同 fill/layout/effect 自动去重,节点上只放引用
- 文字样式 key 用设计师命名(`sharedStyle.name`),保留语义
- 切图节点 fills 数组里写 `IMAGE` fill,LLM 拿 `imageRef` 调 download

## 常见失败

| 现象 | 处理 |
|---|---|
| `cookie 未配置` (exit 10) | `mockplus cookie set` |
| `API code != 0` (exit 21) | cookie 过期 → `mockplus cookie set` 重配 |
| `URL 指向 group,先用 tree 浏览` (exit 22) | URL 不是 page,先 `tree` 找正确 page id |
| `_meta.unhandledFields` 非空 | Mockplus schema 升级了,反馈 issue |
| 切图下载失败 | CDN 临时不通,重跑 `download`(已存在的会跳过) |
| 中国境外节点超时 | `img02.mockplus.cn` 是华东 CDN,境外节点请挂回国代理 |

## Cache 与隐私

- 中间产物:`~/.cache/mockplus/<APP_ID>/`(可被 `MOCKPLUS_CACHE_DIR` 覆盖)
- cookie 只读,不上传;`~/.config/mockplus/cookie` 自动 `chmod 600`
- 用户切图产物在用户指定目录,不污染 git 仓库

## 进阶参考

- `references/examples.md` — 端到端调用样例
- `references/troubleshooting.md` — 完整错误码 + 诊断
