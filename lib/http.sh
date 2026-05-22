# shellcheck shell=bash
# Mockplus API + CDN curl 包装

http_app() {
  local path="$1"; shift || true
  local cookie
  cookie="$(cookie_load)"
  debug "GET https://app.mockplus.cn$path"
  curl -sS --max-time 30 \
    -H 'Accept: application/json' \
    -H 'X-MOCKPLUS-APP: idoc-for-web|1.41.0-cn|macOS' \
    -H 'x-mockplus-lang: zh-cn' \
    -H 'Referer: https://app.mockplus.cn/' \
    -b "$cookie" \
    "$@" \
    "https://app.mockplus.cn$path"
}

http_cdn() {
  local url="$1"; shift || true
  debug "GET $url"
  curl -sS --max-time 60 \
    -H 'Referer: https://app.mockplus.cn/' \
    "$@" \
    "$url"
}
