#!/usr/bin/env bash
# CI 校验: 语法检查 + smoke test

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PASS=0
FAIL=0

ok() { echo "  ✓ $*"; PASS=$((PASS+1)); }
ko() { echo "  ✗ $*" >&2; FAIL=$((FAIL+1)); }

echo '=== bash -n (语法检查) ==='
for f in bin/mockplus lib/*.sh scripts/validate.sh tests/smoke.sh; do
  [ -f "$f" ] || continue
  if bash -n "$f"; then ok "$f"; else ko "$f"; fi
done

echo
echo '=== shellcheck (如果可用) ==='
# SC1091 = 跨文件 source 信息,非问题
# SC2034 = OUT_ROOT_DEFAULT 等跨文件共享变量,非问题
if command -v shellcheck >/dev/null 2>&1; then
  if shellcheck -e SC1091,SC2034 -S warning bin/mockplus lib/*.sh scripts/validate.sh 2>&1; then
    ok 'shellcheck'
  else
    ko 'shellcheck 有警告/错误'
  fi
else
  echo '  (shellcheck 未安装,跳过)'
fi

echo
echo '=== smoke: help / url / cookie ==='

if ./bin/mockplus help >/dev/null; then ok 'help'; else ko 'help'; fi

P="$(./bin/mockplus url 'https://app.mockplus.cn/app/AAA/develop/design/BBB' 2>&1)"
if echo "$P" | grep -q '^APP_ID=AAA$' && echo "$P" | grep -q '^TARGET_ID=BBB$'; then
  ok 'url 解析(单页)'
else
  ko "url 解析(单页): $P"
fi

P="$(./bin/mockplus url 'https://app.mockplus.cn/app/AAA' 2>&1)"
if echo "$P" | grep -q '^APP_ID=AAA$' && echo "$P" | grep -q '^TARGET_ID=$'; then
  ok 'url 解析(只 app)'
else
  ko "url 解析(只 app): $P"
fi

if ! ./bin/mockplus url 'not-a-url' 2>/dev/null; then
  ok 'url 解析(非法 URL 报错)'
else
  ko 'url 解析(非法 URL 未报错)'
fi

TMPCK="$(mktemp -u /tmp/_mp_validate_cookie_XXXXXX)"
trap 'rm -f "$TMPCK"' EXIT

if MOCKPLUS_COOKIE_FILE="$TMPCK.nonexist" ./bin/mockplus cookie status >/dev/null; then
  ok 'cookie status(未配置不报错)'
else
  ko 'cookie status(未配置)'
fi

if echo '_clck=x; ds.sid=y; mockuuid=z' | MOCKPLUS_COOKIE_FILE="$TMPCK" ./bin/mockplus cookie set >/dev/null 2>&1; then
  [ -f "$TMPCK" ] && ok 'cookie set'
else
  ko 'cookie set'
fi

# 注意:不直接 | grep,因为 grep -q 提前关闭 stdin 会让 cookie_status 内的
# echo 触发 EPIPE,在 pipefail 下导致整体 fail。先 capture 再 grep。
STATUS_OUT="$(MOCKPLUS_COOKIE_FILE="$TMPCK" ./bin/mockplus cookie status 2>&1)"
if echo "$STATUS_OUT" | grep -q 'File mode:.*rw-------'; then
  ok 'cookie status (chmod 600 验证)'
else
  ko "cookie status chmod (实际输出: $STATUS_OUT)"
fi

if MOCKPLUS_COOKIE_FILE="$TMPCK" ./bin/mockplus cookie clear >/dev/null 2>&1; then
  [ ! -f "$TMPCK" ] && ok 'cookie clear'
else
  ko 'cookie clear'
fi

# tests/smoke.sh(更完整的离线测试,如果存在)
if [ -x tests/smoke.sh ]; then
  echo
  echo '=== tests/smoke.sh ==='
  if tests/smoke.sh; then ok 'tests/smoke.sh'; else ko 'tests/smoke.sh'; fi
fi

echo
echo "===== 结果: $PASS passed, $FAIL failed ====="
[ "$FAIL" -eq 0 ]
