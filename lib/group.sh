# shellcheck shell=bash
# 分组批量拉取:一次性拉一个 group 下所有(递归)页面

# cmd_group <APP_ID> <GROUP_ID> [out_root]
cmd_group() {
  local app_id="${1:?用法:mockplus group <APP_ID> <GROUP_ID> [out_root]}"
  local group_id="${2:?需要 GROUP_ID}"
  local out_root="${3:-$OUT_ROOT_DEFAULT}"

  ensure_index "$app_id" "$out_root" >/dev/null
  local app_dir="$out_root/$app_id"
  local group_dir="$app_dir/groups/$group_id"
  mkdir -p "$group_dir"

  local ids_file="$group_dir/_page-ids.txt"

  python3 - "$app_dir/_index.json" "$group_id" "$ids_file" "$group_dir/_meta.json" <<'PY' \
    || die "group id=$group_id 未找到(_index.json 是否过期? rm $app_dir/_index.json 后重试)" 41
import json, sys
data = json.load(open(sys.argv[1]))
gid = sys.argv[2]
ids_path = sys.argv[3]
meta_path = sys.argv[4]
def find(node, parent_path):
    nid = node.get('_id') or ''
    cur = parent_path + [node.get('name', '?')]
    if nid == gid and node.get('isGroup', False):
        return node, cur
    for c in node.get('children', []):
        r = find(c, cur)
        if r: return r
    return None
group_hit = None
group_path = []
for root in data.get('payload', {}).get('pages', []):
    r = find(root, [])
    if r:
        group_hit, group_path = r
        break
if not group_hit:
    print(f'ERR: group id={gid} not found in tree', file=sys.stderr); sys.exit(1)

pages = []
def walk(node):
    if not node.get('isGroup', False) and node.get('dataURL'):
        pages.append({'id': node['_id'], 'name': node.get('name', '')})
    for c in node.get('children', []): walk(c)
walk(group_hit)

with open(ids_path, 'w') as f:
    for p in pages: f.write(p['id'] + '\n')

json.dump({
    'groupId': gid,
    'name': group_hit.get('name', ''),
    'path': ' / '.join(group_path),
    'pageCount': len(pages),
    'pages': pages,
}, open(meta_path, 'w'), ensure_ascii=False, indent=2)

print(f'group "{group_hit.get("name","?")}" → {len(pages)} 页', file=sys.stderr)
for p in pages:
    print(f'  - {p["name"]}  [{p["id"]}]', file=sys.stderr)
PY

  local total ok=0 fail=0 i=0
  total="$(wc -l < "$ids_file" | tr -d ' ')"
  info "开始批量拉取 $total 个页面..."
  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    i=$((i+1))
    info "[$i/$total] page $pid"
    if cmd_page "$app_id" "$pid" "$out_root" >/dev/null; then
      ok=$((ok+1))
    else
      info "WARN: page $pid 失败,继续"
      fail=$((fail+1))
    fi
  done < "$ids_file"

  info "==== group $group_id 完成 ===="
  info "成功 $ok / 失败 $fail / 总 $total"
  info "页面目录:$app_dir/pages/<PAGE_ID>/"
  info "分组元信息:$group_dir/"
  echo "$group_dir"
}
