# shellcheck shell=bash
# 单页拉取:data.json + design.png + assets/

# cmd_page <APP_ID> <PAGE_ID> [out_root]
# 输出 page_dir 到 stdout(其他进度信息走 stderr)
cmd_page() {
  local app_id="${1:?用法:mockplus page <APP_ID> <PAGE_ID> [out_root]}"
  local page_id="${2:?需要 PAGE_ID}"
  local out_root="${3:-$OUT_ROOT_DEFAULT}"

  ensure_index "$app_id" "$out_root" >/dev/null
  local app_dir="$out_root/$app_id"

  local page_dir="$app_dir/pages/$page_id"
  mkdir -p "$page_dir"

  python3 - "$app_dir/_pages.json" "$page_id" "$page_dir/page-meta.json" <<'PY' \
    || die "未找到 PAGE_ID=$page_id(可能 _index.json 过期,rm $app_dir/_index.json 后重试)" 31
import json, sys
pages = json.load(open(sys.argv[1]))['pages']
pid = sys.argv[2]
hit = next((p for p in pages if p['id'] == pid), None)
if not hit:
    print(f'ERR: page id={pid} not in _pages.json', file=sys.stderr); sys.exit(1)
json.dump(hit, open(sys.argv[3], 'w'), ensure_ascii=False, indent=2)
print(f'页面 "{hit["name"]}"  路径: {hit.get("path","")}', file=sys.stderr)
PY

  local data_url image_url
  data_url="$(python3 -c "import json;print(json.load(open('$page_dir/page-meta.json'))['dataURL'])")"
  image_url="$(python3 -c "import json;print(json.load(open('$page_dir/page-meta.json')).get('imageURL',''))")"

  info "下载 data.json"
  http_cdn "$data_url" -o "$page_dir/data.json"
  if [ ! -s "$page_dir/data.json" ]; then
    die "data.json 下载失败或为空" 33
  fi

  if [ -n "$image_url" ]; then
    info "下载 design.png"
    http_cdn "$image_url" -o "$page_dir/design.png"
    # PNG magic 校验:跨平台用 python 而非 xxd(Windows Git Bash 没有 xxd)
    if ! python3 -c "import sys;sys.exit(0 if open('$page_dir/design.png','rb').read(4)==b'\\x89PNG' else 1)" 2>/dev/null; then
      info "WARN: design.png 不是合法 PNG,可能为占位"
    fi
  fi

  cmd_assets "$page_dir"
  echo "$page_dir"
}

# cmd_assets <PAGE_DIR>
cmd_assets() {
  local page_dir="${1:?用法:mockplus assets <PAGE_DIR>}"
  [ -f "$page_dir/data.json" ] || die "未找到 $page_dir/data.json(先拉 page)" 32

  local assets_dir="$page_dir/assets"
  mkdir -p "$assets_dir"

  python3 - "$page_dir/data.json" "$page_dir/assets-manifest.json" <<'PY'
import json, sys, re
data = json.load(open(sys.argv[1]))
slices = []
def url_to_hash(u):
    m = re.search(r'/sketch/([^/]+)/', u)
    return m.group(1) if m else u.rsplit('/',1)[-1].rsplit('.',1)[0]
def walk(node):
    s = node.get('slice')
    if isinstance(s, dict) and (s.get('bitmapURL') or s.get('svgURL')):
        h = url_to_hash(s.get('bitmapURL') or s.get('svgURL'))
        slices.append({
            'hash': h,
            'name': node.get('basic', {}).get('name', ''),
            'sourceID': node.get('basic', {}).get('sourceID', ''),
            'bitmapURL': s.get('bitmapURL', ''),
            'svgURL': s.get('svgURL', ''),
            'width': s.get('realSliceWidth') or node.get('bounds', {}).get('width'),
            'height': s.get('realSliceHeight') or node.get('bounds', {}).get('height'),
        })
    for c in node.get('children', []): walk(c)
walk(data.get('layers', {}))
seen=set(); dedup=[]
for s in slices:
    if s['hash'] in seen: continue
    seen.add(s['hash']); dedup.append(s)
json.dump({'slices': dedup}, open(sys.argv[2], 'w'), ensure_ascii=False, indent=2)
print(f'切图清单:{len(dedup)} 个 unique(去重前 {len(slices)})', file=sys.stderr)
PY

  python3 - "$page_dir/assets-manifest.json" "$assets_dir" <<'PY'
import json, sys, os, urllib.request, ssl
manifest = json.load(open(sys.argv[1]))['slices']
out = sys.argv[2]
ctx = ssl.create_default_context()
ok = skip = fail = 0
for s in manifest:
    for url, ext in [(s.get('bitmapURL'), 'png'), (s.get('svgURL'), 'svg')]:
        if not url: continue
        dest = os.path.join(out, f"{s['hash']}.{ext}")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            skip += 1; continue
        try:
            req = urllib.request.Request(url, headers={'Referer': 'https://app.mockplus.cn/'})
            with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
                open(dest, 'wb').write(r.read())
            ok += 1
        except Exception as e:
            print(f'  FAIL {s["hash"]}.{ext}: {e}', file=sys.stderr); fail += 1
print(f'切图:下载 {ok},跳过 {skip},失败 {fail}', file=sys.stderr)
PY
}
