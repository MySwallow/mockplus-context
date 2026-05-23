"""client.py - Mockplus API/CDN 客户端 + cookie + cache 管理。
   v0.5.0:cookie 默认放系统级 ~/.config/mockplus/cookie;cache 放 ~/.cache/mockplus/<APP_ID>/。
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple


# ============================================================
# 常量与路径
# ============================================================

API_HOST = "https://app.mockplus.cn"
CDN_HOST_RE = re.compile(r"^https://img(0[12])\.mockplus\.cn/")
CACHE_TTL_SECONDS = 24 * 3600
COOKIE_TTL_DAYS = 30  # 估算到期

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "X-MOCKPLUS-APP": "idoc-for-web|1.41.0-cn|macOS",
    "x-mockplus-lang": "zh-cn",
    "Referer": f"{API_HOST}/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/148.0.0.0 Safari/537.36",
}


def cache_root() -> Path:
    env = os.environ.get("MOCKPLUS_CACHE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "mockplus"


def cookie_file_path() -> Path:
    env = os.environ.get("MOCKPLUS_COOKIE_FILE")
    if env:
        return Path(env)
    return Path.home() / ".config" / "mockplus" / "cookie"


# ============================================================
# Cookie 读写
# ============================================================

def load_cookie() -> str:
    env = os.environ.get("MOCKPLUS_COOKIE")
    if env:
        return env.strip()
    fp = cookie_file_path()
    if fp.exists():
        text = fp.read_text()
        return "".join(l for l in text.splitlines() if not l.startswith("#")).strip()
    return ""


def require_cookie() -> str:
    c = load_cookie()
    if not c:
        print("ERR: cookie 未配置,运行 `mockplus cookie set`", file=sys.stderr)
        sys.exit(10)
    return c


def write_cookie(content: str) -> None:
    fp = cookie_file_path()
    fp.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    set_at = int(time.time())
    expires_at = set_at + COOKIE_TTL_DAYS * 86400
    body = (
        f"# set_at: {set_at}\n"
        f"# expires_at: {expires_at}\n"
        f"{content.strip()}\n"
    )
    fp.write_text(body)
    os.chmod(fp.parent, 0o700)
    os.chmod(fp, 0o600)


def cookie_status() -> dict:
    """返回 {path, exists, mode?, set_at?, expires_at?, days_left?}。"""
    fp = cookie_file_path()
    out = {"path": str(fp), "exists": fp.exists()}
    if not fp.exists():
        return out
    out["mode"] = oct(fp.stat().st_mode & 0o777)
    text = fp.read_text()
    for line in text.splitlines():
        try:
            if line.startswith("# set_at:"):
                out["set_at"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("# expires_at:"):
                out["expires_at"] = int(line.split(":", 1)[1].strip())
        except (ValueError, IndexError):
            # 损坏的注释行，跳过
            pass
    if "expires_at" in out:
        out["days_left"] = (out["expires_at"] - int(time.time())) // 86400
    return out


# ============================================================
# HTTP 基础
# ============================================================

def _get(path_or_url: str, cookie: Optional[str] = None, timeout: int = 20) -> bytes:
    url = path_or_url if path_or_url.startswith("http") else f"{API_HOST}{path_or_url}"
    req = urllib.request.Request(url, headers=dict(DEFAULT_HEADERS))
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} {url}", file=sys.stderr)
        raise
    except urllib.error.URLError as e:
        print(f"ERR: 网络错误 {e.reason} {url}", file=sys.stderr)
        raise


# ============================================================
# URL 解析
# ============================================================

def parse_url_or_short(s: str) -> Tuple[str, Optional[str]]:
    """完整 URL 或短形式 <APP_ID>:<TARGET_ID> 或 <APP_ID>。
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


# ============================================================
# Index + 页面元信息
# ============================================================

def fetch_index(app_id: str, refresh: bool = False) -> dict:
    """拉 /api/v1/app/module/<APP_ID>/design。24h cache。"""
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
    """返回 (pages, groups)。"""
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


def fetch_page_data(page_meta: dict) -> dict:
    """从 page_meta['dataURL'] 直接拉 sketch JSON,不带 cache(CDN 预签名 URL,无需 cookie)。"""
    raw = _get(page_meta["dataURL"])
    return json.loads(raw)


def get_page_data_cached(app_id: str, page_meta: dict, refresh: bool = False) -> dict:
    """带 cache 的版本:写到 cache_root/<APP_ID>/<PAGE_ID>/data.json。"""
    cdir = cache_root() / app_id / page_meta["id"]
    cdir.mkdir(mode=0o700, parents=True, exist_ok=True)
    data_fp = cdir / "data.json"
    if (not refresh and data_fp.exists()
            and time.time() - data_fp.stat().st_mtime < CACHE_TTL_SECONDS):
        return json.loads(data_fp.read_text())
    data = fetch_page_data(page_meta)
    data_fp.write_text(json.dumps(data, ensure_ascii=False))
    os.chmod(data_fp, 0o600)
    return data


def test_cookie_api(app_id: str) -> int:
    """cookie test <APP_ID> 实现:返回退出码。"""
    try:
        idx = fetch_index(app_id, refresh=True)
        pages, _groups = flatten_pages(idx)
        print(f"OK: code={idx.get('code')} 项目页面数={len(pages)}", file=sys.stderr)
        return 0
    except SystemExit:
        return 15
    except Exception as e:
        print(f"ERR: {e}", file=sys.stderr)
        return 14


# ============================================================
# Slice manifest 提取(从 data.json 找出所有切图节点)
# ============================================================

def url_hash(u: Optional[str]) -> Optional[str]:
    """https://img02.mockplus.cn/idoc/sketch/<hash>/wbyrvwvvlh.png → <hash>"""
    if not u:
        return None
    m = re.search(r"/sketch/([^/]+)/", u)
    return m.group(1) if m else None


def extract_slices(data: dict, wanted: Optional[set] = None) -> List[dict]:
    """遍历 data.json layers,返回切图 manifest 列表。
       wanted=None 表示全要;wanted={'hash1','hash2'} 或包含节点 sourceID 也接受。
    """
    slices = []

    def walk(n):
        s = n.get("slice")
        if isinstance(s, dict) and (s.get("bitmapURL") or s.get("svgURL")):
            h = url_hash(s.get("bitmapURL") or s.get("svgURL"))
            sid = n.get("basic", {}).get("sourceID", "")
            if h and (wanted is None or h in wanted or sid in wanted):
                slices.append({
                    "hash": h,
                    "name": n.get("basic", {}).get("name", ""),
                    "sourceID": sid,
                    "bitmapURL": s.get("bitmapURL", ""),
                    "svgURL": s.get("svgURL", ""),
                    "width": s.get("realSliceWidth") or n.get("bounds", {}).get("width"),
                    "height": s.get("realSliceHeight") or n.get("bounds", {}).get("height"),
                })
        for c in n.get("children", []):
            walk(c)

    walk(data.get("layers", {}))
    # 按 hash 去重
    seen = set()
    dedup = []
    for s in slices:
        if s["hash"] in seen:
            continue
        seen.add(s["hash"])
        dedup.append(s)
    return dedup


# ============================================================
# CDN 下载
# ============================================================

DOWNLOAD_MAX_WORKERS = 8


def _download_url(url: str, dest: Path) -> Tuple[bool, str]:
    """返回 (ok, msg)。已存在 + size>0 视为成功(cached)。"""
    if dest.exists() and dest.stat().st_size > 0:
        return True, "cached"
    try:
        req = urllib.request.Request(
            url, headers={"Referer": "https://app.mockplus.cn/"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            dest.write_bytes(r.read())
        return True, "downloaded"
    except (urllib.error.URLError, OSError) as e:
        return False, str(e)


def download_slices(slices: List[dict], out_dir: Path) -> dict:
    """下载 manifest 里所有 slice(bitmap+svg)。返回 {ok, fail, cached}。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for s in slices:
        for kind, url, ext in [("bitmap", s.get("bitmapURL"), "png"),
                                ("svg", s.get("svgURL"), "svg")]:
            if not url:
                continue
            dest = out_dir / f"{s['hash']}.{ext}"
            jobs.append((url, dest))
    ok = fail = cached = 0
    with ThreadPoolExecutor(max_workers=DOWNLOAD_MAX_WORKERS) as ex:
        results = list(ex.map(lambda j: _download_url(*j), jobs))
    for (url, dest), (success, msg) in zip(jobs, results):
        if success and msg == "cached":
            cached += 1
        elif success:
            ok += 1
        else:
            print(f"  FAIL {dest.name}: {msg}", file=sys.stderr)
            fail += 1
    return {"ok": ok, "fail": fail, "cached": cached, "total": len(jobs)}


def download_page_image(page_meta: dict, dest: Path) -> bool:
    """下载整页截图(design.png)。"""
    url = page_meta.get("imageURL", "")
    if not url:
        return False
    ok, _ = _download_url(url, dest)
    return ok
