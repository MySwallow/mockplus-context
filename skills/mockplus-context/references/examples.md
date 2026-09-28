# Examples

端到端调用样例,按"用户意图 → 调用 → 产物"组织。

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
  - id: AB12CD01
    name: 顶栏
    type: FRAME
    pos: {x: 0, y: 0, w: 375, h: 64}
    abs: {x: 0, y: 0}
    fills: '#FFFFFF'
    children: [...]
globalVars:
  styles:
    Title/17px/Semibold/Center Style:
      fontFamily: PingFang SC
      fontSize: 17
      fontWeight: 600
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

## 例 6:大页两级取数(outline → --node)

**Input(用户意图):**
> "只把这个页面的'预警排行'卡片还原出来"
> *(或:`mockplus data` 的 stderr 出现 `WARN: 输出约 40000 token(>20000)`)*

**Step 1 — 看区块大纲:**
```bash
mockplus outline '<URL>' --depth 2
```

**Output(stdout):**
```
# 页面: Sample Page (<PAGE_ID>)  画布 375x1400  节点 240  整页 YAML 约 16000 token
# 坐标 = 画布绝对坐标(对照 design.png);同级按位置从上到下排;n = 子孙节点数;text = 子树最靠上的文本
# 下钻: mockplus data <APP_ID>:<PAGE_ID> --node <id>[,<id>...]
[INSTANCE] "Nav/White" #AB12CD01 @0,0 375x64 n=26 text="Sample Title"
  [FRAME] #AB12CD02 @0,0 375x64 n=25 text="Sample Title"
[FRAME] #AB12CD03 @12,100 351x442 n=54 text="Summary"
[FRAME] #AB12CD04 @0,554 375x867 n=160 text="Trend"
  [FRAME] #AB12CD05 @0,818 375x603 n=124 text="Warning Rank"
    [VECTOR] #AB12CD06 @12,818 351x555 n=120 text="Warning Rank"
```

没有 `"名称"` 的行 = 图层是自动命名(编组/矩形…),靠 `text` 和坐标对照 design.png 辨认区块。

**Step 2 — 只拉目标区块(可一次多个):**
```bash
mockplus data '<URL>' --node AB12CD06 --out rank-card.yaml
```

产物结构与整页相同,但只含该子树 + 它实际引用的样式/组件;子树根带 `abs`(画布绝对锚点),
`_meta.scope.nodes` 记录所选 id。

---

## 例 7:缺切图图标 + 区块截图

**Input(用户意图):**
> "把这个卡片还原成组件"
> *(`mockplus data` stderr 出现 `NOTE: 3 个疑似图标没有切图(icon 2 / vector 1,节点标 missingSlice)`)*

**Step 1 — 找出缺切图的节点并裁参考图:**
```bash
mockplus outline '<URL>' | grep missingSlice
#   [INSTANCE] "icon/arrow-right" #AB12CD08 @339,840 12x12 n=1 missingSlice=icon
#   [VECTOR] #AB12CD09 @24,1170 16x16 missingSlice=vector
mockplus shot '<URL>' --node AB12CD08,AB12CD09 --pad 4 --out ./shots
# ./shots/AB12CD08.png  #AB12CD08 @339,840 12x12 → 40x40px @2x
```

**Step 2 — 按「实现守则」处理:** 项目里有 `ArrowRight` 图标组件 → 直接用;第二个找不到 →
写进汇报清单(id + 参考图)请用户找设计师补切图,代码里用参考图临时顶替并标 TODO。

---

## 例 8:整个模块的设计 token 汇总

**Input(用户意图):**
> "这个模块要开发十几个页面,先把颜色和字体规范理一下"

**Command:**
```bash
mockplus tokens '<分组 URL>' --out tokens.yaml    # 或 mockplus tokens <APP_ID> 汇总整个项目
```

**Output(`tokens.yaml` 片段):**
```yaml
scope: {kind: group, id: <GROUP_ID>, name: <Module>, pages: 28}
colors:
- value: '#262626'
  uses: 477
  roles: {text: 396, fill: 81}
typography:
- fontFamily: PingFang SC
  fontSize: 14
  fontWeight: 600
  lineHeight: 20
  color: '#262626'
  uses: 97
  names: [TextColor1/14px/Semibold/Left Style, TextColor1/14px/Semibold/Center Style]
radii:
- {value: 8px, uses: 212}
```

LLM 拿它和项目已有的 CSS 变量 / Tailwind config / 主题文件逐项对齐,缺的补成项目 token,再开始写页面。

---

## 组合:典型还原 UI 工作流

**Input(用户意图):**
> "把这个 Mockplus 页面 `https://app.mockplus.cn/app/<APP>/develop/design/<PAGE>` 还原成 Vue 3 + TailwindCSS 的组件"

**LLM 应该跑的步骤序列**(对应 SKILL.md「还原工作流」清单):

```bash
# 1. 定位:URL 是 page,cookie 已配置
mockplus cookie status

# 2. 取结构(stderr 出现 WARN 超预算 → outline → data --node 按区块拉)
mockplus data '<URL>' --out page.yaml

# 3. 取视觉基准(验收标准)
mockplus shot '<URL>' --out ./shots

# 4. 取资产:扫 globalVars.styles 里 type: IMAGE 的 imageRef,只下要用的
mockplus download '<URL>' --nodes <hash1>,<hash2> --out ./src/assets
mockplus outline '<URL>' | grep missingSlice     # 缺切图的图标,按实现守则处理

# 5. 对齐项目:查已有组件 / CSS 变量 / Tailwind config,textStyle、颜色映射到项目 token

# 6. 写 Vue 组件:
#    - nodes 树 → template 嵌套;pos 读间距/对齐,落地用 flex/grid,只有叠放才绝对定位
#    - fills '#hex' → 背景色;fill_NNNNNN(IMAGE)→ 下载好的切图
#    - textStyle → 项目字体 token(字号/字重/行高/颜色)

# 7. 自验:渲染截图与 ./shots 逐项比(布局/文字/外观/资产),有差异修完再比
```
