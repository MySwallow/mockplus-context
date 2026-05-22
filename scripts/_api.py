"""Mockplus 私有 API 客户端 + URL 解析 + cache 层。"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Tuple, Optional

from _cookie import require_cookie


CACHE_TTL_SECONDS = 24 * 3600

API_HOST = "https://app.mockplus.cn"
CDN_HOST_RE = re.compile(r"^https://img(0[12])\.mockplus\.cn/")

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "X-MOCKPLUS-APP": "idoc-for-web|1.41.0-cn|macOS",
    "x-mockplus-lang": "zh-cn",
    "Referer": f"{API_HOST}/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
}


def cache_root() -> Path:
    env = os.environ.get("MOCKPLUS_OUT_ROOT")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "mockplus-context"


def _get(path_or_url: str, cookie: Optional[str] = None) -> bytes:
    url = path_or_url if path_or_url.startswith("http") else f"{API_HOST}{path_or_url}"
    req = urllib.request.Request(url, headers=dict(DEFAULT_HEADERS))
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} {url}", file=sys.stderr)
        raise


def parse_url_or_short(s: str) -> Tuple[str, Optional[str]]:
    """支持完整 URL 和短形式 <APP_ID>:<TARGET_ID> 或 <APP_ID>。
       返回 (app_id, target_id_or_None)。"""
    if s.startswith("http"):
        m = re.search(r"/app/([^/?#]+)", s)
        if not m:
            raise ValueError("URL 缺少 /app/<APP_ID>/ 段")
        app_id = m.group(1)
        tail = re.sub(r"[?#].*$", "", s).rstrip("/").rsplit("/", 1)[-1]
        target = None if tail == app_id else tail
        return app_id, target
    if ":" in s:
        a, t = s.split(":", 1)
        return a, t or None
    return s, None


def fetch_index(app_id: str, refresh: bool = False) -> dict:
    """拉 /api/v1/app/module/<APP_ID>/design,返回 _index.json 内容。24h cache。"""
    cdir = cache_root() / app_id
    cdir.mkdir(mode=0o700, parents=True, exist_ok=True)
    cache_fp = cdir / "_index.json"
    if (not refresh and cache_fp.exists()
            and time.time() - cache_fp.stat().st_mtime < CACHE_TTL_SECONDS):
        return json.loads(cache_fp.read_text())
    cookie = require_cookie()
    raw = _get(f"/api/v1/app/module/{app_id}/design", cookie=cookie)
    data = json.loads(raw)
    if data.get("code") != 0:
        print(f"ERR: API code={data.get('code')} msg={data.get('message')}", file=sys.stderr)
        sys.exit(21)
    cache_fp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.chmod(cache_fp, 0o600)
    return data


def flatten_pages(index: dict) -> Tuple[list, list]:
    """返回 (pages, groups)。每个 page/group 节点保留必要字段 + parentID。"""
    pages, groups = [], []

    def walk(node, path):
        p = path + [node.get("name", "?")]
        if node.get("isGroup", False):
            groups.append({
                "id": node["_id"],
                "name": node.get("name", ""),
                "path": " / ".join(p),
                "parentID": node.get("parentID", ""),
                "childIds": [c["_id"] for c in node.get("children", [])],
            })
        elif node.get("dataURL"):
            pages.append({
                "id": node["_id"],
                "name": node.get("name", ""),
                "path": " / ".join(p),
                "parentID": node.get("parentID", ""),
                "device": node.get("device", ""),
                "size": node.get("size", {}),
                "backgroundColor": node.get("backgroundColor", ""),
                "dataURL": node["dataURL"],
                "imageURL": node.get("imageURL", ""),
                "slicesCount": node.get("slicesCount", 0),
                "updatedAt": node.get("updatedAt", ""),
            })
        for c in node.get("children", []):
            walk(c, p)

    for root in index["payload"]["pages"]:
        walk(root, [])
    return pages, groups


def resolve_target_kind(app_id: str, target_id: Optional[str],
                       refresh: bool = False) -> str:
    """返回 'page' / 'group' / 'app' / 'notfound'。"""
    if not target_id:
        return "app"
    idx = fetch_index(app_id, refresh=refresh)
    pages, groups = flatten_pages(idx)
    if any(p["id"] == target_id for p in pages):
        return "page"
    if any(g["id"] == target_id for g in groups):
        return "group"
    return "notfound"


def fetch_page_data(page_meta: dict, refresh: bool = False) -> dict:
    """从 page_meta['dataURL'] 拉 sketch JSON。"""
    raw = _get(page_meta["dataURL"])
    return json.loads(raw)


def test_cookie(app_id: str) -> int:
    """对应 `mockplus cookie test <APP_ID>`。"""
    try:
        idx = fetch_index(app_id, refresh=True)
        print(f"OK: code={idx.get('code')} 项目页面数={sum(1 for _ in idx['payload']['pages'])}",
              file=sys.stderr)
        return 0
    except SystemExit:
        return 15
    except Exception as e:
        print(f"ERR: {e}", file=sys.stderr)
        return 14


def cmd_get_data(args):
    """P3 实现 transform 后再完整接入;P2 只验证能拉到 data.json。"""
    app_id, target_id = parse_url_or_short(args.url)
    kind = resolve_target_kind(app_id, target_id, refresh=args.refresh)
    if kind == "group":
        print(f"ERR: URL 指向 group,先用 `mockplus tree {app_id}` 浏览找到具体 page id 再重试",
              file=sys.stderr)
        return 22
    if kind != "page":
        print(f"ERR: TARGET_ID={target_id} 不是 page", file=sys.stderr)
        return 22

    idx = fetch_index(app_id, refresh=args.refresh)
    pages, _ = flatten_pages(idx)
    page_meta = next(p for p in pages if p["id"] == target_id)

    cdir = cache_root() / app_id / target_id
    cdir.mkdir(mode=0o700, parents=True, exist_ok=True)
    data_fp = cdir / "data.json"
    if (not args.refresh and data_fp.exists()
            and time.time() - data_fp.stat().st_mtime < CACHE_TTL_SECONDS):
        data = json.loads(data_fp.read_text())
    else:
        data = fetch_page_data(page_meta, refresh=args.refresh)
        data_fp.write_text(json.dumps(data, ensure_ascii=False))
        os.chmod(data_fp, 0o600)

    # P3 替换为 transform 后输出结构化 JSON
    from _transform import transform
    output = transform(data, page_meta, app_id)
    # P4 加入 schema 校验
    try:
        from _schema import validate_lite
        validate_lite(output)
    except (ValueError, ImportError) as e:
        # _schema 还不存在(P4 前)或校验失败
        if isinstance(e, ValueError):
            print(f"ERR: 输出 schema 校验失败: {e}", file=sys.stderr)
            return 50
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_inspect(args):
    """拉单页 + transform,只输出统计 + 异常,不输出完整 JSON。"""
    import json as _json
    from _transform import transform

    app_id, target_id = parse_url_or_short(args.url)
    kind = resolve_target_kind(app_id, target_id, refresh=args.refresh)
    if kind != "page":
        print(f"ERR: TARGET_ID={target_id} 不是 page", file=sys.stderr)
        return 22
    idx = fetch_index(app_id, refresh=args.refresh)
    pages, _ = flatten_pages(idx)
    page_meta = next(p for p in pages if p["id"] == target_id)
    data = fetch_page_data(page_meta, refresh=args.refresh)
    out = transform(data, page_meta, app_id)

    types_seen = {}
    asset_count = 0

    def walk(n):
        nonlocal asset_count
        types_seen[n.get("type", "?")] = types_seen.get(n.get("type", "?"), 0) + 1
        if n.get("asset"):
            asset_count += 1
        for c in n.get("children", []):
            walk(c)

    nodes_count = 0
    for n in out["nodes"]:
        walk(n)
        nodes_count += 1 + sum(1 for _ in _iter_descendants(n))

    summary = {
        "nodes": nodes_count,
        "styles": len(out["globalVars"]["styles"]),
        "sharedStyles": len(out["globalVars"]["sharedStyles"]),
        "typesSeen": types_seen,
        "assets": asset_count,
        "unhandledFields": out["_meta"]["unhandledFields"],
        "warnings": out["_meta"]["warnings"],
    }
    print(_json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _iter_descendants(node):
    for c in node.get("children", []):
        yield c
        yield from _iter_descendants(c)
