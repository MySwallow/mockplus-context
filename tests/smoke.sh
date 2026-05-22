#!/usr/bin/env bash
# 离线 smoke test:不需要 cookie / 网络,只验证不涉及 API 的逻辑
# 涉及 API 的命令(index/page/group/fetch/cookie test)需要用户手工跑

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOCKPLUS="$ROOT/bin/mockplus"

# 1. 假 _index.json fixture,验证 tree / tree_kind / index 后处理
FIX_DIR="$(mktemp -d)"
trap 'rm -rf "$FIX_DIR"' EXIT
APP_ID=TESTAPP
mkdir -p "$FIX_DIR/$APP_ID"

# 构造一个最小 _index.json(一个 group 包两个 page)
cat > "$FIX_DIR/$APP_ID/_index.json" <<'EOF'
{
  "code": 0,
  "message": "ok",
  "payload": {
    "pages": [
      {
        "_id": "g-root",
        "name": "v1",
        "isGroup": true,
        "children": [
          {
            "_id": "g-sub1",
            "name": "采购模块",
            "isGroup": true,
            "parentId": "g-root",
            "children": [
              {
                "_id": "p-001",
                "name": "申请页",
                "size": {"width": 375, "height": 812},
                "backgroundColor": "#ffffff",
                "dataURL": "https://img02.mockplus.cn/idoc/2026-01-01/x/p-001.json",
                "imageURL": "https://img02.mockplus.cn/idoc/sketch/aaa/wbyrvwvvlh.png",
                "device": "ios1x",
                "slicesCount": 0,
                "parentId": "g-sub1"
              },
              {
                "_id": "p-002",
                "name": "审批页",
                "size": {"width": 375, "height": 812},
                "backgroundColor": "#f5f5f5",
                "dataURL": "https://img02.mockplus.cn/idoc/2026-01-01/x/p-002.json",
                "imageURL": "https://img02.mockplus.cn/idoc/sketch/bbb/wbyrvwvvlh.png",
                "device": "ios1x",
                "slicesCount": 0,
                "parentId": "g-sub1"
              }
            ]
          },
          {
            "_id": "p-003",
            "name": "首页",
            "size": {"width": 375, "height": 812},
            "backgroundColor": "#ffffff",
            "dataURL": "https://img02.mockplus.cn/idoc/2026-01-01/x/p-003.json",
            "imageURL": "",
            "device": "ios1x",
            "slicesCount": 0,
            "parentId": "g-root"
          }
        ]
      }
    ]
  }
}
EOF

# 用 source 加载 lib,直接测内部函数
# shellcheck disable=SC1091
source "$ROOT/lib/common.sh"
# shellcheck disable=SC1091
source "$ROOT/lib/http.sh"
# shellcheck disable=SC1091
source "$ROOT/lib/cookie.sh"
# shellcheck disable=SC1091
source "$ROOT/lib/api.sh"

# 2. ensure_index 应直接命中 fixture(不调网络)
OUT_ROOT_DEFAULT="$FIX_DIR"
APP_DIR="$(ensure_index "$APP_ID" "$FIX_DIR")"
[ -f "$APP_DIR/_index.json" ] || { echo "FAIL: _index.json 缺失"; exit 1; }

# 3. tree_kind 验证
K="$(tree_kind "$APP_DIR" g-root)"
[ "$K" = group ] || { echo "FAIL: g-root 应为 group,实为 $K"; exit 1; }
K="$(tree_kind "$APP_DIR" p-001)"
[ "$K" = page ] || { echo "FAIL: p-001 应为 page,实为 $K"; exit 1; }
K="$(tree_kind "$APP_DIR" xxx)"
[ "$K" = notfound ] || { echo "FAIL: xxx 应为 notfound,实为 $K"; exit 1; }
echo "  ✓ tree_kind: group/page/notfound 三种都对"

# 4. cmd_index 重新生成 _pages.json(不涉及网络:_index.json 已存在 < 24h,会跳过 index 拉取)
# 直接调 cmd_index 会拉网络,改用手动生成 _pages.json 来测扁平化逻辑
# 等价于 cmd_index 里的 python 块,验证 groups / pages 都正确
python3 - "$APP_DIR/_index.json" "$APP_DIR/_pages.json" <<'PY'
import json, sys
idx = json.load(open(sys.argv[1]))
pages = []; groups = []
def walk(node, path, parent_id):
    p = path + [node.get('name','?')]
    nid = node.get('_id') or ''
    if node.get('isGroup', False):
        groups.append({'id': nid, 'name': node.get('name',''), 'path': ' / '.join(p),
                       'parentId': parent_id,
                       'pageCount': sum(1 for c in node.get('children',[]) if not c.get('isGroup',False) and c.get('dataURL')),
                       'childGroupCount': sum(1 for c in node.get('children',[]) if c.get('isGroup',False))})
    elif node.get('dataURL'):
        pages.append({'id': nid, 'name': node.get('name',''), 'path': ' / '.join(p),
                      'groupId': parent_id, 'dataURL': node['dataURL'],
                      'imageURL': node.get('imageURL',''), 'device': node.get('device',''),
                      'size': node.get('size',{}), 'backgroundColor': node.get('backgroundColor',''),
                      'slicesCount': node.get('slicesCount',0), 'updatedAt': node.get('updatedAt','')})
    for c in node.get('children', []):
        walk(c, p, nid if node.get('isGroup',False) else parent_id)
for root in idx.get('payload',{}).get('pages',[]):
    walk(root, [], '')
json.dump({'pages': pages, 'groups': groups}, open(sys.argv[2],'w'), ensure_ascii=False, indent=2)
PY

# 验证扁平化结果
PG_COUNT="$(python3 -c "import json;print(len(json.load(open('$APP_DIR/_pages.json'))['pages']))")"
GP_COUNT="$(python3 -c "import json;print(len(json.load(open('$APP_DIR/_pages.json'))['groups']))")"
[ "$PG_COUNT" = 3 ] || { echo "FAIL: 应有 3 页,实为 $PG_COUNT"; exit 1; }
[ "$GP_COUNT" = 2 ] || { echo "FAIL: 应有 2 组,实为 $GP_COUNT"; exit 1; }
echo "  ✓ _pages.json 扁平化:3 页 / 2 组"

# 5. tree 命令输出测试
TREE_OUT="$($MOCKPLUS tree $APP_ID "$FIX_DIR" 2>/dev/null)"
echo "$TREE_OUT" | grep -q '📁 v1' || { echo "FAIL: tree 缺 root group"; exit 1; }
echo "$TREE_OUT" | grep -q '📄 申请页' || { echo "FAIL: tree 缺 p-001"; exit 1; }
echo "  ✓ tree 输出包含 group/page"

echo
echo "==== smoke OK ===="
