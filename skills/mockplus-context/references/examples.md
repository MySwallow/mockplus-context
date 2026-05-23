# Examples

端到端调用样例(v0.5)。

## 例 1:单页拿 YAML

```bash
mockplus data 'https://app.mockplus.cn/app/<APP>/develop/design/<PAGE>' --out page.yaml
cat page.yaml | head -30
```

输出片段:

```yaml
metadata:
  name: 采购申请单列表（老板）
  pageId: -hKyUPiOs
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

## 例 2:按 hash 下指定切图

LLM 在 page.yaml 里看到节点用 `fills: fill_000003`,而 `globalVars.styles.fill_000003` 是 `[{type: IMAGE, imageRef: 2b417ea8...}]`,则:

```bash
mockplus download '<URL>' --nodes 2b417ea8... --out ./assets
ls ./assets
# 2b417ea8....png
# 2b417ea8....svg(若 CDN 有)
# assets-manifest.json
```

## 例 3:一站式 + 视觉对照

```bash
mockplus all '<URL>' ./design-cache
ls ./design-cache
# data.yaml  design.png  assets/
```

## 例 4:URL 是 group 时先用 tree

```bash
mockplus tree <APP_ID>
# 📁 v1.7
#   📁 V1.7采购申请列表
#     📄 采购申请单列表(老板)  [-hKyUPiOs]  (375x812)
#     📄 ...

# JSON 格式给程序处理
mockplus tree <APP_ID> --format json | jq -r '.. | objects | select(.kind=="page") | "\(.id) \(.name)"'
```

## 例 5:回归检测 + 统计

```bash
mockplus data '<URL>' --stats --out /tmp/page.yaml
# stderr 含:
# ---- stats ----
# {
#   "nodes": 142,
#   "styles": 38,
#   "assetsImages": 7,
#   "typesSeen": {"FRAME": 23, "TEXT": 89, "INSTANCE": 12, ...},
#   "unhandledFields": [],
#   "warnings": []
# }
```
