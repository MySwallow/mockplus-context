# shellcheck shell=bash
# 智能 fetch:解析 URL → 自动判断是 page / group / 只索引

# cmd_fetch <URL> [out_root]
cmd_fetch() {
  local url="${1:?用法:mockplus fetch <URL> [out_root]}"
  local out_root="${2:-$OUT_ROOT_DEFAULT}"

  local parsed app_id target_id
  parsed="$(cmd_url "$url")"
  app_id="$(echo "$parsed" | grep '^APP_ID=' | cut -d= -f2)"
  target_id="$(echo "$parsed" | grep '^TARGET_ID=' | cut -d= -f2)"

  info "APP_ID=$app_id  TARGET_ID=${target_id:-(无)}"

  ensure_index "$app_id" "$out_root" >/dev/null

  if [ -z "$target_id" ]; then
    info "URL 没有具体 target,_index.json 已就位:$out_root/$app_id/"
    info "可下一步:mockplus tree $app_id   或   mockplus group $app_id <GROUP_ID>"
    return 0
  fi

  local kind
  kind="$(tree_kind "$out_root/$app_id" "$target_id")"
  case "$kind" in
    page)
      info "→ 命中单页"
      cmd_page "$app_id" "$target_id" "$out_root"
      ;;
    group)
      info "→ 命中分组(批量拉)"
      cmd_group "$app_id" "$target_id" "$out_root"
      ;;
    notfound)
      die "TARGET_ID=$target_id 不在 _index.json 树里。可能:URL 错误,或 _index.json 过期(rm $out_root/$app_id/_index.json 后重试)" 42
      ;;
    *)
      die "无法判断 TARGET_ID 类型(kind=$kind)" 43
      ;;
  esac
}
