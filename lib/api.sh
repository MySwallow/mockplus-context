# shellcheck shell=bash
# URL 解析 + 项目索引拉取 + 树形打印 + 节点类型查询

cmd_url() {
  local url="${1:?用法:mockplus url <URL>}"
  python3 - "$url" <<'PY'
import sys, re
url = sys.argv[1]
m = re.search(r'/app/([^/?#]+)', url)
if not m:
    print('ERR: URL 缺少 /app/<APP_ID>/ 段', file=sys.stderr); sys.exit(1)
app_id = m.group(1)
clean = re.sub(r'[?#].*$', '', url).rstrip('/')
target_id = clean.rsplit('/', 1)[-1]
if target_id == app_id:
    target_id = ''
print(f'APP_ID={app_id}')
print(f'TARGET_ID={target_id}')
PY
}

cmd_index() {
  local app_id="${1:?用法:mockplus index <APP_ID> [out_root]}"
  local out_root="${2:-$OUT_ROOT_DEFAULT}"
  local app_dir="$out_root/$app_id"
  mkdir -p "$app_dir"
  local idx="$app_dir/_index.json"

  info "GET /api/v1/app/module/$app_id/design"
  http_app "/api/v1/app/module/$app_id/design" > "$idx.tmp"

  if ! python3 - "$idx.tmp" <<'PY'
import sys, json
data = json.load(open(sys.argv[1]))
if data.get('code') != 0:
    print(f"ERR: API code={data.get('code')} message={data.get('message')}", file=sys.stderr)
    sys.exit(1)
PY
  then
    head -c 500 "$idx.tmp" >&2; echo >&2
    rm -f "$idx.tmp"
    die "API 响应非 success(常见原因:cookie 过期、app_id 无权限)。运行 mockplus cookie test $app_id" 21
  fi
  mv "$idx.tmp" "$idx"

  python3 - "$idx" "$app_dir/_pages.json" <<'PY'
import json, sys
idx = json.load(open(sys.argv[1]))
pages = []; groups = []
def walk(node, path, parent_id):
    p = path + [node.get('name','?')]
    nid = node.get('_id') or node.get('id') or ''
    if node.get('isGroup', False):
        groups.append({
            'id': nid, 'name': node.get('name',''),
            'path': ' / '.join(p),
            'parentId': parent_id,
            'pageCount': sum(1 for c in node.get('children',[]) if not c.get('isGroup', False) and c.get('dataURL')),
            'childGroupCount': sum(1 for c in node.get('children',[]) if c.get('isGroup', False)),
        })
    elif node.get('dataURL'):
        pages.append({
            'id': nid, 'name': node.get('name',''),
            'path': ' / '.join(p),
            'groupId': parent_id,
            'device': node.get('device',''),
            'size': node.get('size',{}),
            'backgroundColor': node.get('backgroundColor',''),
            'dataURL': node['dataURL'],
            'imageURL': node.get('imageURL',''),
            'slicesCount': node.get('slicesCount', 0),
            'updatedAt': node.get('updatedAt',''),
        })
    for c in node.get('children', []):
        walk(c, p, nid if node.get('isGroup', False) else parent_id)
for root in idx.get('payload', {}).get('pages', []):
    walk(root, [], '')
json.dump({'pages': pages, 'groups': groups}, open(sys.argv[2],'w'), ensure_ascii=False, indent=2)
print(f'OK: {len(pages)} 页 / {len(groups)} 分组 → {sys.argv[2]}', file=sys.stderr)
PY
  echo "$app_dir"
}

# 确保 _index.json 存在且 < 24h,返回 app_dir 路径
ensure_index() {
  local app_id="$1"
  local out_root="${2:-$OUT_ROOT_DEFAULT}"
  local app_dir="$out_root/$app_id"
  local idx="$app_dir/_index.json"
  if [ -f "$idx" ] && [ "$(find "$idx" -mmin -1440 2>/dev/null | wc -l | tr -d ' ')" -gt 0 ]; then
    debug "_index.json < 24h,使用缓存:$idx"
    echo "$app_dir"
    return 0
  fi
  cmd_index "$app_id" "$out_root" >/dev/null
  echo "$app_dir"
}

cmd_tree() {
  local app_id="${1:?用法:mockplus tree <APP_ID> [out_root]}"
  local out_root="${2:-$OUT_ROOT_DEFAULT}"
  local app_dir
  app_dir="$(ensure_index "$app_id" "$out_root")"
  python3 - "$app_dir/_index.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
def walk(node, depth=0):
    is_g = node.get('isGroup', False)
    icon = '📁' if is_g else '📄'
    nid = node.get('_id') or '?'
    name = node.get('name','?')
    suffix = ''
    if not is_g:
        sz = node.get('size', {})
        if sz: suffix = f"  ({sz.get('width','?')}x{sz.get('height','?')})"
    print(f"{'  '*depth}{icon} {name}  [{nid}]{suffix}")
    for c in node.get('children', []):
        walk(c, depth+1)
for root in data.get('payload',{}).get('pages', []):
    walk(root)
PY
}

# 在 _index.json 树里查 target_id,输出类型:page / group / notfound
tree_kind() {
  local app_dir="$1" target_id="$2"
  python3 - "$app_dir/_index.json" "$target_id" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
tid = sys.argv[2]
def walk(node):
    nid = node.get('_id') or ''
    if nid == tid:
        return 'group' if node.get('isGroup', False) else 'page'
    for c in node.get('children', []):
        r = walk(c)
        if r: return r
    return None
for root in data.get('payload',{}).get('pages', []):
    r = walk(root)
    if r:
        print(r); sys.exit(0)
print('notfound')
PY
}
