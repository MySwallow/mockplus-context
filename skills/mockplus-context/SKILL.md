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

# Mockplus Context

把 Mockplus develop URL 转成 LLM 直接可读的结构化 YAML(节点树 + 相对父坐标 + 样式),
配套区块截图、切图下载、设计 token 汇总,用于按设计稿还原 UI。

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

## 取数工作流

按需求走到对应步骤即可:只要结构停在第 2 步,只要切图走 1 → 4。

### 1. 定位页面

- `mockplus cookie status` 确认已配置;未配置则引导用户 `cookie set`
- 只有 `.../develop/design/<PAGE_ID>` 这种 page URL 能直接取数。URL 指向分组或只有 APP_ID(exit 22)时,
  `mockplus tree <APP_ID>` 按名称找到 page id,之后用 `<APP_ID>:<PAGE_ID>` 代替 URL

### 2. 取结构

- `mockplus data <URL> --out page.yaml`,读产物(字段语义见「读懂 YAML」)
- stderr 出现 `WARN: 输出约 N token` = 整页超过单次读取预算,**不要硬读整份**:
  `mockplus outline <URL>` 看区块(每行:类型/名称/id/画布坐标/子孙数/首段文本)→
  `mockplus data <URL> --node <id1>,<id2> --out part.yaml` 只拉需要的区块;仍超预算就挑更小的子区块
- 只需要页面某一块时同样 outline → `--node`,不必拉整页

### 3. 取截图

- `mockplus shot <URL> --node <id>` 按区块裁出 @2x 截图(省略 `--node` = 整页)
- 尺寸、间距、颜色、字号以 YAML 为准;截图用来理解层次、叠放和 YAML 表达不了的外观
  (如 `missingSlice: vector` 到底是不是图标)

### 4. 取资产

- 切图:`globalVars.styles` 里 `type: IMAGE` 的 fill 带 `imageRef`,只下要用的:
  `mockplus download <URL> --nodes <hash1>,<hash2> --out <项目资产目录>`
- stderr `NOTE: N 个疑似图标没有切图` → 带 `missingSlice` 的节点没有资产文件,按「实现守则」处理;
  列清单用 `mockplus outline <URL> | grep missingSlice`

### 5. 取 token 汇总(多页 / 整个模块时)

- `mockplus tokens <分组 URL 或 APP_ID>`:实际用到的颜色/文字样式/圆角/阴影/渐变及使用次数,
  供下游映射到项目已有 token

数据交给下游(代码生成、对照还原等)时,遵循下方「实现守则」。

## 实现守则(把数据翻成代码时)

- **design.png 是视觉目标,不是素材**:只拿来对照,绝不放进代码当背景图/占位
- **切图原样原位用**:每个 IMAGE fill 按 `imageRef` 下载后用在设计里对应的位置;不改图,
  SVG 保留根节点 width/height。接口/数据驱动的图片保持动态
- **没切图的图标(`missingSlice`)别自绘**:① 先在项目里找同名/同形的现成图标(图标组件、
  iconfont、assets 目录),`componentId` 里的组件库路径是线索;② 找不到就列清单(id、名称、
  `mockplus shot --node <id>` 裁出的参考图)请用户向设计师要切图;③ 必须先出效果时可用该
  参考图临时顶替并在代码里标 TODO(它是带背景的位图,不是正式资产),汇报时列出。
  不要自己画 SVG、不要拿第三方图标库凑
- **布局翻成项目原生写法**:`pos` 是相对父容器的设计快照,用来读间距、对齐、尺寸;落地优先
  flex/grid(或 Flutter Row/Column 等),只有确实叠放/浮层的元素才用绝对定位。
  `metadata.size.width` 是设计稿宽度,别写死成页面容器宽
- **先复用再新建**:动手前查项目已有组件、设计 token、样式变量;INSTANCE 的 `componentId`
  指向设计组件库,项目里有对应组件就用它;textStyle 是设计师命名,可映射到项目字体 token

## 读懂 YAML

```yaml
metadata:
  name: Sample Page
  pageId: pgA1bC2X3
  device: ios1x
  size: { width: 375, height: 812 }    # 设计稿画布尺寸
  backgroundColor: '#f5f5f5'
  components:                          # 页面用到的设计组件
    <libId>/<path>: { id, name, libraryName }

nodes:
  - id: 2F11A218                       # UUID 前 8 位,可直接给 --node
    name: Submit Bar                   # 设计师命名;没有 name = 没有语义名
    type: VECTOR                       # FRAME/TEXT/INSTANCE/RECTANGLE/ELLIPSE/VECTOR/IMAGE/SLICE/MASK
    pos: {x: 0, y: 718, w: 375, h: 48} # 相对父节点;非默认布局时 pos 内另有 mode/hsz/vsz
    abs: {x: 0, y: 718}                # 仅容器节点:画布绝对锚点
    fills: '#FFFFFF'                   # 纯色直写;fill_NNNNNN = 渐变/切图,查 globalVars
    children:
      - id: 67C9DB5F
        type: TEXT
        pos: {x: 266, y: 19, w: 80, h: 22}
        textStyle: Body/16px/Semibold/Center Style   # 设计师命名的文字样式
        text: "Submit Action"
      - id: 5C0FFEE1
        name: icon/arrow-right
        type: INSTANCE
        pos: {x: 351, y: 18, w: 12, h: 12}
        componentId: <libId>/icon/arrow-right
        missingSlice: icon             # 像图标但没有切图

globalVars:
  styles:                              # 渐变/切图 fill、stroke、effect、textStyle
    fill_000003:
      - type: IMAGE
        imageRef: 2b417ea8...          # 切图哈希 → download --nodes
        scaleMode: FILL
    Body/16px/Semibold/Center Style:
      fontFamily: PingFang SC
      fontWeight: 600
      fontSize: 16

_meta:
  coordinateSpace: parent-relative
  distilled: true
  unhandledFields: []                  # 非空 = Mockplus schema 有新字段未消费
  scope:                               # 仅 --node 产物:所选子树 id
    nodes: [2F11A218]
```

- **树结构**:视觉上压在背景/卡片上的元素已嵌套为它的子节点(设计师的分组是硬边界,组内按几何
  包含、最小容器胜出;INSTANCE 内部结构保持原样)。带 `adoptedBy: geometry` 的节点是跨分组按几何
  收养进来的,语义存疑时可忽略该归属
- **坐标**:`pos` 相对父节点,读间距/对齐不用再做减法;任意节点的画布绝对位置 = 最近容器 `abs` +
  自身 `pos`(outline、shot 用的都是画布绝对坐标)。`--node` 产物的子树根 `pos` 仍相对原父节点
- **id**:UUID 前 8 位;会被 YAML 读成数字的前缀(如 `03450216`)保留完整 UUID
- **name**:Sketch 自动命名(`编组 2`、`矩形备份 3`、`Rectangle Copy` 等)和等于文本内容的 TEXT 图层名
  已删除,不要去猜
- **textSegments: N**(N>1):该文本原有 N 段样式、只取了首段,`textStyle` 未必代表整段,
  字重/颜色先核对样式名和截图
- **missingSlice**:`icon` = 名称命中,基本确定是图标;`vector` = 小尺寸矢量形状,需对照截图判断
- **坐标空间警示**:`_meta.coordinateSpace` 不是 `parent-relative`(包含树重建被回退,原因见
  `_meta.warnings`;或 `--coords absolute` 产物),或出现 `_meta.distillWarnings` 时,`pos` 是
  画布绝对坐标,不要当相对父坐标用
- **未蒸馏形态**:`--raw` 或蒸馏自检失败回退时(stderr WARN,无 `_meta.distilled`),节点是完整
  UUID + `layout: layout_NNNNNN` 引用,位置尺寸在 `globalVars.styles.layout_*` 的
  `locationRelativeToParent` / `dimensions` 里,语义不变;已蒸馏产物里个别含特殊字段的节点也会保留
  `layout:` 引用,同样查表

## 命令速查

```bash
mockplus data <URL> [--node ID[,ID...]] [--out PATH] [--format yaml|json] [--coords relative|absolute] [--raw] [--stats] [--refresh]
mockplus outline <URL> [--depth N] [--refresh]                # 区块大纲(大页先看它)
mockplus shot <URL> [--node ID[,ID...]] [--pad N] [--out DIR] # 按区块裁 @2x 截图(省略 --node = 整页)
mockplus tokens <页/分组 URL 或 APP_ID> [--format yaml|json] [--out PATH]  # token 汇总
mockplus download <URL> [--nodes all|h1,h2] [--out DIR] [--include-design]
mockplus all <URL> [<OUT_DIR>] [--coords relative|absolute]   # = data + download(all + design)
mockplus tree <APP_ID> [--format text|json] [--refresh]
mockplus cookie {set|test|status|clear|path}
```

> Mockplus API 只能按**整页(page)** 拉数据,分组没有节点级 API,所以 `data` 只接受 page URL,分组浏览靠 `tree`。
> `outline` / `--node` / `shot` 都在本地整页结果上裁剪,不额外请求 API(shot 首次会下整页截图并缓存)。`--node` 的 id 取自 outline 或 YAML(≥8 位前缀即可),只在当前页有效。
> `tokens` 给分组或 APP_ID 时逐页拉数据(有 24h 缓存),单页失败记入 `_meta.pagesFailed` 不中断;文字样式按字号/字重/行高/颜色合并(忽略对齐),`names` 是设计师命名别名——同一名字出现在不同颜色条目里 = 实例覆盖过颜色。

## 常见失败

| 现象 | 处理 |
|---|---|
| `cookie 未配置` (exit 10) | `mockplus cookie set` |
| `API code != 0` (exit 21) | cookie 过期 → `mockplus cookie set` 重配 |
| `URL 指向 group,先用 tree 浏览` (exit 22) | URL 不是 page,先 `tree` 找正确 page id |
| `--node ... 不存在 / 太短 / 匹配到 N 个` (exit 23) | 先 `mockplus outline <URL>` 取 id;给 ≥8 位,歧义时给完整 UUID |
| stderr `WARN: 输出约 N token(>20000)` | 整页太大,走 `outline` → `data --node` 按区块拉(工作流第 2 步) |
| stderr `NOTE: N 个疑似图标没有切图` | 不是错误;节点带 `missingSlice`,按「实现守则」找项目图标或列清单向设计师要切图 |
| `shot` 报错 (exit 24) | 页面无整页截图 / 截图下载失败(加 `--refresh` 重试)/ 无裁剪工具(`pip install Pillow`,macOS 自带 sips 可兜底) |
| `_meta.unhandledFields` 非空 | Mockplus schema 升级了,反馈 issue |
| `_meta.coordinateSpace` 是 `absolute-artboard` | `pos` 是画布绝对坐标;非 `--coords absolute` 时看 `_meta.warnings` 里的回退原因 |
| 切图下载失败 | CDN 临时不通,重跑 `download`(已存在的会跳过) |
| 中国境外节点超时 | `img02.mockplus.cn` 是华东 CDN,境外节点请挂回国代理 |

## Cache 与隐私

- 中间产物:`~/.cache/mockplus/<APP_ID>/`(可被 `MOCKPLUS_CACHE_DIR` 覆盖)
- cookie 只读,不上传;`~/.config/mockplus/cookie` 自动 `chmod 600`
- 用户切图产物在用户指定目录,不污染 git 仓库

## 进阶参考

- `references/examples.md` — 端到端调用样例
- `references/troubleshooting.md` — 完整错误码 + 诊断
