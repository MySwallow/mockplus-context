# Examples

真实场景用法。复制即用。

## 场景 1:第一次跑(配 cookie + 拉单页)

```bash
# 1. 装
git clone https://github.com/<you>/mockplus-context.git
cd mockplus-context
export PATH="$PWD/bin:$PATH"   # 或者每次用 ./bin/mockplus

# 2. 配 cookie(浏览器登录后 F12 拷 cookie)
mockplus cookie set
# (粘贴一行)

# 3. 验
mockplus cookie test 5gAIPn9LE

# 4. 拉单页
mockplus fetch 'https://app.mockplus.cn/app/5gAIPn9LE/develop/design/0-ITsFIbmL'

# 5. 看产物
ls mockplus-cache/5gAIPn9LE/pages/0-ITsFIbmL/
# page-meta.json  data.json  design.png  assets/  assets-manifest.json
```

## 场景 2:批量拉一个分组

先看项目结构,找到 group 的 ID:

```bash
mockplus tree 5gAIPn9LE
# 📁 v1.7  [g-v17]
#   📁 V1.7采购申请列表  [g-purchase]
#     📁 新建/编辑  [g-create]
#       📄 新建采购申请单-空开页  [0-ITsFIbmL]  (375x812)
#       📄 新建采购申请单-填写中  [0-AAAAAA]  (375x812)
#       📄 新建采购申请单-审核中  [0-BBBBBB]  (375x812)
#     📁 查看  [g-view]
#       ...
```

批量拉 `g-create` 这个分组下所有页:

```bash
mockplus group 5gAIPn9LE g-create
# [mockplus] group "新建/编辑" → 3 页
# [mockplus]   - 新建采购申请单-空开页  [0-ITsFIbmL]
# [mockplus]   - 新建采购申请单-填写中  [0-AAAAAA]
# [mockplus]   - 新建采购申请单-审核中  [0-BBBBBB]
# [mockplus] 开始批量拉取 3 个页面...
# [mockplus] [1/3] page 0-ITsFIbmL
# [mockplus] [2/3] page 0-AAAAAA
# [mockplus] [3/3] page 0-BBBBBB
# [mockplus] ==== group g-create 完成 ====
# [mockplus] 成功 3 / 失败 0 / 总 3

ls mockplus-cache/5gAIPn9LE/groups/g-create/
# _meta.json  _page-ids.txt

ls mockplus-cache/5gAIPn9LE/pages/
# 0-ITsFIbmL/  0-AAAAAA/  0-BBBBBB/
```

## 场景 3:CI / 脚本里用(环境变量 + 静默)

```bash
#!/usr/bin/env bash
set -euo pipefail
export MOCKPLUS_COOKIE="$(cat /run/secrets/mockplus_cookie)"
export MOCKPLUS_OUT_ROOT=/tmp/design-cache

mockplus fetch 'https://app.mockplus.cn/app/5gAIPn9LE/develop/design/g-purchase' >/dev/null

# 把所有 data.json 打包给下游
tar -czf designs.tar.gz -C "$MOCKPLUS_OUT_ROOT" .
```

## 场景 4:只补切图(已拉过 data.json,但切图缺失)

```bash
PAGE_DIR=./mockplus-cache/5gAIPn9LE/pages/0-ITsFIbmL
mockplus assets "$PAGE_DIR"
# [mockplus] 切图清单:5 个 unique
# [mockplus] 切图:下载 2,跳过 3,失败 0
```

## 场景 5:重命名了项目,缓存过期

```bash
mockplus fetch 'https://app.mockplus.cn/app/5gAIPn9LE/develop/design/0-ITsFIbmL'
# ERR: TARGET_ID=0-ITsFIbmL 不在 _index.json 树里...

# 强制刷新
rm mockplus-cache/5gAIPn9LE/_index.json
mockplus fetch 'https://app.mockplus.cn/app/5gAIPn9LE/develop/design/0-ITsFIbmL'
```

## 场景 6:从 `data.json` 提取颜色调色板(下游用法示例)

`mockplus-context` 不做这个,但下游一个小脚本就能搞:

```python
#!/usr/bin/env python3
# extract-palette.py - 从 mockplus data.json 抽出所有 fill 颜色
import json, sys, collections

def rgba_to_hex(c):
    return '#{:02X}{:02X}{:02X}'.format(int(c['r']), int(c['g']), int(c['b']))

def walk(node, out):
    fill = node.get('fill', {})
    for c in fill.get('colors', []):
        if c.get('color'):
            out[rgba_to_hex(c['color'])] += 1
    for child in node.get('children', []): walk(child, out)

data = json.load(open(sys.argv[1]))
palette = collections.Counter()
walk(data.get('layers', {}), palette)
for color, count in palette.most_common():
    print(f"{color}  x{count}")
```

```bash
python3 extract-palette.py mockplus-cache/5gAIPn9LE/pages/0-ITsFIbmL/data.json
# #FFFFFF  x12
# #262626  x8
# #0C479D  x3
# ...
```

## 场景 7:多账号 / 多机器

每台机器一份 cookie,互不影响:

```bash
# 个人开发机
MOCKPLUS_COOKIE_FILE=$HOME/.config/mockplus/cookie.personal mockplus cookie set

# 共享 CI 机器(独立 cookie)
MOCKPLUS_COOKIE_FILE=/etc/mockplus/cookie.ci mockplus cookie set
sudo chown ci:ci /etc/mockplus/cookie.ci
sudo chmod 600 /etc/mockplus/cookie.ci
```

或用 alias 区分:

```bash
alias mp-personal='MOCKPLUS_COOKIE_FILE=$HOME/.config/mockplus/cookie.personal mockplus'
alias mp-work='MOCKPLUS_COOKIE_FILE=$HOME/.config/mockplus/cookie.work mockplus'
```
