"""纯 CDN 下载工具。不需要 cookie,只校验 host + 文件名后缀。"""
import json
import os
import re
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


HOST_OK = re.compile(r"^https://img(0[12])\.mockplus\.cn/")
MAX_WORKERS = 8


def _download_one(item: dict, local_path: Path) -> dict:
    url = item.get("url", "")
    name = item.get("fileName", "")
    if not HOST_OK.match(url):
        return {"url": url, "fileName": name, "ok": False, "reason": "invalid host"}
    if not url.endswith(".png"):
        return {"url": url, "fileName": name, "ok": False, "reason": "unsupported format"}
    if not name.endswith(".png"):
        return {"url": url, "fileName": name, "ok": False, "reason": "filename must end with .png"}

    dest = local_path / name
    if dest.exists() and dest.stat().st_size > 0:
        return {"url": url, "fileName": name, "ok": True, "cached": True}

    req = urllib.request.Request(url, headers={"Referer": "https://app.mockplus.cn/"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            dest.write_bytes(r.read())
        return {"url": url, "fileName": name, "ok": True, "bytes": dest.stat().st_size}
    except (urllib.error.URLError, OSError) as e:
        return {"url": url, "fileName": name, "ok": False, "reason": str(e)}


def cmd_download_assets(args):
    try:
        items = json.loads(args.downloads)
    except json.JSONDecodeError as e:
        print(f"ERR: --downloads JSON 解析失败: {e}", file=sys.stderr)
        return 2
    if not isinstance(items, list):
        print("ERR: --downloads 必须是数组", file=sys.stderr)
        return 2

    local_path = Path(args.local_path)
    local_path.mkdir(parents=True, exist_ok=True)

    downloaded, failed = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for r in ex.map(lambda it: _download_one(it, local_path), items):
            (downloaded if r["ok"] else failed).append(r)

    out = {"downloaded": downloaded, "failed": failed}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0  # 失败不算 fatal
