# shellcheck shell=bash
# cookie 管理:set / test / status / clear / path / load

# cookie 默认存在 <repo>/config/cookie(已被 .gitignore)
# 这样每个 clone / worktree 自带独立 cookie,不污染用户全局目录
COOKIE_FILE="${MOCKPLUS_COOKIE_FILE:-${MOCKPLUS_ROOT_DIR:-$HOME/.config/mockplus-context}/config/cookie}"
COOKIE_ASSUMED_TTL_DAYS=30

cookie_load() {
  if [ -n "${MOCKPLUS_COOKIE:-}" ]; then
    printf '%s' "$MOCKPLUS_COOKIE" | tr -d '\n\r'
    return 0
  fi
  [ -f "$COOKIE_FILE" ] || die "未找到 cookie(运行:mockplus cookie set)" 10
  local line
  line="$(grep -v '^[[:space:]]*#' "$COOKIE_FILE" 2>/dev/null | sed -E '/^[[:space:]]*$/d' | head -n1 | tr -d '\n\r')"
  [ -n "$line" ] || die "cookie 文件 $COOKIE_FILE 没有有效内容(运行:mockplus cookie set)" 10
  printf '%s' "$line"
}

_cookie_compute_expires() {
  python3 -c "
import datetime
print((datetime.datetime.now().astimezone() + datetime.timedelta(days=$COOKIE_ASSUMED_TTL_DAYS)).strftime('%Y-%m-%dT%H:%M:%S%z'))
"
}

cookie_set() {
  local from_file=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --from-file) from_file="${2:?需要文件路径}"; shift 2 ;;
      --from-file=*) from_file="${1#*=}"; shift ;;
      -h|--help)
        cat <<'EOF'
mockplus cookie set [--from-file PATH]

读取 cookie 字符串(一行,格式: "key=val; key=val; ...")并写入
$MOCKPLUS_COOKIE_FILE(默认 <repo_root>/config/cookie),自动 chmod 600。

获取方式: 浏览器 (已登录 app.mockplus.cn) F12 → Application → Cookies →
app.mockplus.cn,把所有 cookie 拼成一行用 "; " 分隔。

不传 --from-file 时:
  - 终端交互:粘贴一行后回车
  - 管道输入:从 stdin 读
EOF
        return 0 ;;
      *) die "cookie set 未知参数:$1" 2 ;;
    esac
  done

  local raw=""
  if [ -n "$from_file" ]; then
    [ -f "$from_file" ] || die "源文件不存在:$from_file" 11
    raw="$(cat "$from_file")"
  else
    if [ -t 0 ]; then
      info "粘贴 cookie 字符串(单行),按 Enter:"
      IFS= read -r raw
    else
      raw="$(cat)"
    fi
  fi
  raw="$(printf '%s' "$raw" | tr -d '\n\r' | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//')"
  [ -n "$raw" ] || die "cookie 为空" 12

  if ! printf '%s' "$raw" | grep -q 'ds\.sid\|mockuuid'; then
    info "WARN: cookie 不含 ds.sid / mockuuid,可能不是有效 Mockplus cookie。仍写入。"
  fi

  mkdir -p "$(dirname "$COOKIE_FILE")"
  chmod 700 "$(dirname "$COOKIE_FILE")" 2>/dev/null || true
  local now expires
  now="$(date '+%Y-%m-%dT%H:%M:%S%z')"
  expires="$(_cookie_compute_expires)"
  {
    echo "# mockplus-context cookie"
    echo "# set_at: $now"
    echo "# expires_at: $expires (estimated ~${COOKIE_ASSUMED_TTL_DAYS}d)"
    printf '%s\n' "$raw"
  } > "$COOKIE_FILE"
  # Windows NTFS 上 chmod 是 no-op,允许失败
  chmod 600 "$COOKIE_FILE" 2>/dev/null || true
  info "已写入 $COOKIE_FILE (chmod 600)"
  info "预估到期:$expires"
  info "下一步建议:mockplus cookie test <APP_ID>"
}

cookie_clear() {
  if [ -f "$COOKIE_FILE" ]; then
    rm -f "$COOKIE_FILE"
    info "已删除 $COOKIE_FILE"
  else
    info "未找到 cookie 文件(无需删除)"
  fi
}

cookie_path() { echo "$COOKIE_FILE"; }

cookie_status() {
  echo "Cookie file:    $COOKIE_FILE"
  if [ -n "${MOCKPLUS_COOKIE:-}" ]; then
    echo "Env override:   MOCKPLUS_COOKIE 已设置(优先于文件)"
  fi
  if [ ! -f "$COOKIE_FILE" ]; then
    echo "Status:         未配置(运行 mockplus cookie set)"
    return 0
  fi
  local mode set_at expires
  mode="$(stat -f '%Sp' "$COOKIE_FILE" 2>/dev/null || stat -c '%A' "$COOKIE_FILE" 2>/dev/null || echo '?')"
  set_at="$(grep -E '^# set_at:' "$COOKIE_FILE" | head -n1 | sed -E 's/^# set_at:[[:space:]]*//')"
  expires="$(grep -E '^# expires_at:' "$COOKIE_FILE" | head -n1 | sed -E 's/^# expires_at:[[:space:]]*//')"
  echo "File mode:      $mode"
  echo "Set at:         ${set_at:-未知}"
  echo "Expires at:     ${expires:-未知}"
  if [ -n "$expires" ]; then
    local days_left
    days_left="$(python3 -c "
import datetime, re, sys
m = re.match(r'(\S+)', '''$expires''')
if not m: print('?'); sys.exit(0)
try:
    e = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S%z')
    now = datetime.datetime.now().astimezone()
    print(f'{(e - now).total_seconds()/86400:.1f}')
except Exception:
    print('?')
" 2>/dev/null)"
    echo "Days remaining: $days_left"
  fi
}

cookie_test() {
  local app_id="${1:-}"
  if [ -z "$app_id" ]; then
    die "用法:mockplus cookie test <APP_ID>(用任意一个你能访问的 mockplus 项目 ID,URL 中 /app/XXX/ 段)" 13
  fi
  info "调 /api/v1/app/module/$app_id/design"
  local body code
  body="$(http_app "/api/v1/app/module/$app_id/design" 2>/dev/null)" || die "请求失败(网络或 HTTP 层)" 14
  code="$(printf '%s' "$body" | python3 -c "import sys,json
try: print(json.load(sys.stdin).get('code','?'))
except Exception: print('?')" 2>/dev/null)"
  if [ "$code" = "0" ]; then
    info "✓ cookie 有效 (APP_ID=$app_id, code=0)"
    return 0
  fi
  printf '%s' "$body" | head -c 500 >&2; echo >&2
  die "✗ cookie 无效或权限不足(code=$code)。重新运行:mockplus cookie set" 15
}

cookie_main() {
  local sub="${1:-help}"; shift || true
  case "$sub" in
    set)    cookie_set "$@" ;;
    test)   cookie_test "$@" ;;
    status) cookie_status "$@" ;;
    clear)  cookie_clear "$@" ;;
    path)   cookie_path "$@" ;;
    help|-h|--help|"")
      cat <<'EOF'
mockplus cookie <subcmd>

子命令:
  set [--from-file PATH]    从 stdin 或文件读 cookie,写入 <repo_root>/config/cookie
  test <APP_ID>             用任意一个 APP_ID 调一次 API 验证 cookie 有效性
  status                    显示 cookie 路径/权限/设置时间/预估剩余天数
  clear                     删除 cookie 文件
  path                      打印 cookie 文件路径

环境变量 MOCKPLUS_COOKIE 优先于文件,适合 CI/临时会话。
详见 docs/cookie.md。
EOF
      ;;
    *) die "未知子命令:$sub(运行 mockplus cookie help)" 2 ;;
  esac
}
