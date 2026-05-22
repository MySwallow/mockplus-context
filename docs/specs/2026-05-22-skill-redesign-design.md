# mockplus-context skill 重构设计 v3

- **日期**: 2026-05-22
- **状态**: 待实施
- **影响范围**: `~/Documents/dev/github/mockplus-context/` 整体重构 —— 现有 bash + lib 实现作为"功能参考"保留到 P1 字段侦察后删除,产物形态从"通用抓取 CLI"切换为"Claude/LLM-friendly skill"

---

## 1. 背景与动机

### 1.1 当前形态(github 仓库内)

- **bash + lib 模块化 CLI**: 12 个子命令,7 个 `lib/*.sh`,纯 `bash + python3 + curl`,无外部 pip 依赖
- 定位明确"纯抓取 CLI、不做 spec 转换、不做代码生成",输出落地为文件(`data.json` / `design.png` / `assets/*.{png,svg}`)
- 没有 `SKILL.md`,LLM 调用没有正式入口

### 1.2 目标

把项目从"通用 CLI"转型为"**LLM-friendly skill**":

1. **接口对齐 figma-context MCP 心智模型** —— LLM 调本项目与调 figma-context 步骤、参数、输出结构尽可能一致
2. **新增结构化 JSON 输出** —— LLM 不再读 raw sketch JSON,直接消化分层结构化数据(`metadata` / `globalVars` / `nodes`)
3. **新增 SKILL.md** —— LLM 入口(frontmatter + 触发场景 + 工作流)
4. **保留 github 版已验证的能力** —— cookie 全生命周期、group 批量、tree 浏览(原 bash 版的好东西,不丢)

物理形态仍是**纯 skill**(不引入 MCP server,不开新进程)。源码留在 github 项目下,可未来发布。开发期间不集成到 `~/.claude/skills/`。

### 1.3 与 figma-context 的对照(明确不对称的地方)

| 维度 | figma-context | mockplus-context(本设计) |
|---|---|---|
| 拿数据入口 | `get_figma_data(fileKey, nodeId?, depth?)` | `get-data <URL>`(只接 page URL,不支持 layer/group 子树 —— Mockplus API 物理约束) |
| 下图 | `download_figma_images(nodes[], localPath)` 用 nodeId | `download-assets --downloads '[{url,fileName}]' --local-path` 用 URL 直传 —— Mockplus CDN URL 永久稳定 |
| 项目浏览 | LLM 自己从 Figma 文件结构推 | `tree <APP_ID>` 树形打印项目结构,LLM 据此推导要 transform 哪些 page |
| 认证 | env 里设 API key | `cookie set/test/status/clear/path` 子命令族 + 兼容 env `MOCKPLUS_COOKIE` |
| 输出格式 | typed JSON(metadata/globalVars/nodes) | 同结构,字段细节贴近 Mockplus / Sketch 原生命名(`bounds.{top,left,width,height}` 而非 figma 的 `{x,y,w,h}`) |

---

## 2. Non-goals (本次不做)

- 不引入 MCP server 或 Node 进程
- 不做设计稿 diff、不做 visual-loop 串联、不做代码生成
- 不支持 `--node-id` 子树查询(Mockplus API 排查确认连 group 级也不行,只能整页)
- 不做客户端 `--depth` 嵌套裁剪(意义不大,YAGNI)
- **不做 `get-group` 多页摘要查询** —— group 浏览由 `tree` 提供文本视图;LLM 看到树后自行决定逐个调 `get-data`,不再单独暴露 group 摘要接口
- 不为旧 bash 子命令(`url` / `index` / `page` / `group` / `assets` / `fetch`)保留向后兼容
- 不在 `~/.claude/skills/` 做镜像安装(开发期间)—— 用户后续手动 symlink 或发布后由用户决定

---

## 3. 架构总览

### 3.1 包结构(实施完成时)

```
~/Documents/dev/github/mockplus-context/
├── README.md                          # 重写,反映新接口
├── SKILL.md                           # 【新增】LLM 入口(frontmatter + 触发场景 + 工作流)
├── LICENSE                            # 不动
├── CHANGELOG.md                       # 追加 v0.2.0 条目
├── .gitignore                         # 更新:移除"Python heredoc"注释,新增 __pycache__ 等
├── docs/
│   ├── specs/2026-05-22-skill-redesign-design.md   # 本文档
│   ├── api-reference.md               # 重写,描述 4 个新子命令(get-data / tree / download-assets / cookie *)
│   ├── architecture.md                # 重写
│   ├── cookie.md                      # 沿用大部分
│   ├── examples.md                    # 重写
│   └── troubleshooting.md             # 沿用 + 加新错误码
├── scripts/
│   ├── mockplus.py                    # 唯一 CLI 入口,argparse 多子命令
│   ├── _api.py                        # Mockplus 私有 API 客户端
│   ├── _transform.py                  # sketch JSON → 结构化输出 JSON
│   ├── _assets.py                     # CDN 下载(并发)
│   ├── _cookie.py                     # cookie 管理(set/test/status/clear/path)
│   ├── _tree.py                       # 树形结构打印(含 group 与 page 嵌套)
│   ├── _schema.py                     # 输出 JSON 校验(轻量 + 可选 jsonschema)
│   └── _explore.py                    # 字段侦察辅助脚本(P1 用)
├── tests/
│   ├── fixtures/                      # 真实 data.json 样本 + 期望输出
│   │   ├── simple-text.json
│   │   ├── nested-groups.json
│   │   ├── with-slices.json
│   │   ├── with-shared-styles.json
│   │   ├── with-gradients.json
│   │   └── expected/*.json
│   ├── test_transform.py
│   ├── test_api.py
│   ├── test_assets.py
│   ├── test_cookie.py
│   └── test_schema.py
├── config/                            # 沿用,cookie 默认存储位置
│   └── README.md
└── (删除) bin/mockplus, lib/*.sh, scripts/validate.sh, tests/smoke.sh
```

### 3.2 数据流(LLM 视角)

```
LLM 收到 Mockplus URL
       ↓
   是否知道 page id?
   ├── 不知道,或者 URL 指向 group → mockplus.py tree <APP_ID>     (浏览项目结构,找到目标 page id)
   └── URL 指向 page             → mockplus.py get-data <URL>     (拿单页结构化 JSON)
                          ↓
       扫描 nodes,找 asset.url + metadata.pageImage.url
                          ↓
       决定要下哪些图,语义化命名
                          ↓
       mockplus.py download-assets --downloads '[...]' --local-path <DIR>
                          ↓
       进入下游任务(还原 Vue/Flutter/小程序 等)
```

---

## 4. CLI 接口(4 个子命令)

### 4.1 `get-data <URL>` — 拉单页结构化 JSON [LLM 主用]

```bash
python3 scripts/mockplus.py get-data <URL> [--refresh]
```

- `<URL>`: Mockplus develop 页 URL(`https://app.mockplus.cn/app/<APP_ID>/develop/design/<PAGE_ID>`),也接受短形式 `<APP_ID>:<PAGE_ID>`
- `--refresh`: 强制重新拉取,跳过 cache
- stdout: 结构化 JSON(见 §5)
- stderr: 进度 / 警告 / 未识别字段日志

**约束**: 不支持 `--node-id` / `--depth`(Mockplus API 物理只能整页)。若 URL 指向 group → exit code 22,提示用户改用 `tree` 浏览项目结构后再选具体 page。

### 4.2 `tree <APP_ID>` — 项目结构概览 [LLM 浏览辅助]

```bash
python3 scripts/mockplus.py tree <APP_ID> [--format text|json] [--refresh]
```

- `--format text`(默认): 含 emoji 的层级文本
  ```
  📁 v1  [g-root]
    📁 采购模块  [g-sub1]
      📄 申请页  [p-001]  (375x812)
      📄 审批页  [p-002]  (375x812)
    📄 首页  [p-003]  (375x812)
  ```
- `--format json`: 结构化树,每节点 `{id, name, kind: "group"|"page", device?, size?, children?}`
- 自动调用 index API(`_index.json` 不存在或 >24h 时)
- **必须 DFS 全树**:group 可能同时含直接 page + 子 group(混合树);容忍 `parentID` 指向不存在 group 的孤儿 page

### 4.3 `download-assets` — 纯 CDN 下载工具 [LLM 主用]

```bash
python3 scripts/mockplus.py download-assets \
  --downloads '[
    {"url":"https://img02.mockplus.cn/idoc/sketch/<hash>/...png","fileName":"nav-back.png"},
    {"url":"https://img02.mockplus.cn/idoc/sketch/<hash>/...png","fileName":"home-preview.png"}
  ]' \
  --local-path <DIR>
```

- `--downloads`: JSON 数组,每项 `{url, fileName}`
- `--local-path`: 本地保存目录,不存在则创建
- stdout: `{"downloaded": [...], "failed": [...]}` 摘要

**校验规则**:
- `url` 必须匹配 `^https://img(0[12])\.mockplus\.cn/`,否则标记 failed,reason `invalid host`
- `url` 必须以 `.png` 结尾,否则标记 failed,reason `unsupported format`(SVG 后续可能加,首版先 PNG-only)
- `fileName` 必须以 `.png` 结尾,否则标记 failed,reason `filename must end with .png`
- 不附 cookie(CDN 公开),只附 `Referer: https://app.mockplus.cn/`
- 并发上限 8(`concurrent.futures.ThreadPoolExecutor`),失败的 URL 不重试
- 已存在(`exists && size > 0`)的 fileName skip,并入 `downloaded` 列表加 `cached: true`

**`download-assets` 不需要 URL/APP_ID 参数,也不查 cookie** —— 纯 CDN 下载工具,可独立运行,测试时不需要 mock Mockplus API。

### 4.4 `cookie set/test/status/clear/path` — Cookie 管理 [User 配置]

完整保留现有 github 版本的 5 个 cookie 子命令(set/test/status/clear/path)语义(详见现有 `docs/cookie.md` + `docs/api-reference.md` §`mockplus cookie *`),Python 重新实现:

```bash
python3 scripts/mockplus.py cookie set [--from-file PATH]   # stdin/文件 写入,chmod 600
python3 scripts/mockplus.py cookie test <APP_ID>             # 调 design API 验证
python3 scripts/mockplus.py cookie status                    # 路径/权限/设置时间/剩余天数
python3 scripts/mockplus.py cookie clear                     # 删除 cookie 文件
python3 scripts/mockplus.py cookie path                      # 打印 cookie 文件路径
```

LLM 不会调这些(它没法交互式粘贴),只在 user 首次配置时用。SKILL.md 工作流只在"前置条件"章节提一句"用户需自行 `mockplus.py cookie set`"。

---

## 5. 输出 JSON Schema(`get-data` 输出,**核心契约**)

### 5.1 顶层结构

```jsonc
{
  "metadata": { ... },
  "globalVars": { ... },
  "nodes": [ ... ],
  "_meta": { ... }
}
```

### 5.2 `metadata`

```jsonc
{
  "appId": "5gAIPn9LE",
  "pageId": "0-ITsFIbmL",
  "name": "新建采购申请单",                            // page 节点 name(design API)
  "pageName": "V1.7 ",                                 // sketch JSON 顶层 pageName,可能与 name 不同
  "path": "v1.7 / V1.7采购申请列表 / 新建/编辑 / 新建采购申请单-空开页",
  "device": "ios1x",                                   // 取自 design API page 节点,与 sketch JSON 顶层 device 一致
  "canvas": { "width": 375, "height": 812 },           // sketch JSON 顶层 size
  "backgroundColor": "#F5F5F5",                        // alpha=1 时纯 hex;否则 "#RRGGBB (alpha=0.85)"。input 是 8 位 hex(`#f5f5f5ff`)
  "updatedAt": "2026-03-24T...",
  "source": "sketch",                                  // 从 sketch JSON 顶层透传(目前固定 sketch,留扩展)
  "artboardScale": 2,                                  // 从 sketch JSON 顶层透传,@2x / @1x 标识
  "pluginVersion": "5.0.28",                           // sketch 导出插件版本,排查 schema 漂移用
  "pageImage": {
    "url": "https://img02.mockplus.cn/idoc/sketch/<hash>/wbyrvwvvlh.png",
    "intrinsicSize": { "width": 750, "height": 1624 } // 由 `canvas.width * artboardScale` 推导
  }
}
```

**`pageImage.url` 数据源**: 取自 sketch JSON 的 **`layers.URL`** 字段(根 layer 上),不是 design API 的 `imageURL` ——
虽然是同一张图,但单一数据源(`get-data` 拉完 sketch JSON 即可)更稳。

### 5.3 `globalVars`

```jsonc
{
  "styles": {
    "fill_001":   { "kind": "solid", "color": "#FFFFFF" },
    "fill_002":   {
      "kind": "linearGradient",
      "stops": [
        { "color": "#FF0000", "position": 0.0 },
        { "color": "#0000FF", "position": 1.0 }
      ],
      "from": { "x": 0, "y": 0 },
      "to":   { "x": 0, "y": 1 }
    },
    "fill_003":   { "kind": "radialGradient", "stops": [...] },
    "text_001":   {
      "fontSize": 16,
      "fontFamily": "PingFang SC",
      "fontWeight": 500,                                // 数字 weight(400/500/600/...)
      "fontWeightName": "Medium",                       // 来自 font.fontWeight 字符串("Regular"/"Medium"/"Semibold")
      "fontDisplayName": "苹方-简 中黑体",                // 来自 font.name(中文显示名,可缺)
      "color": "#333333",
      "lineHeight": 22,
      "letterSpacing": 0,                               // text.styles[].space.letterSpacing
      "paragraph": 0,                                   // text.styles[].space.paragraph
      "align": "left",
      "decoration": {                                   // 仅当至少一项 true 时输出
        "bold": false, "italic": false,
        "underline": false, "lineThrough": false
      }
    },
    "shadow_001": {
      "type": "outside",                                // outside | inside,取自 effect.shadows[].type
      "offsetX": 0, "offsetY": 2,                       // 来自 effect.shadows[].offsetX/offsetY
      "blur": 4, "spread": 0,
      "color": "#0000001A"
    },
    "stroke_001": {
      "width": 1,                                       // 来自 stroke.borders[].strokeWidth
      "color": "#E5E5E5",
      "position": "inside",                             // 来自 stroke.borders[].type(inside/outside/center)
      "dash": []                                        // 仅当非空数组时输出
    }
  },
  "sharedStyles": {
    "F8F45C8E-BD9B-4F37-B089-10EF87F485A6": {           // key 用 sharedStyle.id(UUID),避免中文/斜杠/空格
      "displayName": "blue/600",                        // sharedStyle.name 原文
      "kind": "LayerStyle",                             // sharedStyle.type
      "stylesRef": ["fill_005"]                         // 首次解析的具体 style refs;后续若不一致写 _meta.warnings
    },
    "0FCB5C2C-24D8-44FE-B423-078C51979A5C": {
      "displayName": "01文字色1/18px/semibold/居中对齐 Style",
      "kind": "TextStyle",
      "stylesRef": ["text_007"]
    }
  }
}
```

**ID 命名规则**:
- `fill_NNN` / `text_NNN` / `shadow_NNN` / `stroke_NNN`,3 位数字递增,按首次出现的 z-order 稳定排序
- 内部用 spec 指纹去重(避免同色多次产生不同 fill_NNN)

**sharedStyles 一对多处理**: 同一 sharedStyle 名/id 下不同 layer 实例可能解析出不一致的具体 fill/text(因为 Mockplus 允许 layer 局部覆盖),`stylesRef` **以首次解析为准**,后续不一致写到 `_meta.warnings` 而非强求一对一。

### 5.4 `nodes`(递归树)

```jsonc
[
  {
    "id": "5f8a...",                  // basic.sourceID(真实数据每个 layer 都有,fallback 极少触发)
                                      // 真实里 basic.id === basic.sourceID,取 sourceID 为权威
    "name": "提交按钮",                // basic.name
    "type": "rect",                   // basic.type(粗类:group/text/rect/path/symbol/image)
    "realType": "ShapePath",          // basic.realType(细类:Artboard/Text/ShapePath/path/MSShapeGroup/SymbolInstance)
    "bounds": { "top": 100, "left": 20, "width": 335, "height": 48 },
                                      // 直接沿用 Sketch / Mockplus 原生命名(与 CSS top/left 一致)
    "opacity": 1,                     // 取自 basic.opacity(注意路径:在 basic 下,不在 node 顶层)
                                      // 仅当 < 1 时输出
    "sourceComponent": "04表单/01表单/14底部提示",
                                      // 来自 basic.containerSourceName,可选
                                      // 这是 LLM 还原组件最关键的设计系统线索
    "library": {                      // 可选;基于 basic.libraryID / libraryName
      "id": "BCE70C89-FD15-4E28-9BE7-1081065A022F",
      "name": "美孚门店通"
    },
    "imageId": "",                    // basic.imageID,可选
    "symbol": {                       // 仅 realType=SymbolInstance 时输出
      "masterId": "E442B0B5-32A4-48BB-ACE2-FAAA59393AD4",  // basic.symbolMasterId
      "symbolId": "8A5E893D-9C2F-4233-8136-8976C243CB45"   // basic.symbolId
    },
    "fills":   ["fill_001"],          // ref → globalVars.styles(fill.colors[])
    "strokes": ["stroke_001"],        // ref → globalVars.styles(stroke.borders[])
    "radius":  [8, 8, 8, 8],          // [TL, TR, BR, BL],来自 stroke.radius
    "shadows": ["shadow_001"],        // ref → globalVars.styles(effect.shadows[])
    "sharedStyle": {                  // 仅 sharedStyle.id 非空时输出
      "id": "F8F45C8E-BD9B-4F37-B089-10EF87F485A6",
      "name": "blue/600",
      "kind": "LayerStyle"            // sharedStyle.type:LayerStyle | TextStyle
    },
    "text": { "value": "提交", "style": "text_001" },
                                      // value 来自 text.styles[0].value(多 style 仅取第一段,write warning)
    "asset": {                        // 仅当 slice.bitmapURL 非空 + layer 有可下载切图
      "url": "https://img02.mockplus.cn/idoc/sketch/<hash>/...png",
      "intrinsicSize": { "width": 64, "height": 64 }
    },
    "children": [...]                 // 递归
  }
]
```

**字段省略规则**: 任何字段为 `null` / `[]` / `{}` / `""` 时**不输出**;`children` 为空时也不输出。

**type / realType 双轨保留** —— `type` 是粗分类(LLM 写 CSS 用),`realType` 是 Sketch 原生细分类(LLM debug / symbol 识别用)。两者**都从 sketch JSON 透传,不翻译为 figma 命名**。

**SymbolInstance 与 SymbolMaster 不会撞 ID**:SymbolInstance 的 `sourceID` 与对应 SymbolMaster 的 `sourceID` 是不同 UUID。但**同一 master 在不同位置插入多次**时,实例 sourceID 是否唯一目前未确认 —— 实施时 `_transform.py` 加 dedupe check,撞 ID 时写 `_meta.warnings`。

### 5.5 `_meta`

```jsonc
{
  "transformVersion": "0.1.0",
  "sketchPluginVersion": "5.0.28",    // 来自 sketch JSON 顶层 pluginVersion,Mockplus 升级时立刻可见
  "documentVersion": "1.0",           // sketch JSON 顶层 documentVersion
  "inputFieldsTotal": 1234,
  "unhandledFields": [],              // 未消费的输入字段路径
  "warnings": []                      // 非致命异常(bounds 缺失 / sharedStyle 一对多 / SymbolInstance ID 撞等)
}
```

---

## 6. URL / ID 处理

- `get-data` / `tree` 接受:
  1. 完整 URL: `https://app.mockplus.cn/app/<APP_ID>/develop/design/<TARGET_ID>`
  2. 短形式: `<APP_ID>:<TARGET_ID>`(对 `tree` 只需 `<APP_ID>`)
- 内部用 `_api.py` 里的 url 解析函数统一解析为 `(APP_ID, TARGET_ID, TARGET_KIND)`
- `TARGET_KIND` 由 `_index.json` 树判断(`page` / `group` / `app` / `notfound`)
- `get-data` 前置校验 TARGET_KIND == page,否则 exit 22 并提示用户用 `tree` 浏览找到具体 page id 后重试(对应现有 `fetch` 的 smart 分发逻辑改成 fail-fast)

---

## 7. 缓存策略

- API 响应 cache: `~/.cache/mockplus-context/<APP_ID>/<PAGE_ID>/`
  - `_index.json`(项目树)24h 过期
  - `<PAGE_ID>.data.json`(sketch JSON)24h 过期
- `MOCKPLUS_OUT_ROOT` env(沿用 github 版变量名)覆盖默认 cache 根,以兼容现有用户习惯
- `--refresh` 跳过 cache 强制重新拉
- 切图本地缓存**不由 skill 管** —— LLM 通过 `--local-path` 指定位置,文件存在则 skip,目录组织由 LLM 自行决定
- Cache 目录权限 `0700`,文件 `0600`(与 cookie 一致)

> 与现有 github 版的差异: 默认从 `./mockplus-cache/` 改到 `~/.cache/mockplus-context/`。理由: skill 是全局工具,不污染调用方的项目目录。env override 保留,要回旧行为 `export MOCKPLUS_OUT_ROOT=./mockplus-cache`。

---

## 8. 正确性保障策略(4 层)

Mockplus 没公开 sketch schema,本质是逆向工程。无法承诺 100% 正确,但承诺**"出错时立刻被发现"**。

### 8.1 实现前: 字段侦察(P1,不可跳)

`scripts/_explore.py` 扫描真实 `data.json`:

```bash
python3 scripts/_explore.py ~/path/to/mockplus-cache/
```

输出:
- 所有层级出现过的字段名 + 出现频率
- 每个枚举字段的取值集合(如 `fill.colors[i].type`、`basic.realType`)
- 字段缺失模式
- 异常案例采样

**优势**: github 项目已有完整 bash CLI,可以**先用现有 `bin/mockplus group <APP_ID> <GROUP_ID>` 批量拉真实数据**作为侦察素材。这是 P1 跟 P7(删除 bash 旧码)之间不可调换顺序的原因。

至少 10 份样本,覆盖 3 种设备类型(ios1x / web / android)。

### 8.2 实现时: Fixture 黄金对照

`tests/fixtures/` 选 5 份覆盖度高的真实 data.json:

1. `simple-text.json` —— 文本密集(基线)
2. `nested-groups.json` —— 多层嵌套 group
3. `with-slices.json` —— 多切图
4. `with-shared-styles.json` —— sharedStyle 引用密集
5. `with-gradients.json` —— 渐变 / 阴影 / 特效

每份配 `expected/<name>.json` 黄金对照,`pytest` 跑 diff。

### 8.3 运行时防御(每次调用都生效)

**A. Schema 校验(双层)**

为了保持 skill 零运行时依赖(开箱即用):

- **轻量校验(必跑,标准库)**: `_schema.py` 提供 `validate_lite(output)`,只用标准库实现:
  - 顶层 4 个 key 必存在
  - `metadata` 必填字段类型检查
  - `nodes` 必为 list,每节点必有 `id` + `type` + `bounds`
  - `globalVars.styles` / `sharedStyles` 必为 dict
  - 失败 → abort,exit code 50,stderr 指出失败路径

- **完整校验(可选,需 `pip install jsonschema`)**: `validate_full(output)` 用完整 jsonschema 检测更严格错误
  - jsonschema 已安装则自动启用,否则跳过并 stderr 一行 hint

**B. 未识别字段不静默丢**

transform 遍历输入时记录"已消费"标记,遍历结束后未标记字段写入:
- `_meta.unhandledFields` 列表(LLM 可见)
- stderr `WARN unhandled: <path>` 日志

这是**最重要的一层**: Mockplus 哪天偷偷改 schema → 从"静默错误"变成"用户能看到的 warn"。

**C. 容错降级**

- 节点缺 `bounds` → 用 parent 兜底,写 warning
- 节点缺 `basic.sourceID` → 自生成稳定 hash(name + bounds + parent path 的 sha1 前 8)
- 颜色字段非法 → fallback `#000000`,写 warning
- 单节点 transform panic → 该节点输出 `{ "id": "...", "_error": "<msg>" }`,不中断整体

### 8.4 回归检测: `inspect` 命令(辅助子命令)

> 可作为 P4 的产出,不计入 4 个主子命令。LLM 一般不调,user/CI 用。

```bash
python3 scripts/mockplus.py inspect <URL> [--refresh]
# stdout: 统计 + 异常列表
# {
#   "nodes": 234, "styles": 18,
#   "typesSeen": {"text": 80, "rect": 60, "group": 40, "symbol": 5},
#   "sharedStyles": 12, "assets": 23,
#   "unhandledFields": [...], "warnings": [...]
# }
```

---

## 9. 实施阶段

按顺序,**不可跳步**:

| Phase | 目标 | 退出标准 |
|---|---|---|
| **P1: 侦察** | 用现有 bash CLI 拉 ≥10 份真实 data.json → 跑 `_explore.py` → 产出字段分布表 | 字段分布表已 review,覆盖 ≥3 种设备类型 |
| **P2: 骨架** | `scripts/mockplus.py` argparse 框架,`_cookie.py` / `_api.py`(纯 GET + cache 层) | `python3 mockplus.py cookie test <APP_ID>` 跑通; `get-data <URL>` 能拉到 data.json(不 transform) |
| **P3: Transform** | `_transform.py` 实现,符合 §5 schema | fixture 测试全绿 + `validate_lite` 通过 |
| **P4: Schema 守卫** | `_schema.py` + `_meta.unhandledFields` 探测 + 容错降级 + `inspect` 命令 | 真实页面跑 `inspect`,unhandledFields 为空或全部已知 |
| **P5: Tree** | `_tree.py` + `tree` 子命令(text + json 两种 format),DFS 全树,容错孤儿 page | 用真实 APP_ID 跑通,树形输出与现有 `mockplus tree` 一致;含混合树(group 同时含 page + 子 group)的样本验证通过 |
| **P6: Assets** | `_assets.py` 并发下载、host/扩展名校验 | `download-assets` 端到端跑通,host 拒绝路径有测试覆盖 |
| **P7: 文档 + 收尾** | SKILL.md(新增);README / api-reference / architecture / examples 重写;删除 `bin/mockplus`、`lib/*.sh`、`scripts/validate.sh`、`tests/smoke.sh`;`.gitignore` 去掉 Python heredoc 注释;CHANGELOG v0.2.0 | SKILL.md 触发 Mockplus URL 能走完整工作流;`ls bin/ lib/` 不存在;`find . -name '*.sh' -not -path './.git/*'` 无结果;CHANGELOG 落地 |

---

## 10. 测试策略

| 模块 | 测试手段 |
|---|---|
| `_transform.py` | fixture 黄金对照 + 字段映射断言 |
| `_api.py` | 标准库 `unittest.mock` patch `urllib.request.urlopen` |
| `_assets.py` | 本地 `http.server` 起临时 PNG,验证并发 / 跳过 / host 拒绝 |
| `_cookie.py` | 5 个 cookie 子命令全覆盖,env / 文件 / 缺失三种路径 |
| `_tree.py` | fixture(简化 `_index.json` 样本,含混合树 + 孤儿 page)+ 输出 diff |
| `_schema.py` | 用 `_transform.py` fixture 输出跑 `validate_lite`;装了 jsonschema 时额外跑 `validate_full` |
| end-to-end | 不做(需真实 cookie),留给用户手动 `inspect` |

### 10.1 依赖矩阵

| 依赖 | 性质 | 用途 |
|---|---|---|
| Python 3.8+ | **运行时必需** | skill 本体 |
| 标准库 | **运行时必需** | 不引入第三方运行时依赖 |
| `pytest` | **dev only** | 跑测试 |
| `jsonschema` | **optional**(运行时 + dev) | 装了启用 `validate_full`,没装走 `validate_lite` |

提供 `tests/requirements.txt`(仅 `pytest` + `jsonschema`)。README 标注"如需开发/测试 `python3 -m pip install -r tests/requirements.txt`"。

---

## 11. SKILL.md(新增)

`SKILL.md` 是 LLM 入口,~80 行,结构:

1. **frontmatter**: name=`mockplus-context`,description 包含触发场景关键词(Mockplus develop URL / 摹客 / app.mockplus.cn)
2. **何时使用 / 不使用**
3. **前置条件**: 用户 setup `cookie set` 一次性配 cookie(链 `docs/cookie.md`)
4. **LLM 工作流**(数据流图,§3.2 简化版:URL → tree(若需) → get-data → download-assets)
5. **命令参考**(4 个主子命令的极简签名)
6. **输出 JSON schema 速览**(§5 顶层结构 + 关键字段,详细见 spec)
7. **常见失败模式**(cookie 401 / TARGET_ID 误判 → 提示用 tree / 切图 host 拒绝)
8. **隐私 & 安全**

`README.md` 重写后**面向人类开发者**,描述项目定位、安装、CLI 用法;末尾链向 `SKILL.md`。

---

## 12. 兼容性 —— 一刀切

- 删除 `bin/mockplus`、`lib/*.sh`、`scripts/validate.sh`、`tests/smoke.sh`
- 子命令命名变化:
  - `page <APP_ID> <PAGE_ID>` → `get-data <URL>`(不再落文件,JSON 到 stdout)
  - `assets <PAGE_DIR>` → `download-assets --downloads ... --local-path ...`(LLM 自决文件名)
  - `group <APP_ID> <GROUP_ID>` → **不再保留**,group 批量需求改用 `tree` 浏览 + LLM 逐个调 `get-data`
  - `index` / `url` / `fetch` 不再暴露(内部 module)
  - `cookie` / `tree` 沿用语义
- Cache 默认路径变更: `./mockplus-cache/` → `~/.cache/mockplus-context/`(env `MOCKPLUS_OUT_ROOT` 覆盖)
- `config/cookie` 路径**沿用**(避免老用户 cookie 失效)
- CHANGELOG 标记 v0.2.0 为 **breaking change**

---

## 13. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Mockplus 升级 sketch 导出格式 | §8.3.B `_meta.unhandledFields` 浮现,触发用户报告 |
| 真实项目出现 fixture 没覆盖的奇怪 layer | §8.3.C 容错降级,单节点失败不影响整体;`_meta.warnings` 暴露 |
| 切图 CDN host 未来扩展 | host 白名单可扩展,集中 `_assets.py` 维护 |
| `_explore.py` 缺样本 | P1 用现有 bash CLI 跑 group 批量,数据来源不愁 |
| 现有 bash CLI 用户的迁移阵痛 | CHANGELOG v0.2.0 显式列 breaking changes;`config/cookie` 路径保留;`MOCKPLUS_OUT_ROOT` env 保留 |

---

## 14. Open Questions

无 —— 设计中所有歧义已通过 brainstorm 收敛。

---

## 15. 文件清单(实施完成时预期)

详见 §3.1。要点:

- **新增**: `SKILL.md`、`scripts/*.py`(8 个)、`tests/*.py`(4 个)+ `fixtures/`、`docs/specs/`
- **重写**: `README.md`、`CHANGELOG.md`(追加)、`.gitignore`、`docs/api-reference.md`、`docs/architecture.md`、`docs/examples.md`
- **沿用**: `LICENSE`、`docs/cookie.md`(微调)、`docs/troubleshooting.md`(加新错误码)、`config/`
- **删除**: `bin/mockplus`、`lib/*.sh`、`scripts/validate.sh`、`tests/smoke.sh`
