---
name: mockplus-context
description: |
  ALWAYS invoke for any request touching Mockplus or 摹客 design sources. This is the ONLY skill for fetching Mockplus page data (structure, 标注, 字号, 颜色, 尺寸, layout, 切图/icon export) and feeding it into UI/code work.

  Trigger immediately, without asking, on ANY of these signals:
  - The string "Mockplus" or "摹客" appears anywhere in the user's message
  - Any URL containing `mockplus.cn`, `app.mockplus.cn`, or `idoc` (full or partial, e.g. `app.mockplus.cn/app/.../develop/design/...`)
  - A Mockplus link plus phrases like 看看 / 按这个做 / 还原 / 复刻 / 转成 Vue / 转成 React / 转成 Flutter / 转成小程序 / 对比 / 取源数据 / 拿标注 / 切图 / icon

  The link or keyword ALONE is enough — never wait for the user to say "use the skill" or "use a tool". Pairing with a frontend framework (Vue/React/Flutter/小程序/Tailwind) makes it MORE relevant, not less.

  Skip ONLY for: Figma URLs, isolated PNG/PDF/screenshot files with no Mockplus link, local .sketch parsing, building a Mockplus-clone product, or Mockplus desktop-app UI bugs.
---

# Mockplus Context (v0.7.0)

把 Mockplus develop URL 转换为**结构化 YAML**,LLM 直接消费。v0.6 起输出经过
**包含树重建**:视觉上压在背景/卡片上的元素真正嵌套为其子节点,
`locationRelativeToParent` 是真·相对父坐标(v0.5 及更早是画布绝对坐标,
读旧缓存文件时看 `_meta.coordinateSpace` 区分)。

v0.7 起 YAML 默认再经**机械蒸馏**(`scripts/distill.py`,实测 −45~48%):
`layout_*` 查找表内联为节点行内 `pos: {x, y, w, h}`(非默认 mode/sizing 以
`mode:`/`hsz:`/`vsz:` 键保留),UUID 截前 8 位(确定性、跨拉取稳定;**前 8 位与
YAML 数字形歧义的 id 保留全 UUID**——如 `03450216`,截断会被解析器读成数字);
`imageRef` 资产哈希、fill/textStyle 表、文本内容一律不动。出口不变量自检,任何一条
不满足即整体回退未蒸馏原文(stderr WARN),绝不出半成品;产物打标 `_meta.distilled: true`。
要 v0.6 原形态加 `--raw`;旧文件离线蒸馏:`python3 scripts/distill.py <in> [<out>] [--check-only]`。

两个消费警示:① 蒸馏 v0.5 旧文件会在 `_meta.distillWarnings` 提示坐标空间非
parent-relative(pos 为原语义=画布绝对坐标,勿当相对父坐标);② TEXT 节点带
`textSegments: N`(N>1)= 原文有 N 段样式仅取首段,`textStyle` 未必代表整段
(字重/颜色判定先核 sharedStyle 名)。

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
mockplus data <URL> [--out PATH] [--format yaml|json] [--coords relative|absolute] [--raw] [--stats] [--refresh]
mockplus download <URL> [--nodes all|h1,h2] [--out DIR] [--include-design]
mockplus all <URL> [<OUT_DIR>] [--coords relative|absolute]   # = data + download(all + design)
mockplus tree <APP_ID> [--format text|json] [--refresh]
mockplus cookie {set|test|status|clear|path}
```

> Mockplus API 物理约束:只能按**整页(page)** 拉数据。Group/sub-group 没有节点级 API,所以 `data` 只接受 page URL,group 浏览靠 `tree`。

## 输出 YAML 速览(`data` 产物)

```yaml
metadata:
  name: Sample Page
  pageId: pgA1bC2X3
  device: ios1x
  size: { width: 375, height: 812 }
  backgroundColor: '#f5f5f5'
  components:                          # SymbolInstance 反推
    <libId>/<path>: { id, name, libraryName }

nodes:
  - id: 2F11A218                       # v0.7:UUID 已截前 8 位(--raw 为完整 UUID)
    name: Submit Bar                   # 吸底栏背景(重建后成为容器)
    type: VECTOR                       # FRAME/TEXT/INSTANCE/RECTANGLE/ELLIPSE/VECTOR/IMAGE/SLICE/MASK
    pos: {x: 0, y: 718, w: 375, h: 48} # v0.7:layout 表已内联为行内 pos(--raw 为 layout: layout_000003)
    absolutePosition: { x: 0, y: 718 } # 仅容器节点有:画布绝对锚点
    children:
      - id: 67C9DB5F
        name: Submit Action
        type: TEXT
        pos: {x: 266, y: 19, w: 80, h: 22}   # 真·相对父坐标(v0.6 语义不变)
        fills: fill_000001             # 可选
        text: "Submit Action"
        textStyle: Body/16px/Semibold/Center Style   # 设计师命名

globalVars:
  styles:                              # v0.7:仅剩 fill / textStyle(layout_* 已内联)
    fill_000003:                       # 切图填充
      - type: IMAGE
        imageRef: 2b417ea8...          # ← LLM 拿这个调 download(40 位哈希,蒸馏不动)
        scaleMode: FILL
    Body/16px/Semibold/Center Style:
      fontFamily: PingFang SC
      fontWeight: 600
      fontSize: 16

_meta:
  coordinateSpace: parent-relative     # absolute-artboard = v0.5 语义(旧文件/回退)
  relayout:                            # 包含树重建统计
    reparented: 21                     # 被重挂进视觉容器的节点数
    zFilter: 'on'                      # z 方向证据不足的页会自动置 off 并告警
  unhandledFields: []                  # Mockplus schema 升级时这里会列字段
```

**关键设计:**
- **包含树重建(v0.6)**:授权分组是硬边界,组内兄弟按几何包含嵌套(最小面积
  容器胜出);INSTANCE 内部结构冻结、不收养外来节点;任意叶子的画布绝对位置 =
  最近容器 `absolutePosition` + 自身 rel,一次加法
- 元素定位直接用 `locationRelativeToParent` 写 CSS(父容器 `position:relative`
  + 子 `absolute`),不需要再做减法
- Token 复用:相同 fill/layout/effect 自动去重,节点上只放引用(相对化后重复
  卡片的内部元素共享同一 layout token,重复模式直接可见)
- 文字样式 key 用设计师命名(`sharedStyle.name`),保留语义
- 切图节点 fills 数组里写 `IMAGE` fill,LLM 拿 `imageRef` 调 download
- 带 `adoptedBy: geometry` 的节点是几何跨界收养进授权分组的,语义存疑时可忽略该标记

## 常见失败

| 现象 | 处理 |
|---|---|
| `cookie 未配置` (exit 10) | `mockplus cookie set` |
| `API code != 0` (exit 21) | cookie 过期 → `mockplus cookie set` 重配 |
| `URL 指向 group,先用 tree 浏览` (exit 22) | URL 不是 page,先 `tree` 找正确 page id |
| `_meta.unhandledFields` 非空 | Mockplus schema 升级了,反馈 issue |
| `_meta.coordinateSpace` 是 `absolute-artboard` | 包含树重建被回退(看 `_meta.warnings`)或读到了 v0.5 旧文件/`--coords absolute` 产物 —— 此时 `locationRelativeToParent` 是画布绝对坐标 |
| 切图下载失败 | CDN 临时不通,重跑 `download`(已存在的会跳过) |
| 中国境外节点超时 | `img02.mockplus.cn` 是华东 CDN,境外节点请挂回国代理 |

## Cache 与隐私

- 中间产物:`~/.cache/mockplus/<APP_ID>/`(可被 `MOCKPLUS_CACHE_DIR` 覆盖)
- cookie 只读,不上传;`~/.config/mockplus/cookie` 自动 `chmod 600`
- 用户切图产物在用户指定目录,不污染 git 仓库

## 进阶参考

- `references/examples.md` — 端到端调用样例
- `references/troubleshooting.md` — 完整错误码 + 诊断
