# shellcheck shell=bash
# 通用工具:日志 / 错误 / 依赖检查 / 默认配置

OUT_ROOT_DEFAULT="${MOCKPLUS_OUT_ROOT:-./mockplus-cache}"

die() { echo "ERR: $1" >&2; exit "${2:-1}"; }
info() { echo "[mockplus] $*" >&2; }
debug() { [ -n "${MOCKPLUS_DEBUG:-}" ] && echo "[debug] $*" >&2; return 0; }

require_tools() {
  local missing=()
  for t in "$@"; do
    command -v "$t" >/dev/null 2>&1 || missing+=("$t")
  done
  [ ${#missing[@]} -eq 0 ] || die "缺少工具:${missing[*]}(请先安装)" 3
}

# 启动时一次性依赖检查
require_tools curl python3
