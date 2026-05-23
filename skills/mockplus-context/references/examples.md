# Examples

端到端调用样例(v0.5),按"用户意图 → 调用 → 产物"组织。

---

## 例 1:单页拿 YAML

**Input(用户意图):**
> "把这个 Mockplus 页面的结构给我:`https://app.mockplus.cn/app/<APP_ID>/develop/design/<PAGE_ID>`"

**Command:**
```bash
mockplus data 'https://app.mockplus.cn/app/<APP_ID>/develop/design/<PAGE_ID>' --out page.yaml
```

**Output(`page.yaml` 前 20 行):**
```yaml
metadata:
  name: Home Page
  pageId: <PAGE_ID>
  appId: <APP_ID>
  device: ios1x
  size: { width: 375, height: 812 }
nodes:
  - id: <UUID>
    name: 顶栏
    type: FRAME
    layout: layout_000001
    children: [...]
globalVars:
  styles:
    fill_000001:
      - '#FFFFFF'
    layout_000001:
      mode: none
      dimensions: { width: 375, height: 64 }
```

---

## 例 2:按 hash 下指定切图

**Input(用户意图):**
> "把那两个图标切图下下来,我要做 PWA assets"
>
> *(LLM 已在上一步的 page.yaml 里看到 `fills: fill_000003` → `globalVars.styles.fill_000003` 是 `[{type: IMAGE, imageRef: 2b417ea8...}]`)*

**Command:**
```bash
mockplus download '<URL>' --nodes 2b417ea8,7c1d4f6a --out ./assets
```

**Output(`./assets/` 目录):**
```
2b417ea8....png    # bitmap
2b417ea8....svg    # vector(若 CDN 有)
7c1d4f6a....png
7c1d4f6a....svg
assets-manifest.json    # 本次下载的目标清单
```

---

## 例 3:一站式 + 视觉对照

**Input(用户意图):**
> "我要把这页还原成 Vue 组件,所有素材一次准备齐"

**Command:**
```bash
mockplus all 'https://app.mockplus.cn/app/<APP>/develop/design/<PAGE>' ./design-cache
```

**Output(`./design-cache/` 目录):**
```
data.yaml          # 结构化页面数据
design.png         # 整页 @2x 截图(视觉对照用)
assets/            # 所有切图(<hash>.png + <hash>.svg)
└── ...
```

LLM 接下来可以同时拿 YAML(写代码)+ design.png(视觉对比)+ 切图(<img src>)。

---

## 例 4:URL 是 group 时先用 tree 找 page

**Input(用户意图):**
> "这个 Mockplus 项目里有个'Sample Module'相关的页面,帮我找出来"
> *(用户只给出 `https://app.mockplus.cn/app/<APP>` 或一个 group URL)*

**Command:**
```bash
mockplus tree <APP_ID>
```

**Output(stdout):**
```
📁 Module
  📁 Module Subgroup
    📄 Sample Page  [pgA1bC2X3]  (375x812)
    📄 Sample Page (Variant)  [pgD3eF4Y5]  (375x812)
    📄 ...
```

**JSON 格式给程序处理:**
```bash
mockplus tree <APP_ID> --format json | jq -r '.. | objects | select(.kind=="page") | "\(.id) \(.name)"'
```

输出:
```
pgA1bC2X3 Sample Page
pgD3eF4Y5 Sample Page (Variant)
...
```

LLM 拿到 page id 后再 `mockplus data <APP>:pgA1bC2X3`。

---

## 例 5:回归检测 + 统计

**Input(用户意图):**
> "看看这个页面的结构复杂度,顺便确认 transform 没漏字段"

**Command:**
```bash
mockplus data '<URL>' --stats --out /tmp/page.yaml
```

**Output(stderr 含):**
```
---- stats ----
{
  "nodes": 142,
  "styles": 38,
  "assetsImages": 7,
  "typesSeen": {"FRAME": 23, "TEXT": 89, "INSTANCE": 12, "VECTOR": 18},
  "unhandledFields": [],     ← 空表示 transform 完整消费所有字段
  "warnings": []
}
```

`unhandledFields` 非空 → Mockplus schema 升级了,需要更新 `transform.py` 的 `LAYER_HANDLED` / `BASIC_HANDLED` 集合。

---

## 组合:典型还原 UI 工作流

**Input(用户意图):**
> "把这个 Mockplus 页面 `https://app.mockplus.cn/app/<APP>/develop/design/<PAGE>` 还原成 Vue 3 + TailwindCSS 的组件"

**LLM 应该跑的步骤序列:**

```bash
# Step 1: 拿 YAML 数据
mockplus data '<URL>' --out page.yaml

# Step 2: 读 page.yaml,扫所有 fills 引用 IMAGE 的 globalVars.styles entries,
#         收集 imageRef hash 列表

# Step 3: 按 hash 下切图(只下需要的,不下所有)
mockplus download '<URL>' --nodes <hash1>,<hash2>,<hash3> --out ./public/assets

# Step 4: 视觉对照(可选,debug 时用)
mockplus download '<URL>' --include-design --out ./tmp

# Step 5: 基于 page.yaml 写 Vue 组件:
#         - metadata.size → container width/height
#         - globalVars.styles.layout_NNNNNN → 绝对定位 / 尺寸
#         - globalVars.styles.fill_NNNNNN(hex 或 IMAGE) → bg-color / bg-image
#         - globalVars.styles.<sharedStyle.name>(textStyle) → 字号字重颜色
#         - nodes 树 → Vue template 嵌套
```
