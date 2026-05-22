# mockplus-context skill 重构 Implementation Plan

> **For agentic workers:** Use the subagent-driven-development skill (recommended) or executing-plans skill to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `~/Documents/dev/github/mockplus-context/` 从 bash + lib CLI 重构为 Python 单文件 skill,产出结构化 JSON(对齐 figma-context 心智模型),提供 4 个子命令(`get-data` / `tree` / `download-assets` / `cookie *`)。

**Architecture:** Python 3.8+ 标准库实现,`scripts/mockplus.py` 作为 argparse 多子命令入口,各业务模块(`_api/_transform/_assets/_cookie/_tree/_group/_schema/_explore`)在同目录,无运行时 pip 依赖。dev 时 `pytest + jsonschema` 可选。

**Tech Stack:** Python 3.8+ / `urllib.request` / `argparse` / `concurrent.futures` / `json` / `hashlib`。dev 用 `pytest`,可选 `jsonschema`。

**Spec reference:** `docs/specs/2026-05-22-skill-redesign-design.md` —— 实施过程中以 spec §3-§13 为权威。

---

## Pre-flight: 阅读 spec

执行此 plan 前,先完整读 `docs/specs/2026-05-22-skill-redesign-design.md`。下面所有任务假设你已读过它,plan 不复述 spec。

---

## Phase 1: 字段侦察(P1)

> 目标: 不动新代码,先用现有 bash CLI 拉真实样本,跑 `_explore.py` 产出字段分布表。基于这份表设计 `_transform.py`。

### Task 1: 创建 `_explore.py` 字段侦察脚本

**Files:**
- Create: `scripts/_explore.py`

- [ ] **Step 1: 实现 `_explore.py`**

```python
#!/usr/bin/env python3
"""扫描若干 data.json,统计字段分布、enum 值集合、缺失模式。"""
import argparse, json, os, sys
from collections import Counter, defaultdict


def walk(node, path, field_count, enum_values, _samples):
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else k
            field_count[p] += 1
            if isinstance(v, (str, int, float, bool)) and not isinstance(v, bool):
                # 收集 string 类型字段的 enum 候选
                if isinstance(v, str) and len(v) < 64:
                    enum_values[p].add(v)
            walk(v, p, field_count, enum_values, _samples)
    elif isinstance(node, list):
        for item in node[:5]:  # 每个 list 只采样前 5 项,避免爆炸
            walk(item, f"{path}[]", field_count, enum_values, _samples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="包含 data.json 的目录(递归扫描)")
    ap.add_argument("--top", type=int, default=200, help="只打印出现频率 top N 字段")
    ap.add_argument("--enum-max", type=int, default=20, help="enum 取值超过这个数视为非枚举")
    args = ap.parse_args()

    field_count = Counter()
    enum_values = defaultdict(set)
    file_count = 0

    for root, _, files in os.walk(args.path):
        for f in files:
            if f == "data.json":
                fp = os.path.join(root, f)
                try:
                    data = json.load(open(fp))
                    walk(data, "", field_count, enum_values, None)
                    file_count += 1
                except Exception as e:
                    print(f"SKIP {fp}: {e}", file=sys.stderr)

    print(f"=== 扫描 {file_count} 份 data.json ===\n")
    print("## 字段出现频率(top {})".format(args.top))
    for path, cnt in field_count.most_common(args.top):
        line = f"  {cnt:6d}  {path}"
        # 附 enum 候选(取值数小于阈值)
        vals = enum_values.get(path, set())
        if 1 < len(vals) <= args.enum_max:
            line += f"  enum={sorted(vals)}"
        print(line)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证脚本可跑(空目录测试)**

Run: `python3 scripts/_explore.py /tmp 2>&1 | head -5`
Expected: 输出 `=== 扫描 0 份 data.json ===`,无 traceback

- [ ] **Step 3: Stage**

```bash
git add scripts/_explore.py
```

---

### Task 2: 用现有 bash CLI 拉真实样本(用户手工)

**Files:**
- Create: `tests/fixtures/_raw/` 目录存放原始 data.json

- [ ] **Step 1: 配 cookie(若未配)**

```bash
./bin/mockplus cookie status
# 未配则: ./bin/mockplus cookie set
```

- [ ] **Step 2: 找一个有 group 的 APP_ID,拉至少 2 个 group**

```bash
# 用户自己选 APP_ID 和 GROUP_ID(从 tree 看)
./bin/mockplus tree <APP_ID>
./bin/mockplus group <APP_ID> <GROUP_ID_A>
./bin/mockplus group <APP_ID> <GROUP_ID_B>
```

退出标准: `mockplus-cache/<APP_ID>/pages/` 下有 **至少 10 份** `data.json`,覆盖至少 2 种 device(ios1x / web / android 任 2)

- [ ] **Step 3: 备份样本到 tests fixtures(后续 P3 选 5 份作 fixture)**

```bash
mkdir -p tests/fixtures/_raw
find mockplus-cache -name 'data.json' -type f | while read f; do
  pageid=$(basename "$(dirname "$f")")
  cp "$f" "tests/fixtures/_raw/${pageid}.json"
done
ls tests/fixtures/_raw/ | wc -l   # ≥ 10
```

- [ ] **Step 4: Stage(raw 样本本身**不**入库,只 stage 目录占位)**

```bash
echo "tests/fixtures/_raw/" >> .gitignore
git add .gitignore
```

> 理由: raw 样本可能含项目私密数据,不入库。P3 选定的 5 份 fixture 才入库。

---

### Task 3: 跑 `_explore.py` 产出字段分布

**Files:**
- Create: `docs/specs/_field-survey.md`(临时文档,P7 可删)

- [ ] **Step 1: 跑探索脚本**

```bash
python3 scripts/_explore.py tests/fixtures/_raw/ > docs/specs/_field-survey.md
```

- [ ] **Step 2: 人工 review 输出**

打开 `docs/specs/_field-survey.md`,确认以下 spec §5 字段都出现:
- `basic.realType` 的 enum 集合
- `fill.colors[].type` 的 enum 集合(solid / linearGradient / radialGradient)
- `stroke.radius`、`stroke.borders[]` 存在
- `effect.shadows[]`、`effect.blur` 存在
- `text.styles[].font` 嵌套字段
- `slice.bitmapURL` / `slice.svgURL` 存在
- `sharedStyle.name` / `sharedStyle.type` 存在

如果某字段未出现 → fixture 数据不够多样,回 Task 2 补样本

- [ ] **Step 3: Stage**

```bash
git add docs/specs/_field-survey.md
```

---

## Phase 2: 骨架 + Cookie 管理(P2)

> 目标: `scripts/mockplus.py` argparse 框架就位,`_cookie.py` 5 子命令跑通,`_api.py` 能拉 `_index.json`(但不 transform)。

### Task 4: 创建 `mockplus.py` argparse 主入口

**Files:**
- Create: `scripts/mockplus.py`
- Create: `scripts/__init__.py`(空文件,标识为 package)

- [ ] **Step 1: 创建 `scripts/__init__.py`**

```python
```

(空内容)

- [ ] **Step 2: 实现 `scripts/mockplus.py` 主入口**

```python
#!/usr/bin/env python3
"""mockplus-context skill 主入口。
   子命令: get-data / tree / download-assets / cookie / inspect
"""
import argparse
import sys


def build_parser():
    p = argparse.ArgumentParser(prog="mockplus", description="Mockplus 设计稿抓取 skill")
    sub = p.add_subparsers(dest="cmd", required=True)

    # get-data
    g = sub.add_parser("get-data", help="拉单页结构化 JSON")
    g.add_argument("url", help="完整 URL 或 <APP_ID>:<PAGE_ID>")
    g.add_argument("--refresh", action="store_true")

    # tree
    g = sub.add_parser("tree", help="树形打印项目结构")
    g.add_argument("app_id")
    g.add_argument("--format", choices=["text", "json"], default="text")
    g.add_argument("--refresh", action="store_true")

    # download-assets
    g = sub.add_parser("download-assets", help="并发下载 CDN 图片")
    g.add_argument("--downloads", required=True,
                   help='JSON 数组,每项 {url, fileName}')
    g.add_argument("--local-path", required=True)

    # inspect
    g = sub.add_parser("inspect", help="拉单页并打印统计(回归检测)")
    g.add_argument("url")
    g.add_argument("--refresh", action="store_true")

    # cookie
    g = sub.add_parser("cookie", help="Cookie 管理")
    csub = g.add_subparsers(dest="cookie_cmd", required=True)
    cset = csub.add_parser("set")
    cset.add_argument("--from-file")
    ctest = csub.add_parser("test")
    ctest.add_argument("app_id")
    csub.add_parser("status")
    csub.add_parser("clear")
    csub.add_parser("path")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.cmd == "cookie":
        from _cookie import cmd_cookie
        return cmd_cookie(args)
    if args.cmd == "get-data":
        from _api import cmd_get_data
        return cmd_get_data(args)
    if args.cmd == "tree":
        from _tree import cmd_tree
        return cmd_tree(args)
    if args.cmd == "download-assets":
        from _assets import cmd_download_assets
        return cmd_download_assets(args)
    if args.cmd == "inspect":
        from _api import cmd_inspect
        return cmd_inspect(args)

    print(f"未知子命令: {args.cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
```

- [ ] **Step 3: 验证 argparse 解析**

Run: `python3 scripts/mockplus.py --help`
Expected: 列出 5 个子命令(get-data / tree / download-assets / inspect / cookie),exit 0

Run: `python3 scripts/mockplus.py get-data --help`
Expected: 列出 `url` 参数与 `--refresh`,exit 0

- [ ] **Step 4: Stage**

```bash
git add scripts/__init__.py scripts/mockplus.py
```

---

### Task 5: 实现 `_cookie.py`

**Files:**
- Create: `scripts/_cookie.py`

- [ ] **Step 1: 实现 `_cookie.py`**

```python
"""Cookie 加载与管理子命令。
   优先级: env MOCKPLUS_COOKIE > MOCKPLUS_COOKIE_FILE > <repo_root>/config/cookie
"""
import os
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COOKIE_FILE = REPO_ROOT / "config" / "cookie"
COOKIE_TTL_DAYS = 30  # 估算到期


def cookie_file_path() -> Path:
    env = os.environ.get("MOCKPLUS_COOKIE_FILE")
    return Path(env) if env else DEFAULT_COOKIE_FILE


def load_cookie() -> str:
    """返回 cookie 字符串;未配置返回空字符串。"""
    env = os.environ.get("MOCKPLUS_COOKIE")
    if env:
        return env.strip()
    fp = cookie_file_path()
    if fp.exists():
        text = fp.read_text()
        # 跳过 `# set_at:` `# expires_at:` 注释行
        return "".join(l for l in text.splitlines() if not l.startswith("#")).strip()
    return ""


def require_cookie() -> str:
    c = load_cookie()
    if not c:
        print("ERR: cookie 未配置,运行 `mockplus cookie set`", file=sys.stderr)
        sys.exit(10)
    return c


def _write_cookie(content: str) -> None:
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


def cmd_cookie(args):
    sub = args.cookie_cmd

    if sub == "set":
        if args.from_file:
            p = Path(args.from_file)
            if not p.exists():
                print(f"ERR: 文件不存在: {p}", file=sys.stderr)
                return 11
            content = p.read_text()
        elif sys.stdin.isatty():
            print("粘贴 cookie(单行),回车结束:", file=sys.stderr)
            content = sys.stdin.readline()
        else:
            content = sys.stdin.read()
        if not content.strip():
            print("ERR: cookie 为空", file=sys.stderr)
            return 12
        _write_cookie(content)
        print(f"OK: cookie 已写入 {cookie_file_path()}", file=sys.stderr)
        return 0

    if sub == "test":
        from _api import test_cookie
        return test_cookie(args.app_id)

    if sub == "status":
        fp = cookie_file_path()
        if not fp.exists():
            print(f"Status: 未配置(运行 mockplus cookie set)")
            print(f"Path:   {fp}")
            return 0
        text = fp.read_text()
        set_at = expires_at = None
        for line in text.splitlines():
            if line.startswith("# set_at:"):
                set_at = int(line.split(":", 1)[1].strip())
            elif line.startswith("# expires_at:"):
                expires_at = int(line.split(":", 1)[1].strip())
        now = int(time.time())
        print(f"Path:    {fp}")
        print(f"Mode:    {oct(fp.stat().st_mode & 0o777)}")
        if set_at:
            print(f"SetAt:   {time.ctime(set_at)}")
        if expires_at:
            days_left = (expires_at - now) // 86400
            print(f"Expires: {time.ctime(expires_at)} ({days_left} 天后)")
        return 0

    if sub == "clear":
        fp = cookie_file_path()
        if fp.exists():
            fp.unlink()
            print(f"OK: 已删除 {fp}", file=sys.stderr)
        return 0

    if sub == "path":
        print(cookie_file_path())
        return 0

    return 2
```

- [ ] **Step 2: 验证 status / path 子命令(无 cookie 也不报错)**

Run: `python3 scripts/mockplus.py cookie path`
Expected: 打印 `<repo_root>/config/cookie`,exit 0

Run: `python3 scripts/mockplus.py cookie status`
Expected: 打印 `Status: 未配置` 或现有 cookie 信息,exit 0

- [ ] **Step 3: Stage**

```bash
git add scripts/_cookie.py
```

---

### Task 6: 实现 `_api.py` API 客户端骨架

**Files:**
- Create: `scripts/_api.py`

- [ ] **Step 1: 实现 `_api.py`**

```python
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
        # 取最后一段为 target id
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
    """返回 (pages, groups)。每个 page/group 节点保留必要字段。"""
    pages, groups = [], []

    def walk(node, path):
        p = path + [node.get("name", "?")]
        if node.get("isGroup", False):
            groups.append({
                "id": node["_id"],
                "name": node.get("name", ""),
                "path": " / ".join(p),
                "childIds": [c["_id"] for c in node.get("children", [])],
            })
        elif node.get("dataURL"):
            pages.append({
                "id": node["_id"],
                "name": node.get("name", ""),
                "path": " / ".join(p),
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
    """从 page_meta['dataURL'] 拉 sketch JSON,24h cache。"""
    page_id = page_meta["id"]
    app_id_dir = None
    # 让调用方传入 app_id 决定缓存路径
    # 为保持函数纯净,这里只下载,缓存由 cmd_get_data 控制
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
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_inspect(args):
    """P4 完整实现。P2 stub。"""
    print("inspect: P4 stub", file=sys.stderr)
    return 0
```

- [ ] **Step 2: 验证拉 _index.json 路径(需真实 APP_ID + cookie)**

```bash
# 用户跑(需配过 cookie):
python3 scripts/mockplus.py cookie test <APP_ID>
```
Expected: 输出 `OK: code=0 项目页面数=N`,exit 0;`~/.cache/mockplus-context/<APP_ID>/_index.json` 已落地

- [ ] **Step 3: Stage**

```bash
git add scripts/_api.py
```

---

### Task 7: 验证 P2 骨架端到端跑通(`cookie test`)

**Files:** 无新建,只跑

- [ ] **Step 1: 跑 cookie test**

```bash
python3 scripts/mockplus.py cookie test <APP_ID>
```
Expected: 退出码 0;`~/.cache/mockplus-context/<APP_ID>/_index.json` 存在

- [ ] **Step 2: 验证 status 显示正确**

```bash
python3 scripts/mockplus.py cookie status
```
Expected: 含 SetAt / Expires / 剩余天数

- [ ] **Step 3: 无新 stage(本 task 仅验证)**

---

## Phase 3: Transform + Fixture 测试(P3)

> 目标: `_transform.py` 把 sketch JSON 转成 spec §5 schema 的结构化 JSON。fixture 黄金对照测试覆盖。

### Task 8: 实现 `_transform.py` 颜色/bounds/字段省略工具

**Files:**
- Create: `scripts/_transform.py`

- [ ] **Step 1: 实现 transform 工具函数**

```python
"""sketch JSON → 结构化 JSON。详见 docs/specs/2026-05-22-skill-redesign-design.md §5。"""
import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple


TRANSFORM_VERSION = "0.1.0"


# ---------- 颜色 ----------

def rgba_to_hex(c: Optional[dict]) -> Optional[str]:
    if not isinstance(c, dict):
        return None
    r = int(c.get("r", 0)); g = int(c.get("g", 0)); b = int(c.get("b", 0))
    a = float(c.get("a", 1))
    hex_ = f"#{r:02X}{g:02X}{b:02X}"
    if a < 0.999:
        return f"{hex_} (alpha={a:.2f})"
    return hex_


def normalize_bg(bg: str) -> str:
    """'#f5f5f5ff' → '#F5F5F5';'#xxxxxxAA' (alpha<1) → '#XXXXXX (alpha=0.67)'"""
    if not bg:
        return ""
    s = bg.lstrip("#").upper()
    if len(s) == 8:
        hex6 = "#" + s[:6]
        a_int = int(s[6:], 16)
        if a_int == 255:
            return hex6
        return f"{hex6} (alpha={a_int/255:.2f})"
    return "#" + s


# ---------- bounds ----------

def round_num(n):
    if n is None:
        return None
    if isinstance(n, (int, float)):
        if abs(n - round(n)) < 0.01:
            return int(round(n))
        return round(n * 2) / 2
    return n


def fmt_bounds(b: Optional[dict]) -> Optional[Dict[str, Any]]:
    """输出对齐 Sketch / Mockplus 原生命名 {top, left, width, height}。"""
    if not b:
        return None
    return {
        "top": round_num(b.get("top")),
        "left": round_num(b.get("left")),
        "width": round_num(b.get("width")),
        "height": round_num(b.get("height")),
    }


# ---------- 节点 ID 兜底 ----------

def stable_id(name: str, bounds: Optional[dict], parent_path: List[str]) -> str:
    key = f"{name}|{bounds}|{'.'.join(parent_path)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


# ---------- 字段省略(_compact) ----------

def compact(d: dict) -> dict:
    """删 null / [] / {} 值。"""
    return {k: v for k, v in d.items()
            if v is not None and v != [] and v != {}}


# ---------- 切图 URL → hash(切图引用复用) ----------

def url_to_hash(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    m = re.search(r"/sketch/([^/]+)/", u)
    return m.group(1) if m else u.rsplit("/", 1)[-1].rsplit(".", 1)[0]
```

- [ ] **Step 2: Stage**

```bash
git add scripts/_transform.py
```

---

### Task 9: 实现 `_transform.py` globalVars 抽取

**Files:**
- Modify: `scripts/_transform.py`(在 Task 8 文件末尾追加)

- [ ] **Step 1: 追加 globalVars 抽取函数**

```python
# ---------- globalVars 抽取 ----------

class StyleBank:
    """累积式 style 抽取器,返回 ref ID。"""

    def __init__(self):
        self.styles = {}                # style_id → spec
        self.shared_styles = {}         # sharedStyle.id (UUID) → {displayName, kind, stylesRef:[ids]}
        self._counters = {"fill": 0, "text": 0, "shadow": 0, "stroke": 0}
        self._shared_warnings = []      # one-to-many sharedStyle 警告

    def _next(self, kind: str) -> str:
        self._counters[kind] += 1
        return f"{kind}_{self._counters[kind]:03d}"

    def _intern(self, kind: str, spec: dict) -> str:
        # 用 spec 内容做指纹去重
        fp = repr(sorted(spec.items()))
        for k, v in self.styles.items():
            if k.startswith(kind + "_") and repr(sorted(v.items())) == fp:
                return k
        sid = self._next(kind)
        self.styles[sid] = spec
        return sid

    def fill(self, color_obj: dict) -> Optional[str]:
        if not isinstance(color_obj, dict):
            return None
        ctype = color_obj.get("type", "normal")
        val = color_obj.get("value")
        if ctype == "normal":
            hex_ = rgba_to_hex(val)
            return self._intern("fill", {"kind": "solid", "color": hex_}) if hex_ else None
        if ctype == "linearGradient" and isinstance(val, dict):
            stops = [{"color": rgba_to_hex(s.get("color")), "position": s.get("position", 0)}
                     for s in val.get("colorStops", [])]
            return self._intern("fill", {
                "kind": "linearGradient",
                "stops": stops,
                "from": {"x": val.get("fromX", 0), "y": val.get("fromY", 0)},
                "to": {"x": val.get("toX", 0), "y": val.get("toY", 1)},
            })
        if ctype == "radialGradient" and isinstance(val, dict):
            stops = [{"color": rgba_to_hex(s.get("color")), "position": s.get("position", 0)}
                     for s in val.get("colorStops", [])]
            return self._intern("fill", {"kind": "radialGradient", "stops": stops})
        return None

    def text(self, st: dict) -> Optional[str]:
        font = st.get("font") or {}
        space = st.get("space") or {}
        fstyles = st.get("fontStyles") or {}
        color = (font.get("color") or {}).get("value")
        # decoration: 只有任一为 truthy 时输出
        deco = {
            "bold": bool(fstyles.get("bold")),
            "italic": bool(fstyles.get("italic")),
            "underline": bool(fstyles.get("underLine")),
            "lineThrough": bool(fstyles.get("lineThrough")),
        }
        decoration = deco if any(deco.values()) else None
        spec = compact({
            "fontSize": font.get("size"),
            "fontFamily": font.get("family", ""),
            "fontWeight": font.get("weight"),               # 数字 weight (400/500/600)
            "fontWeightName": font.get("fontWeight", ""),   # 字符串("Regular"/"Medium"/"Semibold")
            "fontDisplayName": font.get("name", ""),        # 中文显示名,可缺
            "color": rgba_to_hex(color),
            "lineHeight": space.get("lineHeight"),
            "letterSpacing": space.get("letterSpacing"),
            "paragraph": space.get("paragraph"),
            "align": st.get("align", ""),
            "decoration": decoration,
        })
        return self._intern("text", spec) if spec else None

    def shadow(self, s: dict) -> Optional[str]:
        color = (s.get("color") or {}).get("value")
        spec = compact({
            "type": s.get("type", "outside"),               # outside | inside
            "offsetX": s.get("offsetX", 0),
            "offsetY": s.get("offsetY", 0),
            "blur": s.get("blur", 0),
            "spread": s.get("spread", 0),
            "color": rgba_to_hex(color),
        })
        return self._intern("shadow", spec) if spec else None

    def stroke(self, b: dict, dash: Optional[list] = None) -> Optional[str]:
        color = (b.get("color") or {}).get("value") if isinstance(b.get("color"), dict) else None
        spec = compact({
            "width": b.get("strokeWidth"),
            "color": rgba_to_hex(color),
            "position": b.get("type", "center"),            # inside / outside / center,来自 borders[].type
            "dash": list(dash) if dash else None,           # 仅非空数组输出
        })
        return self._intern("stroke", spec) if spec else None

    def shared(self, ss: dict, refs: List[str]) -> Optional[str]:
        """ss = node.sharedStyle = {id, name, type}; 返回 sharedStyle.id 作为 key。
           首次注册一对一;后续若同一 id 出现 refs 不一致,记录到 self._shared_warnings。"""
        sid = ss.get("id")
        name = ss.get("name", "")
        kind = ss.get("type", "")
        if not sid:
            return None
        existing = self.shared_styles.get(sid)
        if existing is None:
            self.shared_styles[sid] = {
                "displayName": name,
                "kind": kind,
                "stylesRef": list(refs),
            }
        elif sorted(existing["stylesRef"]) != sorted(refs):
            self._shared_warnings.append(
                f"sharedStyle {sid} ({name}) resolves to multiple concrete styles"
            )
        return sid
```

- [ ] **Step 2: Stage**

```bash
git add scripts/_transform.py
```

---

### Task 10: 实现 `_transform.py` 节点提取 + 树遍历

**Files:**
- Modify: `scripts/_transform.py`(追加)

- [ ] **Step 1: 追加节点提取**

```python
# ---------- 单节点提取 ----------

class TransformContext:
    def __init__(self):
        self.bank = StyleBank()
        self.unhandled = set()
        self.warnings = []
        self.input_field_count = 0
        self.seen_symbol_ids = set()    # 撞 ID 检测用

    def warn(self, msg: str):
        self.warnings.append(msg)


# 一个 layer 节点上我们消费的顶层字段(用于 unhandled 追踪)
LAYER_HANDLED = {
    "basic", "bounds", "fill", "stroke", "effect", "text", "slice",
    "sharedStyle", "children",
}

# basic 子字段我们消费的(supersets actual usage)
BASIC_HANDLED = {
    "id", "sourceID", "type", "realType", "name", "opacity",
    "libraryID", "libraryName", "imageID", "containerSourceName",
    "symbolId", "symbolMasterId",
}


def extract_node(node: dict, ctx: TransformContext, parent_path: List[str]) -> dict:
    basic = node.get("basic") or {}
    name = basic.get("name", "")
    btype = basic.get("type", "")            # 粗类 group/text/rect/path/symbol/image
    rtype = basic.get("realType", "")        # 细类 Artboard/Text/ShapePath/path/MSShapeGroup/SymbolInstance
    opacity = basic.get("opacity", 1)        # 注意: 在 basic 下,不在 node 顶层
    bounds = node.get("bounds") or {}

    nid = basic.get("sourceID") or stable_id(name, bounds, parent_path)
    if not basic.get("sourceID"):
        ctx.warn(f"node {nid} 缺 sourceID,用 stable hash")

    out = {
        "id": nid,
        "name": name,
        "type": btype,
        "realType": rtype,
        "bounds": fmt_bounds(bounds),
    }

    if isinstance(opacity, (int, float)) and opacity < 0.999:
        out["opacity"] = opacity

    # 设计系统组件路径(LLM 还原最关键的线索)
    csn = basic.get("containerSourceName")
    if csn:
        out["sourceComponent"] = csn

    # library 来源
    lib_id = basic.get("libraryID")
    lib_name = basic.get("libraryName")
    if lib_id or lib_name:
        out["library"] = compact({"id": lib_id, "name": lib_name})

    img_id = basic.get("imageID")
    if img_id:
        out["imageId"] = img_id

    # SymbolInstance: 暴露 master / symbol id
    sm_id = basic.get("symbolMasterId")
    s_id = basic.get("symbolId")
    if sm_id or s_id:
        sym = compact({"masterId": sm_id, "symbolId": s_id})
        if sym:
            out["symbol"] = sym
            # 检测撞 ID(同一 master 多次实例化时 sourceID 可能重复)
            if nid in ctx.seen_symbol_ids:
                ctx.warn(f"SymbolInstance sourceID {nid} 重复出现,可能不稳定")
            ctx.seen_symbol_ids.add(nid)

    # 文字(只取第一段;多段写 warning)
    text = node.get("text") or {}
    text_styles = text.get("styles") or []
    if text_styles:
        st = text_styles[0]
        if len(text_styles) > 1:
            ctx.warn(f"node {nid} 有 {len(text_styles)} 段 text.styles,仅取首段")
        out["text"] = {"value": st.get("value", ""), "style": ctx.bank.text(st)}

    # fill
    fill = node.get("fill") or {}
    fc = fill.get("colors") or []
    if fc:
        refs = [ctx.bank.fill(c) for c in fc]
        out["fills"] = [r for r in refs if r]

    # stroke borders + dash + radius
    stroke = node.get("stroke") or {}
    borders = stroke.get("borders") or []
    dash = stroke.get("dash") or []
    if borders:
        refs = [ctx.bank.stroke(b, dash=dash) for b in borders]
        out["strokes"] = [r for r in refs if r]
    radius = stroke.get("radius")
    if radius and any(r > 0 for r in radius):
        out["radius"] = [round_num(r) for r in radius]

    # shadows
    eff = node.get("effect") or {}
    shadows = eff.get("shadows") or []
    if shadows:
        refs = [ctx.bank.shadow(s) for s in shadows]
        out["shadows"] = [r for r in refs if r]

    # slice (asset)
    slice_ = node.get("slice")
    if isinstance(slice_, dict):
        url = slice_.get("bitmapURL")
        if url:
            out["asset"] = {
                "url": url,
                "intrinsicSize": {
                    "width": slice_.get("realSliceWidth") or bounds.get("width"),
                    "height": slice_.get("realSliceHeight") or bounds.get("height"),
                },
            }

    # sharedStyle: 字段从字符串改为 {id, name, kind} 对象;注册到 bank 用 id 做 key
    shared = node.get("sharedStyle") or {}
    if shared.get("id"):
        # 收集本节点已解析的具体 style refs,首次注册时挂上
        refs_for_shared = []
        if out.get("fills"):
            refs_for_shared.extend(out["fills"])
        if out.get("strokes"):
            refs_for_shared.extend(out["strokes"])
        if out.get("shadows"):
            refs_for_shared.extend(out["shadows"])
        if out.get("text") and out["text"].get("style"):
            refs_for_shared.append(out["text"]["style"])
        ctx.bank.shared(shared, refs_for_shared)
        out["sharedStyle"] = compact({
            "id": shared.get("id"),
            "name": shared.get("name", ""),
            "kind": shared.get("type", ""),
        })

    # 追踪 layer 顶层未消费字段
    for k in node.keys():
        if k not in LAYER_HANDLED:
            ctx.unhandled.add(f"layer.{k}")
    # 追踪 basic 子字段未消费
    for k in basic.keys():
        if k not in BASIC_HANDLED:
            ctx.unhandled.add(f"layer.basic.{k}")
    ctx.input_field_count += len(node) + len(basic)

    # children
    children = node.get("children") or []
    if children:
        out["children"] = [extract_node(c, ctx, parent_path + [name or rtype])
                           for c in children]

    return compact(out)
```

- [ ] **Step 2: Stage**

```bash
git add scripts/_transform.py
```

---

### Task 11: 实现 `_transform.py` 顶层 transform 函数

**Files:**
- Modify: `scripts/_transform.py`(追加)

- [ ] **Step 1: 追加 metadata 提取 + 顶层 transform 入口**

```python
# ---------- metadata ----------

def build_metadata(data: dict, page_meta: dict, app_id: str) -> dict:
    canvas = data.get("size") or {}
    artboard_scale = data.get("artboardScale", 1)
    # pageImage.url: 优先取 sketch JSON layers.URL(单一数据源),回落 page_meta.imageURL
    layers = data.get("layers") or {}
    layer_url = layers.get("URL", "") if isinstance(layers, dict) else ""
    image_url = layer_url or page_meta.get("imageURL", "")
    page_image = None
    if image_url:
        page_image = {
            "url": image_url,
            "intrinsicSize": {
                "width": int((canvas.get("width") or 0) * artboard_scale),
                "height": int((canvas.get("height") or 0) * artboard_scale),
            },
        }
    md = {
        "appId": app_id,
        "pageId": page_meta["id"],
        "name": page_meta.get("name", ""),
        "pageName": data.get("pageName", ""),                # sketch JSON 顶层 pageName,可能与 name 不同
        "path": page_meta.get("path", ""),
        "device": page_meta.get("device", "") or data.get("device", ""),
        "canvas": {
            "width": canvas.get("width"),
            "height": canvas.get("height"),
        },
        "backgroundColor": normalize_bg(data.get("backgroundColor", "")),
        "updatedAt": page_meta.get("updatedAt", ""),
        "source": data.get("source", ""),                    # sketch JSON 顶层 source
        "artboardScale": artboard_scale,
        "pluginVersion": data.get("pluginVersion", ""),
        "pageImage": page_image,
    }
    return compact(md)


# ---------- 顶层 ----------

def transform(data: dict, page_meta: dict, app_id: str) -> dict:
    ctx = TransformContext()
    layers = data.get("layers") or {}

    # 顶层 layers 节点本身视为根容器,extract 其 children
    root_children = layers.get("children") or []
    nodes = []
    for i, c in enumerate(root_children):
        try:
            nodes.append(extract_node(c, ctx, []))
        except Exception as e:
            nodes.append({
                "id": f"_err_{i:03d}",
                "type": "error",
                "realType": "error",
                "bounds": {"top": 0, "left": 0, "width": 0, "height": 0},
                "_error": str(e),
            })
            ctx.warn(f"root[{i}] transform 失败: {e}")

    # 合并 StyleBank 的 shared-style 一对多警告
    warnings_all = ctx.warnings + ctx.bank._shared_warnings

    return {
        "metadata": build_metadata(data, page_meta, app_id),
        "globalVars": {
            "styles": ctx.bank.styles,
            "sharedStyles": ctx.bank.shared_styles,
        },
        "nodes": nodes,
        "_meta": {
            "transformVersion": TRANSFORM_VERSION,
            "sketchPluginVersion": data.get("pluginVersion", ""),
            "documentVersion": data.get("documentVersion", ""),
            "inputFieldsTotal": ctx.input_field_count,
            "unhandledFields": sorted(ctx.unhandled),
            "warnings": warnings_all,
        },
    }
```

- [ ] **Step 2: 验证 transform 不 crash(用一份 raw 样本)**

```bash
python3 -c "
import json, sys
sys.path.insert(0, 'scripts')
from _transform import transform
import os
samples = os.listdir('tests/fixtures/_raw')[:1]
data = json.load(open(f'tests/fixtures/_raw/{samples[0]}'))
out = transform(data, {'id':'test','name':'t','path':'','device':'','imageURL':'','updatedAt':''}, 'X')
print(f'OK metadata={list(out[\"metadata\"].keys())} nodes={len(out[\"nodes\"])} styles={len(out[\"globalVars\"][\"styles\"])}')
"
```
Expected: `OK metadata=[...] nodes=N styles=M`,无 traceback

- [ ] **Step 3: Stage**

```bash
git add scripts/_transform.py
```

---

### Task 12: 选 fixture + 写 transform 黄金对照测试(TDD)

**Files:**
- Create: `tests/fixtures/simple-text.json`(从 `_raw` 选一份小的拷贝)
- Create: `tests/fixtures/nested-groups.json`
- Create: `tests/fixtures/with-slices.json`
- Create: `tests/fixtures/with-shared-styles.json`
- Create: `tests/fixtures/with-gradients.json`
- Create: `tests/fixtures/expected/simple-text.json`(transform 输出黄金值,review 后落)
- Create: `tests/test_transform.py`
- Create: `tests/requirements.txt`

- [ ] **Step 1: 选 5 份 fixture 拷贝到 `tests/fixtures/`**

基于 architect 报告对 design-response 的扫描,推荐 5 份(若 raw 目录里有同名 pageId):

| Fixture | 推荐 pageId | 理由 |
|---|---|---|
| `simple-text.json` | `gs_vrxrVlV`(设置, ios1x, slicesCount=0) | 文本密集,无切图,基线 |
| `nested-groups.json` | `1BAB8002-5A50-4983-B2D8-08971BF1B711`(采购申请单列表-老板)或类似嵌套深度 ≥3 的页 | 含 Artboard→group→symbol→text 4 层嵌套 + SymbolInstance |
| `with-slices.json` | `mD9fkFj7F9`(我的页面-老板端, Web1x, slicesCount=26) | 切图最多,验证 asset URL 抽取 |
| `with-shared-styles.json` | `bErGteettq`(我的页面-员工端, ios1x, slicesCount=4) | sharedStyle 引用密集 |
| `with-gradients.json` | `l2BuM3e1d`(启动页-android, mdpi)或 `EA-OsC8LQ`(经营看板, Web1x) | 渐变/特效;另多覆盖 mdpi / Web1x device |

```bash
cp tests/fixtures/_raw/gs_vrxrVlV.json tests/fixtures/simple-text.json
cp tests/fixtures/_raw/1BAB8002-5A50-4983-B2D8-08971BF1B711.json tests/fixtures/nested-groups.json
cp tests/fixtures/_raw/mD9fkFj7F9.json tests/fixtures/with-slices.json
cp tests/fixtures/_raw/bErGteettq.json tests/fixtures/with-shared-styles.json
cp tests/fixtures/_raw/l2BuM3e1d.json tests/fixtures/with-gradients.json
```

若某份 raw 没有,降级选 raw 目录里特征相近的页;**`with-gradients` 必须确认真的有 linearGradient**(grep `linearGradient` tests/fixtures/with-gradients.json),否则换页。

- [ ] **Step 2: 写 `tests/requirements.txt`**

```
pytest>=7.0
jsonschema>=4.0
```

- [ ] **Step 3: 写失败的测试 `tests/test_transform.py`**

```python
"""transform 黄金对照测试。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _transform import transform


FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED = FIXTURES / "expected"

FAKE_PAGE_META = {
    "id": "p-test", "name": "test", "path": "test",
    "device": "ios1x", "imageURL": "", "updatedAt": "",
}


@pytest.mark.parametrize("name", [
    "simple-text",
    "nested-groups",
    "with-slices",
    "with-shared-styles",
    "with-gradients",
])
def test_transform_matches_expected(name):
    data = json.load(open(FIXTURES / f"{name}.json"))
    actual = transform(data, FAKE_PAGE_META, "test-app")
    expected_fp = EXPECTED / f"{name}.json"
    if not expected_fp.exists():
        # 首次跑: 写黄金值供 review,测试失败强制人工 review
        expected_fp.parent.mkdir(exist_ok=True)
        expected_fp.write_text(json.dumps(actual, ensure_ascii=False, indent=2))
        pytest.fail(f"首次生成 {expected_fp},请 review 后重跑")
    expected = json.load(open(expected_fp))
    assert actual == expected, f"transform 输出与 {expected_fp} 不一致"
```

- [ ] **Step 4: 跑测试,首次会失败并生成 expected 文件**

Run: `cd ~/Documents/dev/github/mockplus-context && python3 -m pip install -r tests/requirements.txt && python3 -m pytest tests/test_transform.py -v`
Expected: 5 个测试都 FAIL,每个都报 "首次生成 ...,请 review 后重跑"

- [ ] **Step 5: 人工 review 生成的 expected/*.json**

打开每份 `tests/fixtures/expected/<name>.json`,对照 spec §5 schema 检查:
- metadata 字段完整(appId/pageId/canvas/backgroundColor)
- globalVars.styles 有合理的 fill_NNN / text_NNN
- nodes 树有合理的 id/type/bounds
- 无空对象、无 `null` 字段(`compact` 应过滤)

不对的话回 Task 8-11 修代码,然后 rm expected/*.json 重跑生成。

- [ ] **Step 6: 跑测试,这次应该全 PASS**

Run: `python3 -m pytest tests/test_transform.py -v`
Expected: 5 passed

- [ ] **Step 7: Stage**

```bash
git add tests/requirements.txt tests/test_transform.py \
        tests/fixtures/*.json tests/fixtures/expected/*.json
```

---

### Task 13: 接通 `cmd_get_data`,端到端跑通单页 transform

**Files:** 无新建(`cmd_get_data` 在 Task 6 已经引用 `_transform.transform`)

- [ ] **Step 1: 端到端跑通**

```bash
python3 scripts/mockplus.py get-data '<真实 Mockplus URL>' | head -30
```
Expected: stdout 是合法 JSON,顶层有 `metadata` / `globalVars` / `nodes` / `_meta`

- [ ] **Step 2: 跑 jq 验证结构(可选)**

```bash
python3 scripts/mockplus.py get-data '<URL>' | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert set(d.keys()) >= {'metadata','globalVars','nodes','_meta'}
print('OK schema 顶层')
"
```

- [ ] **Step 3: 无新文件 stage**

---

## Phase 4: Schema 守卫 + inspect(P4)

### Task 14: 实现 `_schema.py` validate_lite

**Files:**
- Create: `scripts/_schema.py`

- [ ] **Step 1: 实现轻量 validator(标准库)**

```python
"""轻量 schema 校验(纯标准库)。完整 jsonschema 校验可选。"""
import sys
from typing import Any


def _fail(path: str, msg: str):
    raise ValueError(f"{path}: {msg}")


def _check_type(val: Any, types, path: str):
    if not isinstance(val, types):
        _fail(path, f"expected {types}, got {type(val).__name__}")


def validate_lite(output: dict) -> None:
    """失败抛 ValueError,调用方决定 exit code。"""
    _check_type(output, dict, "$")
    for k in ("metadata", "globalVars", "nodes", "_meta"):
        if k not in output:
            _fail("$", f"missing top-level key '{k}'")

    md = output["metadata"]
    _check_type(md, dict, "metadata")
    for k in ("appId", "pageId", "canvas"):
        if k not in md:
            _fail("metadata", f"missing '{k}'")
    _check_type(md["canvas"], dict, "metadata.canvas")
    for k in ("width", "height"):
        if k not in md["canvas"]:
            _fail("metadata.canvas", f"missing '{k}'")

    gv = output["globalVars"]
    _check_type(gv, dict, "globalVars")
    _check_type(gv.get("styles", {}), dict, "globalVars.styles")
    _check_type(gv.get("sharedStyles", {}), dict, "globalVars.sharedStyles")

    nodes = output["nodes"]
    _check_type(nodes, list, "nodes")
    for i, n in enumerate(nodes):
        _validate_node(n, f"nodes[{i}]")


def _validate_node(n: dict, path: str):
    _check_type(n, dict, path)
    # 跳过容错降级生成的 _err_xxx 节点
    if n.get("type") == "error":
        return
    for k in ("id", "type", "realType", "bounds"):
        if k not in n:
            _fail(path, f"missing '{k}'")
    _check_type(n["bounds"], dict, f"{path}.bounds")
    for bk in ("top", "left", "width", "height"):
        if bk not in n["bounds"]:
            _fail(f"{path}.bounds", f"missing '{bk}' (expected top/left/width/height)")
    if "children" in n:
        _check_type(n["children"], list, f"{path}.children")
        for j, c in enumerate(n["children"]):
            _validate_node(c, f"{path}.children[{j}]")


def validate_full(output: dict) -> None:
    """如装了 jsonschema,跑更严格校验。否则 no-op + hint。"""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        print("[mockplus] hint: pip install jsonschema for stricter validation",
              file=sys.stderr)
        return
    jsonschema.validate(instance=output, schema=_FULL_SCHEMA)


_BOUNDS_SCHEMA = {
    "type": "object",
    "required": ["top", "left", "width", "height"],
    "properties": {
        "top": {"type": "number"},
        "left": {"type": "number"},
        "width": {"type": "number"},
        "height": {"type": "number"},
    },
}

_NODE_SCHEMA = {
    "type": "object",
    "required": ["id", "type", "realType", "bounds"],
    "properties": {
        "id": {"type": "string"},
        "type": {"type": "string"},
        "realType": {"type": "string"},
        "bounds": _BOUNDS_SCHEMA,
        "name": {"type": "string"},
        "opacity": {"type": "number"},
        "fills": {"type": "array", "items": {"type": "string"}},
        "strokes": {"type": "array", "items": {"type": "string"}},
        "shadows": {"type": "array", "items": {"type": "string"}},
        "sharedStyle": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "kind": {"type": "string"},
            },
        },
        "symbol": {
            "type": "object",
            "properties": {
                "masterId": {"type": "string"},
                "symbolId": {"type": "string"},
            },
        },
        # children 递归引用见下方
    },
}

_FULL_SCHEMA = {
    "type": "object",
    "required": ["metadata", "globalVars", "nodes", "_meta"],
    "properties": {
        "metadata": {
            "type": "object",
            "required": ["appId", "pageId", "canvas"],
            "properties": {
                "appId": {"type": "string"},
                "pageId": {"type": "string"},
                "canvas": {
                    "type": "object",
                    "required": ["width", "height"],
                    "properties": {
                        "width": {"type": "number"},
                        "height": {"type": "number"},
                    },
                },
                "artboardScale": {"type": "number"},
                "pluginVersion": {"type": "string"},
            },
        },
        "globalVars": {
            "type": "object",
            "properties": {
                "styles": {"type": "object"},
                "sharedStyles": {"type": "object"},
            },
        },
        "nodes": {"type": "array", "items": _NODE_SCHEMA},
        "_meta": {
            "type": "object",
            "properties": {
                "sketchPluginVersion": {"type": "string"},
                "documentVersion": {"type": "string"},
                "unhandledFields": {"type": "array"},
                "warnings": {"type": "array"},
            },
        },
    },
}
```

- [ ] **Step 2: 写 `tests/test_schema.py`**

```python
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _schema import validate_lite, validate_full

EXPECTED = Path(__file__).parent / "fixtures" / "expected"


def test_validate_lite_on_all_fixtures():
    for fp in EXPECTED.glob("*.json"):
        validate_lite(json.load(open(fp)))


def test_validate_full_on_all_fixtures():
    # 装了 jsonschema 时跑严格校验,否则 no-op
    for fp in EXPECTED.glob("*.json"):
        validate_full(json.load(open(fp)))


def test_validate_lite_rejects_missing_metadata():
    import pytest
    with pytest.raises(ValueError, match="missing top-level key 'metadata'"):
        validate_lite({"globalVars": {}, "nodes": [], "_meta": {}})
```

- [ ] **Step 3: 跑测试**

Run: `python3 -m pytest tests/test_schema.py -v`
Expected: 3 passed

- [ ] **Step 4: 把 validate_lite 接到 cmd_get_data 出口**

修改 `scripts/_api.py` 的 `cmd_get_data`(在 `output = transform(...)` 之后,`print(...)` 之前)插入:

```python
    from _schema import validate_lite
    try:
        validate_lite(output)
    except ValueError as e:
        print(f"ERR: 输出 schema 校验失败: {e}", file=sys.stderr)
        return 50
```

- [ ] **Step 5: Stage**

```bash
git add scripts/_schema.py scripts/_api.py tests/test_schema.py
```

---

### Task 15: 验证 unhandled fields tracking 在 fixture 上正常工作

> T10 已在 `extract_node` 内实现 unhandled 追踪(消费时标记 LAYER_HANDLED / BASIC_HANDLED)。本任务**只跑测试 + review 实际产生的 unhandled 集合**,而非新增代码。

**Files:** 仅修改 `tests/fixtures/expected/*.json`(根据实际 unhandled 输出 review 后更新)

- [ ] **Step 1: 跑 fixture 测试,观察 `_meta.unhandledFields`**

```bash
python3 -m pytest tests/test_transform.py -v
```

如果 expected/*.json 是上次跑生成的旧黄金,unhandledFields 可能不匹配 — 删了重生成:

```bash
rm tests/fixtures/expected/*.json
python3 -m pytest tests/test_transform.py -v   # 5 个测试都 FAIL,触发首次生成
```

- [ ] **Step 2: 人工 review 5 份 expected 的 `_meta.unhandledFields`**

对每份打开 expected,核对 `_meta.unhandledFields` 列表里的字段:
- **真正没消费的字段**(预期):`layer.position`、`layer.fontStyles`、`layer.basic.imageID`(若没值就不到这步)等
- **不该出现的字段**(异常):比如 `layer.bounds`、`layer.basic.opacity`、`layer.basic.type` —— 说明 T10 LAYER_HANDLED / BASIC_HANDLED 集合有遗漏,回 T10 修代码

如果有不该出现的字段 → 改代码,rm expected/*.json,重跑

- [ ] **Step 3: 跑测试,全 PASS**

```bash
python3 -m pytest tests/test_transform.py -v
```
Expected: 5 passed

- [ ] **Step 4: Stage**

```bash
git add tests/fixtures/expected/*.json
```

---

### Task 16: 实现 inspect 子命令

**Files:**
- Modify: `scripts/_api.py`

- [ ] **Step 1: 重写 `cmd_inspect`**

替换 `_api.py` 末尾的 `cmd_inspect` 函数:

```python
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
```

- [ ] **Step 2: 跑 inspect 验证**

Run: `python3 scripts/mockplus.py inspect '<真实 page URL>'`
Expected: stdout JSON 含 `nodes/styles/typesSeen/assets/unhandledFields/warnings`

- [ ] **Step 3: Stage**

```bash
git add scripts/_api.py
```

---

### Task 17: 容错降级(节点 panic 不中断整体)

**Files:**
- Modify: `scripts/_transform.py`

- [ ] **Step 1: 把 children 递归调用也包成 try/except**

T11 的 `transform()` 已经包装了 root_children 顶层容错。本步追加 **`extract_node` 内部递归 children 时也容错**,避免单节点 panic 拖垮整棵子树。

修改 `extract_node` 末尾的 children 处理段为:

```python
    # children(递归 + 容错)
    children = node.get("children") or []
    if children:
        safe_children = []
        for i, c in enumerate(children):
            try:
                safe_children.append(extract_node(c, ctx, parent_path + [name or rtype]))
            except Exception as e:
                safe_children.append({
                    "id": f"_err_{nid}_{i:03d}",
                    "type": "error",
                    "realType": "error",
                    "bounds": {"top": 0, "left": 0, "width": 0, "height": 0},
                    "_error": str(e),
                })
                ctx.warn(f"node {nid} child[{i}] transform 失败: {e}")
        out["children"] = safe_children
```

- [ ] **Step 2: 写测试,故意构造缺字段的 fixture**

新增 `tests/test_transform.py` 末尾:

```python
def test_transform_tolerates_missing_basic():
    from _transform import transform
    bad_data = {
        "layers": {
            "children": [
                {"bounds": {"left": 0, "top": 0, "width": 100, "height": 50}}
                # 故意没有 basic
            ]
        },
        "size": {"width": 375, "height": 812},
    }
    out = transform(bad_data, FAKE_PAGE_META, "test-app")
    assert len(out["nodes"]) == 1
    # 不 crash 即可
```

Run: `python3 -m pytest tests/test_transform.py::test_transform_tolerates_missing_basic -v`
Expected: PASS

- [ ] **Step 3: Stage**

```bash
git add scripts/_transform.py tests/test_transform.py
```

---

## Phase 5: Tree(P5)

> get-group 已从 spec 移除(Non-goals §2)—— group 浏览改由 `tree` 提供文本/JSON 视图,LLM 看到树后自行决定调 `get-data`。

### Task 19: 实现 `_tree.py`

**Files:**
- Create: `scripts/_tree.py`

- [ ] **Step 1: 实现 `_tree.py`**

```python
"""树形打印项目结构。
   DFS 全树遍历,容忍混合树(group 同时含 page + 子 group)。
   孤儿 page(parentID 指向不存在 group)由 design API 树直接缺失,本命令不显式追加。
"""
import json
import sys
from _api import fetch_index, flatten_pages


def _node_summary_json(node: dict) -> dict:
    """递归把 _index.json 节点转成精简 JSON(LLM 友好)。"""
    is_group = node.get("isGroup", False)
    out = {
        "id": node.get("_id"),
        "name": node.get("name", ""),
        "kind": "group" if is_group else "page",
    }
    if not is_group:
        size = node.get("size") or {}
        if size:
            out["size"] = {"width": size.get("width"), "height": size.get("height")}
        if node.get("device"):
            out["device"] = node["device"]
    children = node.get("children") or []
    if children:
        out["children"] = [_node_summary_json(c) for c in children]
    return out


def cmd_tree(args):
    idx = fetch_index(args.app_id, refresh=args.refresh)

    if args.format == "json":
        out = [_node_summary_json(root) for root in idx["payload"]["pages"]]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # text 格式(emoji + 缩进)
    def walk(node, depth):
        indent = "  " * depth
        if node.get("isGroup", False):
            print(f"{indent}📁 {node.get('name','?')}  [{node['_id']}]")
        else:
            size = node.get("size") or {}
            sz = f"({size.get('width','?')}x{size.get('height','?')})" if size else ""
            print(f"{indent}📄 {node.get('name','?')}  [{node['_id']}]  {sz}")
        for c in node.get("children", []):
            walk(c, depth + 1)

    for root in idx["payload"]["pages"]:
        walk(root, 0)

    # 检测孤儿 page(flatten_pages 找到但未在 walk 打印过)
    pages, _ = flatten_pages(idx)
    # 简单判定:孤儿 = parentID 不为空 + parentID 不在已知 group ids 集合里
    _, groups = flatten_pages(idx)
    group_ids = {g["id"] for g in groups}
    for p in pages:
        parent = p.get("parentID") if isinstance(p, dict) else None
        # flatten_pages 当前不保留 parentID,需 _api 侧补;若已有就检测
        if parent and parent not in group_ids and parent != "":
            print(f"⚠️  孤儿 page {p['id']} (parentID={parent} 不在树里): {p['name']}",
                  file=sys.stderr)
    return 0
```

> 注:`flatten_pages` 当前没保留 `parentID`,孤儿检测需要 T6 `_api.py` 在 `flatten_pages` 输出里追加 `parentID` 字段。实施时同步修这一处。

- [ ] **Step 2: 验证 text + json 输出**

Run: `python3 scripts/mockplus.py tree <APP_ID> | head -10`
Expected: 树形 emoji 输出

Run: `python3 scripts/mockplus.py tree <APP_ID> --format json | head -20`
Expected: 合法 JSON

- [ ] **Step 3: Stage**

```bash
git add scripts/_tree.py
```

---

### Task 20: 写 tree 单元测试(fixture 模拟 _index.json)

**Files:**
- Create: `tests/fixtures/_index-sample.json`
- Create: `tests/test_tree.py`

- [ ] **Step 1: 构造一个最小 `_index-sample.json`(含混合树 + 孤儿)**

```json
{
  "code": 0,
  "payload": {
    "pages": [
      {
        "_id": "g-root",
        "name": "v1",
        "isGroup": true,
        "children": [
          {
            "_id": "g-sub1",
            "name": "采购模块",
            "isGroup": true,
            "children": [
              {
                "_id": "p-001",
                "name": "申请页",
                "parentID": "g-sub1",
                "dataURL": "https://example.com/p001.json",
                "imageURL": "https://example.com/p001.png",
                "device": "ios1x",
                "size": {"width": 375, "height": 812}
              }
            ]
          },
          {
            "_id": "p-003",
            "name": "首页",
            "parentID": "g-root",
            "dataURL": "https://example.com/p003.json",
            "imageURL": "https://example.com/p003.png",
            "device": "ios1x",
            "size": {"width": 375, "height": 812}
          }
        ]
      }
    ]
  }
}
```

> 此 fixture 覆盖 architect 报告点出的"混合树"场景:`g-root` 直接含 `p-003` + 子 group `g-sub1`(含 `p-001`)。

- [ ] **Step 2: 写测试**

```python
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _api
import _tree


SAMPLE = json.load(open(Path(__file__).parent / "fixtures" / "_index-sample.json"))


def test_flatten_pages_extracts_2_pages_2_groups():
    pages, groups = _api.flatten_pages(SAMPLE)
    assert len(pages) == 2
    assert len(groups) == 2
    assert {p["id"] for p in pages} == {"p-001", "p-003"}


def test_tree_text_format_lists_all_nodes(capsys):
    with patch("_api.fetch_index", return_value=SAMPLE):
        class Args:
            app_id = "appX"
            format = "text"
            refresh = False
        _tree.cmd_tree(Args())
    out = capsys.readouterr().out
    assert "📁 v1" in out
    assert "📁 采购模块" in out
    assert "📄 申请页" in out
    assert "📄 首页" in out
    # 混合树:首页 跟 采购模块 同级,缩进相同
    lines = out.splitlines()
    indent_caigou = next(l for l in lines if "采购模块" in l).split("📁")[0]
    indent_shouye = next(l for l in lines if "首页" in l).split("📄")[0]
    assert indent_caigou == indent_shouye


def test_tree_json_format_returns_structured(capsys):
    with patch("_api.fetch_index", return_value=SAMPLE):
        class Args:
            app_id = "appX"
            format = "json"
            refresh = False
        _tree.cmd_tree(Args())
    out = json.loads(capsys.readouterr().out)
    assert out[0]["id"] == "g-root"
    assert out[0]["kind"] == "group"
    # DFS 全树
    children = out[0]["children"]
    assert any(c["id"] == "g-sub1" and c["kind"] == "group" for c in children)
    assert any(c["id"] == "p-003" and c["kind"] == "page" for c in children)
```

- [ ] **Step 3: 跑测试**

Run: `python3 -m pytest tests/test_tree.py -v`
Expected: 3 passed

- [ ] **Step 4: Stage**

```bash
git add tests/fixtures/_index-sample.json tests/test_tree.py
```

---

## Phase 6: Assets(P6)

### Task 21: 实现 `_assets.py` 并发下载

**Files:**
- Create: `scripts/_assets.py`

- [ ] **Step 1: 实现 `_assets.py`**

```python
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
    return 0 if not failed else 0  # 失败不算 fatal
```

- [ ] **Step 2: Stage**

```bash
git add scripts/_assets.py
```

---

### Task 22: 写 assets 测试(本地 http.server)

**Files:**
- Create: `tests/test_assets.py`

- [ ] **Step 1: 写测试**

```python
"""assets 下载测试。用本地 http.server 起一个临时 PNG。"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _assets


TINY_PNG = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000D4944415478DA63F8FFFF3F0005FE02FE9C5E1EFF0000000049454E44AE426082"
)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(TINY_PNG)

    def log_message(self, *a, **kw):
        pass


def _serve():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def test_invalid_host_rejected(tmp_path, capsys):
    class Args:
        downloads = json.dumps([{"url": "https://evil.com/x.png", "fileName": "x.png"}])
        local_path = str(tmp_path)
    _assets.cmd_download_assets(Args())
    out = json.loads(capsys.readouterr().out)
    assert len(out["failed"]) == 1
    assert out["failed"][0]["reason"] == "invalid host"


def test_non_png_extension_rejected(tmp_path, capsys):
    class Args:
        downloads = json.dumps([{"url": "https://img02.mockplus.cn/x.svg", "fileName": "x.svg"}])
        local_path = str(tmp_path)
    _assets.cmd_download_assets(Args())
    out = json.loads(capsys.readouterr().out)
    assert out["failed"][0]["reason"] == "unsupported format"


def test_download_via_local_server(tmp_path, capsys, monkeypatch):
    server = _serve()
    port = server.server_address[1]
    # Monkeypatch host regex to accept localhost for this test
    monkeypatch.setattr(_assets, "HOST_OK", _assets.re.compile(r"^http://127\.0\.0\.1:\d+/"))
    class Args:
        downloads = json.dumps([
            {"url": f"http://127.0.0.1:{port}/a.png", "fileName": "a.png"},
            {"url": f"http://127.0.0.1:{port}/b.png", "fileName": "b.png"},
        ])
        local_path = str(tmp_path)
    _assets.cmd_download_assets(Args())
    server.shutdown()
    out = json.loads(capsys.readouterr().out)
    assert len(out["downloaded"]) == 2
    assert (tmp_path / "a.png").exists()
    assert (tmp_path / "b.png").exists()
```

- [ ] **Step 2: 跑测试**

Run: `python3 -m pytest tests/test_assets.py -v`
Expected: 3 passed

- [ ] **Step 3: 端到端跑真实下载(可选)**

```bash
python3 scripts/mockplus.py download-assets \
  --downloads '[{"url":"https://img02.mockplus.cn/<真实切图 URL>","fileName":"test.png"}]' \
  --local-path /tmp/mockplus-test
ls /tmp/mockplus-test/
```

- [ ] **Step 4: Stage**

```bash
git add tests/test_assets.py
```

---

## Phase 7: 文档 + 收尾(P7)

### Task 23: 写 `SKILL.md`

**Files:**
- Create: `SKILL.md`

- [ ] **Step 1: 写 SKILL.md**

```markdown
---
name: mockplus-context
description: 从 Mockplus(摹客 app.mockplus.cn)设计稿抓取结构化数据 + 切图。**触发场景**:用户给出 Mockplus develop 页 URL(形如 `https://app.mockplus.cn/app/<APPID>/develop/design/<PAGEID>`)、要求"读 Mockplus 设计稿"、"按 Mockplus 还原 UI"、"导出 Mockplus 切图"等。返回 figma-context 风格的分层 JSON(metadata + globalVars + nodes),LLM 不再需要解析 raw sketch JSON。
---

# Mockplus Context

把 Mockplus develop URL 转换为结构化 JSON + 本地切图。
**接口对齐 figma-context MCP 心智模型**,LLM 用法一致。

启动时声明:**"Using mockplus-context to extract <PAGE_ID> from Mockplus."**

## 何时使用

- 输入是 Mockplus develop URL: `https://app.mockplus.cn/app/<APPID>/develop/design/<TARGET_ID>`
- 要"读 Mockplus 设计稿"、"按 Mockplus 还原 UI"、"导出切图"等

**不要用于**:
- Figma URL → 用 `figma-context` MCP
- 单张 PNG → 让用户先找到对应 Mockplus 页面

## 前置条件: cookie 配置(用户一次性)

```bash
python3 scripts/mockplus.py cookie set
# 浏览器(已登录 mockplus.cn) F12 → Application → Cookies → app.mockplus.cn
# 把所有 cookie 拼成一行粘贴
```

Cookie 有效期 ~30 天,过期重新 `set`。详见 `docs/cookie.md`。

## LLM 工作流(收到 URL 时按这个顺序)

1. 不知道 page id 或 URL 指向 group/app 时:`python3 scripts/mockplus.py tree <APP_ID>` 浏览结构,从中挑出具体 page id
2. URL 是 page:`python3 scripts/mockplus.py get-data <URL>` 拿结构化 JSON
3. 扫 nodes,找 `asset.url` + `metadata.pageImage.url`
4. 语义化命名,`python3 scripts/mockplus.py download-assets --downloads '[...]' --local-path <DIR>`
5. 进入下游(还原 Vue/Flutter/小程序 等)

## 命令参考(4 个主子命令 + inspect 辅助)

```bash
mockplus.py get-data <URL>                       # 单页结构化 JSON 到 stdout
mockplus.py tree <APP_ID> [--format text|json]   # 项目结构(text emoji 或 json 树)
mockplus.py download-assets --downloads '[...]' --local-path <DIR>
mockplus.py cookie {set|test|status|clear|path}  # cookie 管理(user-only)
mockplus.py inspect <URL>                        # 统计 + 异常(辅助,回归检测用)
```

## 输出 JSON schema 速览(get-data)

```json
{
  "metadata": { "appId", "pageId", "name", "device", "canvas", "backgroundColor", "pageImage" },
  "globalVars": {
    "styles": { "fill_001": {...}, "text_001": {...}, "shadow_001": {...}, "stroke_001": {...} },
    "sharedStyles": { "blue/600": { "stylesRef": [...], "kind": "LayerStyle" } }
  },
  "nodes": [
    { "id", "name", "type", "bounds", "fills", "strokes", "radius", "shadows",
      "sharedStyle", "text", "asset", "children" }
  ],
  "_meta": { "transformVersion", "inputFieldsTotal", "unhandledFields", "warnings" }
}
```

详见 `docs/specs/2026-05-22-skill-redesign-design.md` §5。

## 常见失败

| 现象 | 处理 |
|---|---|
| `cookie 未配置` (exit 10) | 跑 `mockplus.py cookie set` |
| `API code != 0` (exit 21) | cookie 过期 → `mockplus.py cookie set` 重配 |
| `URL 指向 group,先用 tree 浏览` (exit 22) | URL 指向 group/app,需先用 tree 找具体 page id |
| `_meta.unhandledFields` 不为空 | Mockplus 升级了 schema,反馈 issue |

## 隐私 & 安全

- cookie 只读取,不上传;`config/cookie` 自动 chmod 600
- API 响应 cache 在 `~/.cache/mockplus-context/`,user 自决是否清理
- 切图保存到 `--local-path` 指定目录,user 自管
```

- [ ] **Step 2: Stage**

```bash
git add SKILL.md
```

---

### Task 24: 重写 `README.md`

**Files:**
- Modify: `README.md`(完全重写)

- [ ] **Step 1: 重写**

```markdown
# mockplus-context

> 从 Mockplus(摹客)设计稿抓取**结构化 JSON + 切图**,接口对齐 figma-context MCP 心智模型。Python 单文件 skill,无外部依赖。

## 与 figma-context 的对照

| | figma-context | mockplus-context |
|---|---|---|
| 拿数据 | `get_figma_data(fileKey, nodeId?)` | `get-data <URL>`(仅整页,Mockplus API 物理约束) |
| 下图 | `download_figma_images(nodes[], localPath)` | `download-assets --downloads '[{url,fileName}]' --local-path` |
| 项目浏览 | LLM 自己从 file 推 | `tree <APP_ID>` 浏览 group/page 树 |
| 输出 | typed JSON(globalVars+nodes) | 同结构,字段沿用 Sketch 原生命名(bounds.top/left/width/height) |

## 安装

只要 Python 3.8+ 即可:

```bash
git clone https://github.com/<you>/mockplus-context.git
cd mockplus-context
python3 scripts/mockplus.py --help
```

加 PATH 后用着方便:

```bash
alias mockplus='python3 /path/to/mockplus-context/scripts/mockplus.py'
mockplus --help
```

## 5 分钟上手

```bash
# 1. 配 cookie(一次)
mockplus cookie set        # 粘贴浏览器 cookie

# 2. 验证
mockplus cookie test <任意 APP_ID>

# 3. 拉单页结构化 JSON
mockplus get-data 'https://app.mockplus.cn/app/<APP_ID>/develop/design/<PAGE_ID>' > page.json

# 4. 拉切图(把 page.json 里的 asset.url 喂过来)
mockplus download-assets \
  --downloads '[{"url":"https://img02.mockplus.cn/.../<hash>.png","fileName":"nav-back.png"}]' \
  --local-path ./assets
```

## 命令一览

| 命令 | 说明 |
|---|---|
| `mockplus get-data <URL>` | 单页结构化 JSON(stdout) |
| `mockplus tree <APP_ID> [--format text\|json]` | 项目结构(浏览 group/page) |
| `mockplus download-assets --downloads '[...]' --local-path <DIR>` | 并发下载切图 |
| `mockplus inspect <URL>` | 统计 + 异常(回归检测) |
| `mockplus cookie set [--from-file PATH]` | 写 cookie |
| `mockplus cookie test <APP_ID>` | 验证 cookie |
| `mockplus cookie status` | cookie 状态 |
| `mockplus cookie clear` | 删 cookie |
| `mockplus cookie path` | 打印 cookie 路径 |

详见 `docs/api-reference.md`。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MOCKPLUS_COOKIE` | (空) | 优先于文件 |
| `MOCKPLUS_COOKIE_FILE` | `config/cookie` | 覆盖 cookie 文件位置 |
| `MOCKPLUS_OUT_ROOT` | `~/.cache/mockplus-context` | API 响应 cache 根 |

## 文档

| 文档 | 内容 |
|---|---|
| `SKILL.md` | LLM 入口(给 Claude / Cursor 等读) |
| `docs/specs/2026-05-22-skill-redesign-design.md` | 设计 spec |
| `docs/api-reference.md` | 命令完整签名 |
| `docs/architecture.md` | 模块划分 |
| `docs/cookie.md` | cookie 获取 / 配置 |
| `docs/troubleshooting.md` | 故障排查 |
| `docs/examples.md` | 使用示例 |

## 开发 / 测试

```bash
python3 -m pip install -r tests/requirements.txt
python3 -m pytest tests/ -v
```

## 许可证

MIT
```

- [ ] **Step 2: Stage**

```bash
git add README.md
```

---

### Task 25: 重写 `docs/api-reference.md`

**Files:**
- Modify: `docs/api-reference.md`(完全重写)

- [ ] **Step 1: 重写**

```markdown
# API Reference

所有命令的完整签名 + 退出码 + 示例。

## 全局环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MOCKPLUS_COOKIE` | (空) | 优先于文件 |
| `MOCKPLUS_COOKIE_FILE` | `<repo>/config/cookie` | cookie 文件位置 |
| `MOCKPLUS_OUT_ROOT` | `~/.cache/mockplus-context` | API 响应 cache 根 |

## 退出码

- `0` 成功
- `2` CLI 参数错
- `10` cookie 未配置
- `11` `--from-file` 文件不存在
- `12` cookie 为空
- `14` HTTP 层失败
- `15` API code != 0(cookie 测试场景)
- `21` index API code != 0
- `22` TARGET_ID 误判 / 与子命令不匹配
- `50` 输出 schema 校验失败

---

## `mockplus get-data <URL> [--refresh]`

拉单页 sketch JSON → 转结构化 JSON → 输出到 stdout。

参数:
- `<URL>`: 完整 Mockplus develop 页 URL 或 `<APP_ID>:<PAGE_ID>` 短形式
- `--refresh`: 跳过 cache,强制重新拉

stdout: 结构化 JSON(详见 `docs/specs/2026-05-22-skill-redesign-design.md` §5)。

---

## `mockplus tree <APP_ID> [--format text|json] [--refresh]`

树形打印项目结构。

`--format text`(默认): 含 emoji 的层级文本。
`--format json`: `_index.json` 原始 payload.pages。

---

## `mockplus download-assets --downloads '[...]' --local-path <DIR>`

并发下载 CDN 切图。

`--downloads`: JSON 数组,每项 `{ "url": "...", "fileName": "..." }`。

校验:
- `url` 必须 `img(01|02).mockplus.cn` host
- `url` 与 `fileName` 必须 `.png` 结尾
- 文件已存在(size > 0) skip

stdout: `{ downloaded: [...], failed: [...] }`

---

## `mockplus inspect <URL> [--refresh]`

拉单页 + transform,只输出统计:

```json
{ "nodes", "styles", "sharedStyles", "typesSeen", "assets", "unhandledFields", "warnings" }
```

用于回归检测(检查 Mockplus 是否升级了 sketch schema)。

---

## `mockplus cookie set [--from-file PATH]`

写 cookie。stdin / TTY / 文件。自动 `chmod 600`,文件首部加 `# set_at:` `# expires_at:` 注释。

---

## `mockplus cookie test <APP_ID>`

调一次 design API 验证 cookie 有效。退出码 0 = ok, 15 = API 拒绝。

---

## `mockplus cookie status`

打印路径 / 权限 / 设置时间 / 剩余天数。未配置也返回 0。

---

## `mockplus cookie clear`

删 cookie 文件(幂等)。

---

## `mockplus cookie path`

打印 cookie 文件路径(stdout)。
```

- [ ] **Step 2: Stage**

```bash
git add docs/api-reference.md
```

---

### Task 26: 重写 `docs/architecture.md`

**Files:**
- Modify: `docs/architecture.md`(完全重写)

- [ ] **Step 1: 重写**

```markdown
# Architecture

## 包结构

```
scripts/
├── mockplus.py       # argparse 主入口,根据 cmd 分派到 _xxx 模块
├── _api.py           # Mockplus 私有 API 客户端 + URL 解析 + cache 层
├── _transform.py     # sketch JSON → 结构化 JSON
├── _assets.py        # 纯 CDN 下载(无 cookie 依赖)
├── _cookie.py        # cookie 加载 + 5 个子命令
├── _tree.py          # 树形打印
                    # (无 _group.py — get-group 已从 spec 移除,由 tree 提供 group 浏览)
├── _schema.py        # 输出 JSON 校验(validate_lite + validate_full)
└── _explore.py       # 字段侦察辅助(开发用)
```

每个 `_xxx.py` 暴露一个 `cmd_<name>(args)` 函数给 `mockplus.py` 调用。

## 数据流

```
URL → _api.parse_url_or_short() → (app_id, target_id)
              ↓
_api.fetch_index() → _api.resolve_target_kind()
              ↓
   page:  _api.cmd_get_data → _api.fetch_page_data → _transform.transform → _schema.validate_lite → stdout
   group: _group.cmd_get_group → 过滤 pages by path prefix → stdout
   app:   _tree.cmd_tree → 递归打印
              ↓
download-assets(独立流): _assets.cmd_download_assets → 并发 GET CDN → stdout
```

## 关键决策

- **Python 标准库 only**: `urllib.request` / `concurrent.futures` / `argparse`,运行时零 pip 依赖
- **schema 校验双层**: `validate_lite`(标准库)兜底,`validate_full`(jsonschema 可选)装了启用
- **API cache 24h**: `~/.cache/mockplus-context/<APP_ID>/{_index.json, <PAGE_ID>/data.json}`,`--refresh` 跳过
- **切图 cache 由用户管**: `download-assets --local-path` 决定保存位置,文件存在则 skip
- **globalVars 抽取**: 同样的 fill/text/shadow/stroke 用指纹去重,nodes 引用 ref 而非 inline,LLM token 占用大幅下降
- **未识别字段不静默丢**: transform 用 `LAYER_HANDLED` 集合标记已消费字段,其余进 `_meta.unhandledFields` → Mockplus 改 schema 立刻可见

详见 `docs/specs/2026-05-22-skill-redesign-design.md`。
```

- [ ] **Step 2: Stage**

```bash
git add docs/architecture.md
```

---

### Task 27: 重写 `docs/examples.md`

**Files:**
- Modify: `docs/examples.md`(完全重写)

- [ ] **Step 1: 重写**

```markdown
# Examples

## 1. 还原单页 UI

```bash
# 1. 拿结构化 JSON
mockplus get-data 'https://app.mockplus.cn/app/5gAIPn9LE/develop/design/0-ITsFIbmL' > page.json

# 2. 在 page.json 里找 asset.url(切图),也找 metadata.pageImage.url(整页图)
jq '.nodes | .. | objects | select(.asset) | .asset.url' page.json

# 3. 让 LLM 决定要哪些切图,起语义化文件名,下载
mockplus download-assets \
  --downloads '[
    {"url":"https://img02.mockplus.cn/idoc/sketch/abc.../...png","fileName":"nav-back.png"},
    {"url":"https://img02.mockplus.cn/idoc/sketch/def.../...png","fileName":"submit-icon.png"}
  ]' \
  --local-path ./assets
```

## 2. 批量浏览一个分组

```bash
# 看项目结构(text 或 json 格式都可)
mockplus tree 5gAIPn9LE
# 或解析 JSON 拿到具体 page id 列表:
mockplus tree 5gAIPn9LE --format json | \
  jq -r '.. | objects | select(.kind=="page") | .id'

# 决定要某几页之后,循环 get-data
for pid in p-001 p-002 p-003; do
  mockplus get-data 5gAIPn9LE:$pid > pages/$pid.json
done
```

## 3. 检测 Mockplus 是否升级了 schema

```bash
mockplus inspect 5gAIPn9LE:0-ITsFIbmL | jq '._meta.unhandledFields // empty'
# 空 → schema 没变
# 非空 → 有新字段没消费,需要更新 _transform.py
```

## 4. CI 中用

```bash
export MOCKPLUS_COOKIE='<from secret>'
mockplus cookie test $APP_ID || exit 1
mockplus get-data $URL > artifact.json
```

环境变量优先于文件,适合无状态 CI。
```

- [ ] **Step 2: Stage**

```bash
git add docs/examples.md
```

---

### Task 28: 更新 `docs/troubleshooting.md` 与 `docs/cookie.md`

**Files:**
- Modify: `docs/troubleshooting.md`
- Modify: `docs/cookie.md`(若有过时命令引用)

- [ ] **Step 1: 读现有 troubleshooting.md**

Run: `cat docs/troubleshooting.md`

把所有 `./bin/mockplus` / `mockplus xxx` 旧命令引用改成 `python3 scripts/mockplus.py xxx`(或 `mockplus xxx` 用 alias),退出码表照 Task 25 的更新。

- [ ] **Step 2: 读现有 cookie.md,把命令引用同样更新**

Run: `cat docs/cookie.md`

把 `./bin/mockplus cookie xxx` → `python3 scripts/mockplus.py cookie xxx`。

- [ ] **Step 3: Stage**

```bash
git add docs/troubleshooting.md docs/cookie.md
```

---

### Task 29: 更新 `.gitignore` + `CHANGELOG.md` + 删除旧 bash 代码

**Files:**
- Modify: `.gitignore`
- Modify: `CHANGELOG.md`
- Delete: `bin/mockplus`, `lib/*.sh`, `scripts/validate.sh`, `tests/smoke.sh`

- [ ] **Step 1: 重写 `.gitignore`**

```gitignore
# mockplus-context

# Cookie(绝不入库!)
/config/cookie
/config/cookie.bak

# Raw 样本(P1 用,不入库)
tests/fixtures/_raw/

# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/

# 备份 / 临时
*.bak
*.tmp
*.swp
.DS_Store

# IDE
.idea/
.vscode/
```

- [ ] **Step 2: 追加 CHANGELOG v0.2.0 条目**

读 `CHANGELOG.md`,在顶部追加:

```markdown
## v0.2.0 — 2026-05-22

**Breaking change: 整体重构为 Python skill,bash CLI 移除。**

### Added
- Python 单文件 skill (`scripts/mockplus.py`),5 个子命令 + `inspect`
- 结构化 JSON 输出(对齐 figma-context MCP 心智模型): `metadata` + `globalVars` + `nodes` + `_meta`
- `SKILL.md` LLM 入口
- `_meta.unhandledFields` 字段追踪,Mockplus 改 schema 立刻可见
- 测试覆盖: transform 黄金对照(5 fixture)、schema 校验、group/tree/assets 单元测试

### Changed
- 子命令重命名:
  - `page <APP> <PAGE>` → `get-data <URL>`(JSON 到 stdout,不再落文件)
  - `group <APP> <GROUP>` → **不再保留**,group 浏览改用 `tree`,LLM 据此循环调 `get-data`
  - `assets <PAGE_DIR>` → `download-assets --downloads ... --local-path ...`
  - `index` / `url` / `fetch` 不再暴露(内部 module)
- API cache 默认路径: `./mockplus-cache/` → `~/.cache/mockplus-context/`(env `MOCKPLUS_OUT_ROOT` 覆盖)
- `config/cookie` 路径保留兼容,老用户 cookie 不失效

### Removed
- `bin/mockplus` 及全部 `lib/*.sh`、`scripts/validate.sh`、`tests/smoke.sh`
- SVG 切图下载(首版 PNG-only,后续可加)

### Migration
- 老用户的 `config/cookie` 沿用,不用重配
- 切图 cache 默认位置变了,旧的 `./mockplus-cache/` 想保留 → `export MOCKPLUS_OUT_ROOT=./mockplus-cache`
- 脚本里 `./bin/mockplus xxx` 调用全部换为 `python3 scripts/mockplus.py xxx`
```

- [ ] **Step 3: 删除旧 bash 代码**

```bash
git rm bin/mockplus
git rm lib/common.sh lib/cookie.sh lib/api.sh lib/group.sh lib/http.sh lib/fetch.sh lib/page.sh
git rm scripts/validate.sh
git rm tests/smoke.sh
rmdir bin lib 2>/dev/null || true
```

- [ ] **Step 4: 验证仓库没有遗留 .sh 文件**

Run: `find . -name '*.sh' -not -path './.git/*'`
Expected: 无输出

- [ ] **Step 5: Stage 剩下的变更**

```bash
git add .gitignore CHANGELOG.md
```

- [ ] **Step 6: 跑全量测试,确认重构后仓库可用**

```bash
python3 -m pytest tests/ -v
```
Expected: 全 pass

- [ ] **Step 7: 端到端冒烟**

```bash
python3 scripts/mockplus.py --help
python3 scripts/mockplus.py cookie status
# 配过 cookie 的话:
python3 scripts/mockplus.py tree <APP_ID> | head -5
python3 scripts/mockplus.py inspect '<URL>' | python3 -m json.tool | head -10
```

如有问题回到对应 Phase 修。

---

## 完成

实施完成后,用户审阅 staged changes:

```bash
git status
git diff --staged | head -200
```

满意后 commit:

```bash
git commit -m "$(cat <<'EOF'
refactor: 重构为 Python skill,接口对齐 figma-context

详见 docs/specs/2026-05-22-skill-redesign-design.md 与
docs/plans/2026-05-22-skill-redesign-plan.md。

Breaking change: bash CLI 移除,子命令重命名为 figma-style。
EOF
)"
```
