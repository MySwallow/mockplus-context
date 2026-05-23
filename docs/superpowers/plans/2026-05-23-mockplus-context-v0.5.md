# mockplus-context v0.5.0 Implementation Plan

> **For agentic workers:** Use the subagent-driven-development skill (recommended) or executing-plans skill to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 mockplus-context 从 v0.4(JSON / hash token key / 7 个模块)合并到 v0.5.0(YAML 默认输出 / 设计师 token key / 4 个模块 + 新 all/download 接口)。

**Architecture:** 4 个 Python 模块:`mockplus.py`(argparse 入口) → `cli.py`(action 实现) → `transform.py`(sketch JSON → YAML) + `client.py`(API/cookie/CDN 下载)。`client.py` 替代 spec §4.1 的 `io.py`(避开 Python 标准库 `io` 模块命名冲突)。

**Tech Stack:** Python 3.8+(标准库 only,除 PyYAML)、pytest(测试)、urllib(HTTP)。

**Spec:** `docs/superpowers/specs/2026-05-23-mockplus-context-v0.5-design.md` (commit `55b2f59`)

**Branch:** `refactor/merge-best-subset`(已切,只比 main 多 1 commit:spec 文档)

---

## 偏离 spec 的决策

- **spec §4.1 `io.py` → `client.py`**:`io` 与 Python 标准库 `io` 模块同名,子目录里 `from io import StringIO` 会被本地遮蔽。改用 `client.py`,职责不变。其他 3 个模块名按 spec 保持。

---

## 任务总览

```
A. 基础层    Task 1-3   client.py (cookie + API + 下载)
B. transform Task 4-7   transform.py (YAML 输出 + 设计师 token key)
C. CLI       Task 8-12  cli.py (cookie/tree/data/download/all)
D. 入口      Task 13    mockplus.py (argparse)
E. 清理      Task 14    删 v0.4 老模块
F. 测试      Task 15-21 fixtures + tests
G. 文档      Task 22-27 SKILL.md / README / CHANGELOG / docs / references
H. CI        Task 28    ci.yml 加 PyYAML
I. 验证      Task 29-30 pytest + 手动 smoke
```

依赖:A → B,C → A+B,D → C,F → A+B+C+D。E 可在 F 之后任意时机做(避免误删后回不去)。G 与代码并行。H 在 F 之前(保证 CI 装 PyYAML)。I 最后。

---

## A. 基础层:`client.py`

### Task 1: 建 `client.py` 骨架 — cookie 管理

**Files:**
- Create: `skills/mockplus-context/scripts/client.py`

**Reference:**
- v0.4 `skills/mockplus-context/scripts/_cookie.py`(116 行,逻辑直接迁移)

- [ ] **Step 1: 实现 `client.py` 的 cookie 段**

```python
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
        if line.startswith("# set_at:"):
            out["set_at"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("# expires_at:"):
            out["expires_at"] = int(line.split(":", 1)[1].strip())
    if "expires_at" in out:
        out["days_left"] = (out["expires_at"] - int(time.time())) // 86400
    return out
```

- [ ] **Step 2: 运行 Python 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/client.py').read())"`
Expected: 无输出(语法 OK)

- [ ] **Step 3: 暂存变更**

```bash
git add skills/mockplus-context/scripts/client.py
```

**不要 commit**——由用户审阅后自行 commit。

---

### Task 2: `client.py` 加 API 客户端

**Files:**
- Modify: `skills/mockplus-context/scripts/client.py` (append)

**Reference:**
- v0.4 `skills/mockplus-context/scripts/_api.py:36-138`(`_get`/`parse_url_or_short`/`fetch_index`/`flatten_pages`/`resolve_target_kind`/`fetch_page_data`)
- cache 路径从 `~/.cache/mockplus-context/` 改 `~/.cache/mockplus/`(已在 Task 1 的 `cache_root()` 落地)

- [ ] **Step 1: 在 `client.py` 末尾追加 API 客户端**

```python
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


def fetch_page_data(page_meta: dict, refresh: bool = False) -> dict:
    """从 page_meta['dataURL'] 拉 sketch JSON。带 page 级 cache(写到 cache_root/<APP>/<PAGE>/data.json)。"""
    app_id_unknown = None  # 调用者负责传 cache 路径,本函数仅做网络 IO
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
    data = fetch_page_data(page_meta, refresh=refresh)
    data_fp.write_text(json.dumps(data, ensure_ascii=False))
    os.chmod(data_fp, 0o600)
    return data


def test_cookie_api(app_id: str) -> int:
    """cookie test <APP_ID> 实现:返回退出码。"""
    try:
        idx = fetch_index(app_id, refresh=True)
        pages = sum(1 for _ in idx['payload']['pages'])
        print(f"OK: code={idx.get('code')} 项目页面数={pages}", file=sys.stderr)
        return 0
    except SystemExit:
        return 15
    except Exception as e:
        print(f"ERR: {e}", file=sys.stderr)
        return 14
```

- [ ] **Step 2: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/client.py').read())"`
Expected: 无输出

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/scripts/client.py
```

---

### Task 3: `client.py` 加 CDN 下载 + slice 提取

**Files:**
- Modify: `skills/mockplus-context/scripts/client.py` (append)

**Reference:**
- v0.4 `skills/mockplus-context/scripts/_assets.py:11-50`(`_download_one` + 并发)
- 备份版 `~/.claude/backups/mockplus-context.backup.20260523-183712/scripts/mockplus.sh:232-291`(slice 提取 + 下载循环)
- v0.5 关键差异:不再接 `--downloads JSON`,而是接 `--nodes hash,...`,从 cache 里的 `data.json` 反查切图 URL

- [ ] **Step 1: 在 `client.py` 末尾追加下载相关函数**

```python
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
```

- [ ] **Step 2: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/client.py').read())"`
Expected: 无输出

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/scripts/client.py
```

---

## B. 核心 transform:`transform.py`

### Task 4: 建 `transform.py` 骨架 + helpers

**Files:**
- Create: `skills/mockplus-context/scripts/transform.py`

**Reference:**
- v0.4 `_transform.py:11-83`(`rgba_to_hex`/`normalize_bg`/`round_num`/`stable_id`/`compact`/`url_to_hash`)
- 备份版 `to-yaml.py:34-100`(rgba_to_str / color_obj_to_value / url_hash)
- v0.5 颜色输出格式跟备份版一致:alpha=1 → `#RRGGBB`;alpha<1 → `rgba(r, g, b, a.xx)`(不是 v0.4 的 `#RRGGBB (alpha=0.50)` 带括号)

- [ ] **Step 1: 写 `transform.py` 骨架与 helpers**

```python
"""transform.py - Mockplus sketch JSON → 结构化 dict(可序列化为 YAML 或 JSON)。

v0.5.0 输出契约见 docs/superpowers/specs/2026-05-23-mockplus-context-v0.5-design.md §6。

关键差异(对比 v0.4):
- bounds 拆为 layout (引用 globalVars.styles.layout_NNNNNN)
- fills 是数组形式: ['#RRGGBB'] 或 [{type:GRADIENT_LINEAR, gradient}] 或 [{type:IMAGE, imageRef}]
- textStyle 是单一字符串引用,key 用 sharedStyle.name(若有);否则 textStyle_NNNNNN
- 6 位序号(fill_000001),不是 3 位(fill_001)
- alpha < 1 输出 rgba(r,g,b,a.xx),不是 v0.4 的 #RRGGBB (alpha=0.5)
"""
import hashlib
import math
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional


TRANSFORM_VERSION = "0.5.0"


# ============================================================
# 颜色
# ============================================================

def rgba_to_str(c: Optional[dict]) -> Optional[str]:
    """{r,g,b,a} → '#RRGGBB' (alpha=1) 或 'rgba(r, g, b, a.xx)' (alpha<1)。"""
    if not isinstance(c, dict):
        return None
    r = int(c.get("r", 0))
    g = int(c.get("g", 0))
    b = int(c.get("b", 0))
    a = float(c.get("a", 1))
    if a >= 0.999:
        return f"#{r:02X}{g:02X}{b:02X}"
    return f"rgba({r}, {g}, {b}, {a:.2f})"


def normalize_bg(bg: str) -> str:
    """'#f5f5f5ff' → '#F5F5F5';带 alpha 走 rgba()。"""
    if not bg:
        return ""
    s = bg.lstrip("#").upper()
    if len(s) == 8:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        a_int = int(s[6:], 16)
        if a_int == 255:
            return f"#{s[:6]}"
        return f"rgba({r}, {g}, {b}, {a_int/255:.2f})"
    return f"#{s}"


# ============================================================
# bounds / 数字
# ============================================================

def round_num(n):
    if n is None:
        return None
    if isinstance(n, (int, float)):
        if abs(n - round(n)) < 0.01:
            return int(round(n))
        return round(n * 2) / 2
    return n


# ============================================================
# 节点 ID 兜底
# ============================================================

def stable_id(name: str, bounds: Optional[dict], parent_path: List[str]) -> str:
    key = f"{name}|{bounds}|{'.'.join(parent_path)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


# ============================================================
# compact + url_hash
# ============================================================

def compact(d: dict) -> dict:
    """删 None / [] / {} / '' 值,保留 0 和 False。"""
    return {k: v for k, v in d.items()
            if v is not None and v != [] and v != {} and v != ""}


def url_hash(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    m = re.search(r"/sketch/([^/]+)/", u)
    return m.group(1) if m else None
```

- [ ] **Step 2: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/transform.py').read())"`
Expected: 无输出

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/scripts/transform.py
```

---

### Task 5: `transform.py` 实现 TokenTable(设计师命名)

**Files:**
- Modify: `skills/mockplus-context/scripts/transform.py` (append)

**Reference:**
- 备份版 `to-yaml.py:103-300`(TokenTable 类)
- v0.4 `_transform.py:87-200`(StyleBank 类,设计参考但 key 规则不一样)

**关键命名规则(spec §6.1):**

| 类型 | key 形态 | 例子 |
|---|---|---|
| fill | `fill_NNNNNN` | `fill_000003` |
| stroke | `stroke_NNNNNN` | `stroke_000001` |
| effect | `effect_NNNNNN` | `effect_000001` |
| layout | `layout_NNNNNN` | `layout_000007` |
| textStyle(有 sharedStyle) | sharedStyle.name 原样 | `01文字色1/16px/semibold/居中对齐 Style` |
| textStyle(无 sharedStyle) | `textStyle_NNNNNN` | `textStyle_000001` |

冲突场景(两个 sharedStyle 同名 + spec 不同):后到的加 `_2`/`_3` 后缀。

- [ ] **Step 1: 在 `transform.py` 末尾追加 TokenTable 类**

```python
# ============================================================
# Token 表(globalVars.styles 注册器)
# ============================================================

class TokenTable:
    """累积式 token 抽取器,相同 spec 复用 key。
       textStyle key 优先用 sharedStyle.name(语义化),其他用 6 位序号。"""

    def __init__(self):
        self.styles = OrderedDict()  # key → spec(可能是 dict 或 list)
        self._counters = {"fill": 0, "stroke": 0, "effect": 0,
                          "layout": 0, "textStyle": 0}
        # 用 fingerprint 做去重:fingerprint → key
        self._fingerprints = {}

    def _next_seq_key(self, kind: str) -> str:
        self._counters[kind] += 1
        return f"{kind}_{self._counters[kind]:06d}"

    def _intern(self, kind: str, spec, preferred_key: Optional[str] = None) -> str:
        """注册 spec,返回 key。
           preferred_key 非空时(有 sharedStyle.name):
             - 若 preferred_key 已存在但 spec 不同 → 加 _2/_3 后缀
             - 若 preferred_key 已存在且 spec 同 → 直接复用
           preferred_key 为空时:用 fingerprint 去重 + 自动序号 key。
        """
        fp = (kind, _fingerprint(spec))

        if preferred_key:
            # 命名优先策略:同名同 spec → 复用;同名不同 spec → 加后缀
            existing = self.styles.get(preferred_key)
            if existing is not None and _fingerprint(existing) == fp[1]:
                return preferred_key
            if existing is None:
                self.styles[preferred_key] = spec
                self._fingerprints[fp] = preferred_key
                return preferred_key
            # 同名不同 spec → 加后缀
            n = 2
            while f"{preferred_key}_{n}" in self.styles:
                n += 1
            new_key = f"{preferred_key}_{n}"
            self.styles[new_key] = spec
            self._fingerprints[fp] = new_key
            return new_key

        # 序号策略:fingerprint 去重
        if fp in self._fingerprints:
            return self._fingerprints[fp]
        key = self._next_seq_key(kind)
        self.styles[key] = spec
        self._fingerprints[fp] = key
        return key

    # ---- fills ----

    def fill_solid(self, color_obj: dict) -> Optional[str]:
        hex_ = rgba_to_str(color_obj.get("value")) if color_obj else None
        if not hex_:
            return None
        return self._intern("fill", [hex_])

    def fill_gradient_linear(self, val: dict) -> Optional[str]:
        stops = val.get("colorStops", [])
        cs = ", ".join(
            f"{rgba_to_str(s.get('color'))} {int(round(s.get('position', 0) * 100))}%"
            for s in stops
        )
        fx, fy = val.get("fromX", 0), val.get("fromY", 0)
        tx, ty = val.get("toX", 0), val.get("toY", 1)
        # CSS gradient 角度:0deg 朝上,顺时针;Sketch from/to 是单位坐标(0~1,Y 向下)
        angle = (math.degrees(math.atan2(tx - fx, -(ty - fy))) + 360) % 360
        spec = [{
            "type": "GRADIENT_LINEAR",
            "gradient": f"linear-gradient({angle:.0f}deg, {cs})",
        }]
        return self._intern("fill", spec)

    def fill_gradient_radial(self, val: dict) -> Optional[str]:
        stops = val.get("colorStops", [])
        cs = ", ".join(
            f"{rgba_to_str(s.get('color'))} {int(round(s.get('position', 0) * 100))}%"
            for s in stops
        )
        spec = [{"type": "GRADIENT_RADIAL",
                 "gradient": f"radial-gradient(circle, {cs})"}]
        return self._intern("fill", spec)

    def fill_image(self, slice_url: str, scale_mode: str = "FILL") -> Optional[str]:
        h = url_hash(slice_url)
        if not h:
            return None
        spec = [{"type": "IMAGE", "imageRef": h, "scaleMode": scale_mode}]
        return self._intern("fill", spec)

    # ---- stroke ----

    def stroke(self, border: dict, dash: Optional[list] = None) -> Optional[str]:
        color = border.get("color")
        color_str = rgba_to_str(color.get("value") if isinstance(color, dict) else None)
        spec = compact({
            "width": border.get("strokeWidth"),
            "color": color_str,
            "position": border.get("type", "center"),
            "dash": list(dash) if dash else None,
        })
        return self._intern("stroke", spec) if spec else None

    # ---- effect (shadow) ----

    def shadow(self, s: dict) -> Optional[str]:
        color = (s.get("color") or {}).get("value")
        spec = compact({
            "type": s.get("type", "outside"),
            "offsetX": s.get("offsetX", 0),
            "offsetY": s.get("offsetY", 0),
            "blur": s.get("blur", 0),
            "spread": s.get("spread", 0),
            "color": rgba_to_str(color),
        })
        return self._intern("effect", spec) if spec else None

    # ---- layout ----

    def layout(self, bounds: dict, sizing_h: str = "fixed",
               sizing_v: str = "fixed") -> Optional[str]:
        if not bounds:
            return None
        spec = {
            "mode": "none",  # Mockplus 没 AutoLayout
            "sizing": {"horizontal": sizing_h, "vertical": sizing_v},
            "locationRelativeToParent": {
                "x": round_num(bounds.get("left")),
                "y": round_num(bounds.get("top")),
            },
            "dimensions": {
                "width": round_num(bounds.get("width")),
                "height": round_num(bounds.get("height")),
            },
        }
        return self._intern("layout", spec)

    # ---- textStyle(优先 sharedStyle.name) ----

    def text_style(self, st: dict,
                   preferred_name: Optional[str] = None) -> Optional[str]:
        font = st.get("font") or {}
        space = st.get("space") or {}
        fstyles = st.get("fontStyles") or {}
        color = (font.get("color") or {}).get("value")
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
            "fontWeight": font.get("weight"),
            "fontStyle": font.get("fontWeight", ""),  # 注:Mockplus fontWeight 是 "Semibold" 这类字符串
            "color": rgba_to_str(color),
            "lineHeight": space.get("lineHeight"),
            "letterSpacing": space.get("letterSpacing"),
            "textAlignHorizontal": (st.get("align", "") or "").upper() or None,
            "decoration": decoration,
        })
        if not spec:
            return None
        return self._intern("textStyle", spec, preferred_key=preferred_name)


def _fingerprint(spec) -> str:
    """递归把 dict/list 转可比较元组(对 dict 排序 key)。"""
    if isinstance(spec, dict):
        return repr(sorted((k, _fingerprint(v)) for k, v in spec.items()))
    if isinstance(spec, list):
        return repr([_fingerprint(x) for x in spec])
    return repr(spec)
```

- [ ] **Step 2: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/transform.py').read())"`
Expected: 无输出

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/scripts/transform.py
```

---

### Task 6: `transform.py` 实现节点提取

**Files:**
- Modify: `skills/mockplus-context/scripts/transform.py` (append)

**Reference:**
- v0.4 `_transform.py:218-363`(extract_node)
- 备份版 `to-yaml.py:301-445`(类似的节点 walker)

**v0.5 关键差异(对比 v0.4):**
- 节点上没有 `bounds` 字段,改为 `layout: layout_NNNNNN`(引用 TokenTable.layout)
- 节点上 `fills` 是单一引用(字符串),不是数组;`strokes` / `effects` 同理
- TEXT 节点:`text: "字符串"` 直接平铺,加 `textStyle: <key>`;v0.4 是 `text: {value, style}` 嵌套
- 切图节点(原 `asset`)改为给该节点的 `fills` 加一个 `IMAGE` fill,LLM 通过 `imageRef: <hash>` 调 download
- INSTANCE 节点:加 `componentId: <libraryName>/<containerSourceName>`
- 类型大写:`FRAME` / `TEXT` / `INSTANCE` / `RECTANGLE` / `ELLIPSE` / `VECTOR`(v0.4 是原样小写如 `group`/`text`)

**节点类型映射:**

| sketch realType | v0.5 type |
|---|---|
| `Artboard` | `FRAME` |
| `Group` | `FRAME` |
| `Text` | `TEXT` |
| `SymbolInstance` | `INSTANCE` |
| `Rectangle` / `ShapePath`(矩形特征) | `RECTANGLE` |
| `Oval` | `ELLIPSE` |
| `ShapePath`(其他) | `VECTOR` |
| 其他 | 原样大写,前缀 `_UNKNOWN_` |

- [ ] **Step 1: 在 `transform.py` 末尾追加节点提取逻辑**

```python
# ============================================================
# 节点提取
# ============================================================

# 节点上消费的顶层字段
LAYER_HANDLED = {
    "basic", "bounds", "fill", "stroke", "effect", "text", "slice",
    "sharedStyle", "children",
}
BASIC_HANDLED = {
    "id", "sourceID", "type", "realType", "name", "opacity",
    "libraryID", "libraryName", "imageID", "containerSourceName",
    "symbolId", "symbolMasterId",
}

REAL_TYPE_TO_V5 = {
    "Artboard": "FRAME",
    "Group": "FRAME",
    "Text": "TEXT",
    "SymbolInstance": "INSTANCE",
    "Rectangle": "RECTANGLE",
    "Oval": "ELLIPSE",
    "ShapePath": "VECTOR",  # 可能进一步细分,先按 VECTOR
}


class TransformContext:
    def __init__(self):
        self.bank = TokenTable()
        self.unhandled = set()
        self.warnings = []
        self.input_field_count = 0
        self.seen_symbol_ids = set()
        self.components = {}  # libId/path → {id, name, libraryName}

    def warn(self, msg: str):
        self.warnings.append(msg)


def _v5_type(real_type: str) -> str:
    return REAL_TYPE_TO_V5.get(real_type, f"_UNKNOWN_{real_type.upper()}")


def _border_radius_str(radius: List[int]) -> Optional[str]:
    """[8,8,8,8] → '8px';[8,0,8,0] → '8px 0 8px 0'。"""
    if not radius or not any(r > 0 for r in radius):
        return None
    rr = [round_num(r) for r in radius]
    if len(set(rr)) == 1:
        return f"{rr[0]}px"
    return " ".join(f"{r}px" if r else "0" for r in rr)


def extract_node(node: dict, ctx: TransformContext,
                 parent_path: List[str]) -> dict:
    basic = node.get("basic") or {}
    name = basic.get("name", "")
    real_type = basic.get("realType", "")
    opacity = basic.get("opacity", 1)
    bounds = node.get("bounds") or {}

    nid = basic.get("sourceID") or stable_id(name, bounds, parent_path)
    if not basic.get("sourceID"):
        ctx.warn(f"node {nid} 缺 sourceID,用 stable hash")

    out = {
        "id": nid,
        "name": name,
        "type": _v5_type(real_type),
    }

    # opacity < 1 才输出
    if isinstance(opacity, (int, float)) and opacity < 0.999:
        out["opacity"] = round(opacity, 2)

    # layout: 所有节点都有
    layout_key = ctx.bank.layout(bounds)
    if layout_key:
        out["layout"] = layout_key

    # INSTANCE:componentId + components 注册表
    lib_name = basic.get("libraryName", "")
    csn = basic.get("containerSourceName", "")
    sm_id = basic.get("symbolMasterId")
    if real_type == "SymbolInstance" and (lib_name or csn):
        comp_id = f"{lib_name}/{csn}" if lib_name else csn
        out["componentId"] = comp_id
        ctx.components.setdefault(comp_id, {
            "id": sm_id or basic.get("symbolId", ""),
            "name": csn,
            "libraryName": lib_name,
        })

    # TEXT
    text = node.get("text") or {}
    text_styles = text.get("styles") or []
    if text_styles:
        st = text_styles[0]
        if len(text_styles) > 1:
            ctx.warn(f"node {nid} 有 {len(text_styles)} 段 text.styles,仅取首段")
        # 优先用 sharedStyle.name(若有)
        shared = node.get("sharedStyle") or {}
        preferred = shared.get("name") if shared.get("type") == "text" else None
        ts_key = ctx.bank.text_style(st, preferred_name=preferred)
        if ts_key:
            out["textStyle"] = ts_key
        out["text"] = st.get("value", "")

    # fills: 单一引用(数组本身在 globalVars 里)
    # 切图节点:把 IMAGE fill 注入到 fills 数组里
    slice_ = node.get("slice")
    slice_image_fill = None
    if isinstance(slice_, dict):
        bitmap_url = slice_.get("bitmapURL")
        if bitmap_url:
            slice_image_fill = ctx.bank.fill_image(bitmap_url, scale_mode="FILL")

    fill = node.get("fill") or {}
    fill_colors = fill.get("colors") or []
    if fill_colors or slice_image_fill:
        # 取第一个 fill 作为节点引用(Mockplus 通常每节点单一 fill);多 fill 暂不支持
        primary = None
        for c in fill_colors:
            t = c.get("type", "normal")
            if t == "normal":
                k = ctx.bank.fill_solid(c)
            elif t == "linearGradient":
                v = c.get("value") or {}
                k = ctx.bank.fill_gradient_linear(v)
            elif t == "radialGradient":
                v = c.get("value") or {}
                k = ctx.bank.fill_gradient_radial(v)
            else:
                k = None
            if k:
                primary = k
                break
        if slice_image_fill:
            primary = slice_image_fill  # 切图覆盖普通 fill
        if primary:
            out["fills"] = primary

    # strokes
    stroke = node.get("stroke") or {}
    borders = stroke.get("borders") or []
    dash = stroke.get("dash") or []
    if borders:
        s_keys = [ctx.bank.stroke(b, dash=dash) for b in borders]
        s_keys = [k for k in s_keys if k]
        if s_keys:
            out["strokes"] = s_keys[0]  # 单一引用

    radius = stroke.get("radius")
    br = _border_radius_str(radius) if radius else None
    if br:
        out["borderRadius"] = br

    # effects (shadows)
    eff = node.get("effect") or {}
    shadows = eff.get("shadows") or []
    if shadows:
        e_keys = [ctx.bank.shadow(s) for s in shadows]
        e_keys = [k for k in e_keys if k]
        if e_keys:
            out["effects"] = e_keys[0]

    # unhandled 字段探针
    for k in node.keys():
        if k not in LAYER_HANDLED:
            ctx.unhandled.add(f"layer.{k}")
    for k in basic.keys():
        if k not in BASIC_HANDLED:
            ctx.unhandled.add(f"layer.basic.{k}")
    ctx.input_field_count += len(node) + len(basic)

    # 递归 children(容错降级:单 child 异常不影响其他)
    children = node.get("children") or []
    if children:
        safe_children = []
        for i, c in enumerate(children):
            try:
                safe_children.append(extract_node(c, ctx, parent_path + [name or real_type]))
            except Exception as e:
                safe_children.append({
                    "id": f"_err_{nid}_{i:03d}",
                    "type": "_ERROR",
                    "_error": str(e),
                })
                ctx.warn(f"node {nid} child[{i}] transform 失败: {e}")
        out["children"] = safe_children

    return compact(out)
```

- [ ] **Step 2: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/transform.py').read())"`
Expected: 无输出

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/scripts/transform.py
```

---

### Task 7: `transform.py` 顶层入口 + metadata + serialize

**Files:**
- Modify: `skills/mockplus-context/scripts/transform.py` (append)

**Reference:**
- v0.4 `_transform.py:367-441`(build_metadata + transform)
- spec §6 整体 YAML 形态

- [ ] **Step 1: 在 `transform.py` 末尾追加 metadata + 顶层 + 序列化**

```python
# ============================================================
# metadata
# ============================================================

def build_metadata(data: dict, page_meta: dict, app_id: str,
                   components: dict) -> dict:
    canvas = data.get("size") or {}
    md = {
        "name": page_meta.get("name", ""),
        "path": page_meta.get("path", ""),
        "pageId": page_meta["id"],
        "appId": app_id,
        "device": page_meta.get("device", "") or data.get("device", ""),
        "size": {
            "width": canvas.get("width"),
            "height": canvas.get("height"),
        },
        "backgroundColor": normalize_bg(data.get("backgroundColor", "")),
        "components": components or {},
    }
    return compact(md)


# ============================================================
# 顶层 transform
# ============================================================

def transform(data: dict, page_meta: dict, app_id: str) -> dict:
    """sketch JSON → v0.5 结构化 dict。可序列化为 YAML/JSON。"""
    ctx = TransformContext()
    layers = data.get("layers") or {}
    root_children = layers.get("children") or []
    nodes = []
    for i, c in enumerate(root_children):
        try:
            nodes.append(extract_node(c, ctx, []))
        except Exception as e:
            nodes.append({
                "id": f"_err_root_{i:03d}",
                "type": "_ERROR",
                "_error": str(e),
            })
            ctx.warn(f"root[{i}] transform 失败: {e}")

    return {
        "metadata": build_metadata(data, page_meta, app_id, ctx.components),
        "nodes": nodes,
        "globalVars": {
            "styles": ctx.bank.styles,
        },
        "_meta": {
            "transformVersion": TRANSFORM_VERSION,
            "sketchPluginVersion": data.get("pluginVersion", ""),
            "documentVersion": data.get("documentVersion", ""),
            "inputFieldsTotal": ctx.input_field_count,
            "unhandledFields": sorted(ctx.unhandled),
            "warnings": ctx.warnings,
        },
    }


# ============================================================
# 序列化(YAML / JSON)
# ============================================================

def serialize(result: dict, fmt: str = "yaml") -> str:
    if fmt == "json":
        import json
        return json.dumps(result, ensure_ascii=False, indent=2)
    if fmt == "yaml":
        import yaml
        # default_flow_style=False(块格式),但 size/dimensions 等小 dict 想要 flow 风格
        # 简单起见全部块格式,可读性已够
        return yaml.safe_dump(result, allow_unicode=True, sort_keys=False,
                              default_flow_style=False, width=200)
    raise ValueError(f"未知格式: {fmt}")


def compute_stats(result: dict) -> dict:
    """`mockplus data --stats` 输出统计。"""
    types_seen = {}

    def walk(n):
        types_seen[n.get("type", "?")] = types_seen.get(n.get("type", "?"), 0) + 1
        for c in n.get("children", []):
            walk(c)

    nodes_count = 0
    for n in result["nodes"]:
        walk(n)
        nodes_count += 1 + _descendant_count(n)

    asset_count = sum(
        1 for k, v in result["globalVars"]["styles"].items()
        if isinstance(v, list) and v and isinstance(v[0], dict)
        and v[0].get("type") == "IMAGE"
    )
    return {
        "nodes": nodes_count,
        "styles": len(result["globalVars"]["styles"]),
        "assetsImages": asset_count,
        "typesSeen": types_seen,
        "unhandledFields": result["_meta"]["unhandledFields"],
        "warnings": result["_meta"]["warnings"],
    }


def _descendant_count(node: dict) -> int:
    c = 0
    for ch in node.get("children", []):
        c += 1 + _descendant_count(ch)
    return c
```

- [ ] **Step 2: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/transform.py').read())"`
Expected: 无输出

- [ ] **Step 3: Smoke import + 装 PyYAML**

```bash
pip install --quiet PyYAML
python3 -c "
import sys; sys.path.insert(0, 'skills/mockplus-context/scripts')
import transform, client
t = transform.transform({'layers': {'children': []}}, {'id': 'p1', 'name': 't', 'path': ''}, 'app1')
print(transform.serialize(t, 'yaml')[:200])
"
```
Expected: 输出含 `metadata:`、`nodes: []`、`globalVars:` 的 YAML 片段

- [ ] **Step 4: 暂存**

```bash
git add skills/mockplus-context/scripts/transform.py
```

---

## C. CLI 层:`cli.py`

### Task 8: 建 `cli.py` + action_cookie

**Files:**
- Create: `skills/mockplus-context/scripts/cli.py`

**Reference:**
- v0.4 `_cookie.py:56-116`(cmd_cookie 实现)

- [ ] **Step 1: 写 `cli.py` + cookie action**

```python
"""cli.py - 各子命令的 action 实现。

调用约定:每个 action_<name>(args) 返回退出码 int。
- args 是 argparse.Namespace
- 标准输出走 stdout(用户/下游消费)
- 进度 / 错误走 stderr
"""
import json
import os
import sys
import time
from pathlib import Path
from typing import List

import client


# ============================================================
# cookie
# ============================================================

def action_cookie(args) -> int:
    sub = args.cookie_cmd

    if sub == "set":
        if getattr(args, "from_file", None):
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
        client.write_cookie(content)
        print(f"OK: cookie 已写入 {client.cookie_file_path()}", file=sys.stderr)
        return 0

    if sub == "test":
        return client.test_cookie_api(args.app_id)

    if sub == "status":
        s = client.cookie_status()
        if not s["exists"]:
            print(f"Status:  未配置(运行 `mockplus cookie set`)")
            print(f"Path:    {s['path']}")
            return 0
        print(f"Path:    {s['path']}")
        print(f"Mode:    {s['mode']}")
        if "set_at" in s:
            print(f"SetAt:   {time.ctime(s['set_at'])}")
        if "expires_at" in s:
            print(f"Expires: {time.ctime(s['expires_at'])} ({s['days_left']} 天后)")
        return 0

    if sub == "clear":
        fp = client.cookie_file_path()
        if fp.exists():
            fp.unlink()
            print(f"OK: 已删除 {fp}", file=sys.stderr)
        return 0

    if sub == "path":
        print(client.cookie_file_path())
        return 0

    return 2
```

- [ ] **Step 2: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/cli.py').read())"`
Expected: 无输出

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/scripts/cli.py
```

---

### Task 9: `cli.py` 实现 action_tree

**Files:**
- Modify: `skills/mockplus-context/scripts/cli.py` (append)

**Reference:**
- v0.4 `_tree.py`(整个文件 61 行)

- [ ] **Step 1: 在 `cli.py` 末尾追加 tree action**

```python
# ============================================================
# tree
# ============================================================

def _node_summary_json(node: dict) -> dict:
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


def action_tree(args) -> int:
    idx = client.fetch_index(args.app_id, refresh=args.refresh)

    if args.format == "json":
        out = [_node_summary_json(root) for root in idx["payload"]["pages"]]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # text 格式
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

    # 孤儿 page 警告
    pages, groups = client.flatten_pages(idx)
    group_ids = {g["id"] for g in groups}
    for p in pages:
        parent = p.get("parentID", "")
        if parent and parent not in group_ids:
            print(f"⚠️  孤儿 page {p['id']} (parentID={parent} 不在树里): {p['name']}",
                  file=sys.stderr)
    return 0
```

- [ ] **Step 2: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/cli.py').read())"`
Expected: 无输出

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/scripts/cli.py
```

---

### Task 10: `cli.py` 实现 action_data

**Files:**
- Modify: `skills/mockplus-context/scripts/cli.py` (append)

**Reference:**
- v0.4 `_api.py:155-195`(cmd_get_data 流程)
- v0.4 `_api.py:198-240`(cmd_inspect 统计逻辑——合并到 --stats)
- spec §5.1 数据流:解析 URL → 查 kind → fetch index/page → transform → serialize/stats

- [ ] **Step 1: 在 `cli.py` 末尾追加 data action**

```python
# ============================================================
# data
# ============================================================

import transform as _transform


def action_data(args) -> int:
    app_id, target_id = client.parse_url_or_short(args.url)
    kind = client.resolve_target_kind(app_id, target_id, refresh=args.refresh)
    if kind == "group":
        print(f"ERR: URL 指向 group,先用 `mockplus tree {app_id}` 浏览找到具体 page id",
              file=sys.stderr)
        return 22
    if kind != "page":
        print(f"ERR: TARGET_ID={target_id} 不是 page(kind={kind})", file=sys.stderr)
        return 22

    idx = client.fetch_index(app_id, refresh=args.refresh)
    pages, _ = client.flatten_pages(idx)
    page_meta = next(p for p in pages if p["id"] == target_id)

    data = client.get_page_data_cached(app_id, page_meta, refresh=args.refresh)
    result = _transform.transform(data, page_meta, app_id)

    # 校验:断言关键字段(替代砍掉的 _schema.py)
    try:
        assert "metadata" in result and result["metadata"].get("pageId"), "metadata.pageId 缺失"
        assert isinstance(result["nodes"], list), "nodes 不是 list"
        assert isinstance(result["globalVars"]["styles"], dict), "globalVars.styles 不是 dict"
    except AssertionError as e:
        print(f"ERR: transform 输出校验失败: {e}", file=sys.stderr)
        return 2

    # 输出
    out_text = _transform.serialize(result, fmt=args.format)
    if args.out and args.out != "-":
        Path(args.out).write_text(out_text)
        print(f"OK: 写入 {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(out_text)
        if not out_text.endswith("\n"):
            sys.stdout.write("\n")

    # --stats:额外输出统计到 stderr
    if args.stats:
        stats = _transform.compute_stats(result)
        print("---- stats ----", file=sys.stderr)
        print(json.dumps(stats, ensure_ascii=False, indent=2), file=sys.stderr)
    return 0
```

- [ ] **Step 2: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/cli.py').read())"`
Expected: 无输出

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/scripts/cli.py
```

---

### Task 11: `cli.py` 实现 action_download

**Files:**
- Modify: `skills/mockplus-context/scripts/cli.py` (append)

**Reference:**
- 备份版 `mockplus.sh:211-291`(action_download 流程)
- Task 3 在 client.py 加的 `extract_slices` / `download_slices` / `download_page_image`

- [ ] **Step 1: 在 `cli.py` 末尾追加 download action**

```python
# ============================================================
# download
# ============================================================

def action_download(args) -> int:
    app_id, target_id = client.parse_url_or_short(args.url)
    kind = client.resolve_target_kind(app_id, target_id, refresh=False)
    if kind != "page":
        print(f"ERR: TARGET_ID={target_id} 不是 page(kind={kind})", file=sys.stderr)
        return 22

    idx = client.fetch_index(app_id, refresh=False)
    pages, _ = client.flatten_pages(idx)
    page_meta = next(p for p in pages if p["id"] == target_id)
    data = client.get_page_data_cached(app_id, page_meta, refresh=False)

    # 解析 --nodes
    wanted = None
    if args.nodes and args.nodes != "all":
        wanted = set(args.nodes.split(","))

    slices = client.extract_slices(data, wanted=wanted)
    out_dir = Path(args.out) if args.out else Path(f"./mockplus-assets/{target_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 写 manifest
    manifest_fp = out_dir / "assets-manifest.json"
    manifest_fp.write_text(json.dumps({"slices": slices},
                                       ensure_ascii=False, indent=2))
    print(f"目标切图: {len(slices)} 个 → {out_dir}", file=sys.stderr)

    stats = client.download_slices(slices, out_dir)
    print(f"OK: 下载 {stats['ok']} (cached={stats['cached']}, "
          f"fail={stats['fail']}, total_files={stats['total']})",
          file=sys.stderr)

    if args.include_design:
        design_fp = out_dir / "design.png"
        if client.download_page_image(page_meta, design_fp):
            print(f"OK: design.png → {design_fp}", file=sys.stderr)
        else:
            print(f"WARN: 无 page imageURL,跳过 design.png", file=sys.stderr)

    return 0
```

- [ ] **Step 2: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/cli.py').read())"`
Expected: 无输出

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/scripts/cli.py
```

---

### Task 12: `cli.py` 实现 action_all

**Files:**
- Modify: `skills/mockplus-context/scripts/cli.py` (append)

**Reference:**
- 备份版 `mockplus.sh:315-338`(action_all)
- spec §5.3 产物结构:`data.yaml` + `design.png` + `assets/<hash>.{png,svg}`

- [ ] **Step 1: 在 `cli.py` 末尾追加 all action**

```python
# ============================================================
# all
# ============================================================

import argparse as _argparse


def action_all(args) -> int:
    app_id, target_id = client.parse_url_or_short(args.url)
    out_root = Path(args.out_dir) if args.out_dir else \
        Path(f"./mockplus-cache/{app_id}/{target_id}")
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"[mockplus all] APP_ID={app_id}  PAGE_ID={target_id}  out={out_root}",
          file=sys.stderr)

    # 1) data → data.yaml
    data_ns = _argparse.Namespace(
        url=args.url, out=str(out_root / "data.yaml"),
        format="yaml", stats=False, refresh=False,
    )
    rc = action_data(data_ns)
    if rc != 0:
        return rc

    # 2) download → assets/ + design.png
    assets_dir = out_root / "assets"
    download_ns = _argparse.Namespace(
        url=args.url, out=str(assets_dir),
        nodes="all", include_design=False, png_scale=2,
    )
    rc = action_download(download_ns)
    if rc != 0:
        return rc

    # 3) design.png 单独放外层(spec §5.3)
    kind = client.resolve_target_kind(app_id, target_id, refresh=False)
    if kind == "page":
        idx = client.fetch_index(app_id, refresh=False)
        pages, _ = client.flatten_pages(idx)
        page_meta = next(p for p in pages if p["id"] == target_id)
        design_fp = out_root / "design.png"
        if client.download_page_image(page_meta, design_fp):
            print(f"OK: design.png → {design_fp}", file=sys.stderr)

    print(f"\n==== 完成 ====", file=sys.stderr)
    print(f"页目录:     {out_root}", file=sys.stderr)
    print(f"data.yaml:  {out_root}/data.yaml", file=sys.stderr)
    print(f"design.png: {out_root}/design.png", file=sys.stderr)
    print(f"assets:     {assets_dir}/  ({len(list(assets_dir.glob('*.png')) + list(assets_dir.glob('*.svg')))} 个文件)",
          file=sys.stderr)
    return 0
```

- [ ] **Step 2: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/cli.py').read())"`
Expected: 无输出

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/scripts/cli.py
```

---

## D. 入口:`mockplus.py`

### Task 13: 重写 `mockplus.py`(argparse + dispatch)

**Files:**
- Modify: `skills/mockplus-context/scripts/mockplus.py` (整文件重写)

**Reference:**
- v0.4 `mockplus.py`(73 行,argparse 结构相同,只是子命令名换了)
- spec §5 CLI 接口契约

- [ ] **Step 1: 整文件重写 `mockplus.py`**

```python
#!/usr/bin/env python3
"""mockplus-context skill 主入口(v0.5.0)。
   子命令: data / download / all / tree / cookie
"""
import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mockplus",
        description="Mockplus 设计稿 → YAML/JSON + 切图(v0.5.0)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # data
    g = sub.add_parser("data", help="拉单页结构化 YAML/JSON")
    g.add_argument("url", help="完整 URL 或 <APP_ID>:<PAGE_ID>")
    g.add_argument("--out", default="-", help="输出路径(默认 stdout)")
    g.add_argument("--format", choices=["yaml", "json"], default="yaml")
    g.add_argument("--stats", action="store_true", help="额外打印统计到 stderr")
    g.add_argument("--refresh", action="store_true", help="跳过 cache 重拉")

    # download
    g = sub.add_parser("download", help="按 --nodes 下载切图")
    g.add_argument("url")
    g.add_argument("--nodes", default="all",
                   help="all 或 hash1,hash2(对应 YAML 里 imageRef)")
    g.add_argument("--out", help="输出目录(默认 ./mockplus-assets/<PAGE_ID>/)")
    g.add_argument("--include-design", action="store_true",
                   help="同时下整页截图 design.png")
    g.add_argument("--png-scale", type=int, default=2, choices=[1, 2],
                   help="(保留参数,目前固定 @2x)")

    # all
    g = sub.add_parser("all", help="一站式 = data + download(all + design)")
    g.add_argument("url")
    g.add_argument("out_dir", nargs="?", default=None,
                   help="输出目录(默认 ./mockplus-cache/<APP>/<PAGE>/)")

    # tree
    g = sub.add_parser("tree", help="树形打印项目结构(找 page id)")
    g.add_argument("app_id")
    g.add_argument("--format", choices=["text", "json"], default="text")
    g.add_argument("--refresh", action="store_true")

    # cookie
    g = sub.add_parser("cookie", help="Cookie 管理")
    csub = g.add_subparsers(dest="cookie_cmd", required=True)
    cset = csub.add_parser("set")
    cset.add_argument("--from-file", help="从文件读 cookie(默认 stdin)")
    ctest = csub.add_parser("test")
    ctest.add_argument("app_id")
    csub.add_parser("status")
    csub.add_parser("clear")
    csub.add_parser("path")

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # 延迟 import,避免没装 PyYAML 时也能跑 cookie/tree
    import cli

    if args.cmd == "cookie":
        return cli.action_cookie(args)
    if args.cmd == "tree":
        return cli.action_tree(args)
    if args.cmd == "data":
        return cli.action_data(args)
    if args.cmd == "download":
        return cli.action_download(args)
    if args.cmd == "all":
        return cli.action_all(args)

    print(f"未知子命令: {args.cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
```

- [ ] **Step 2: 语法检查 + dispatch smoke**

Run:
```bash
python3 -c "import ast; ast.parse(open('skills/mockplus-context/scripts/mockplus.py').read())"
python3 skills/mockplus-context/scripts/mockplus.py --help
python3 skills/mockplus-context/scripts/mockplus.py cookie --help
python3 skills/mockplus-context/scripts/mockplus.py cookie path
```
Expected:
- 第 1 条:无输出
- 第 2 条:打印 `usage:` 含 `{data,download,all,tree,cookie}`
- 第 3 条:打印 `usage:` 含 `{set,test,status,clear,path}`
- 第 4 条:打印 `~/.config/mockplus/cookie` 路径

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/scripts/mockplus.py
```

---

## E. 清理 v0.4 残留

### Task 14: 删 v0.4 老模块文件

**Files:**
- Delete: `skills/mockplus-context/scripts/_api.py`
- Delete: `skills/mockplus-context/scripts/_cookie.py`
- Delete: `skills/mockplus-context/scripts/_assets.py`
- Delete: `skills/mockplus-context/scripts/_transform.py`
- Delete: `skills/mockplus-context/scripts/_tree.py`
- Delete: `skills/mockplus-context/scripts/_schema.py`
- Delete: `skills/mockplus-context/scripts/_explore.py`
- Delete: `skills/mockplus-context/scripts/__init__.py`

**注意:**Task 17-19 测试改造在用新模块前会失败。本任务**必须在 Task 17-19 之后**才执行,或在删除之前先确认测试已改完。

**推荐顺序:**Task 15-21 全部完成后,跑一次 pytest(Task 29 的前置),再做 Task 14。

- [ ] **Step 1: 删除 v0.4 模块**

```bash
git rm skills/mockplus-context/scripts/_api.py
git rm skills/mockplus-context/scripts/_cookie.py
git rm skills/mockplus-context/scripts/_assets.py
git rm skills/mockplus-context/scripts/_transform.py
git rm skills/mockplus-context/scripts/_tree.py
git rm skills/mockplus-context/scripts/_schema.py
git rm skills/mockplus-context/scripts/_explore.py
git rm skills/mockplus-context/scripts/__init__.py
```

- [ ] **Step 2: 确认仅剩 v0.5 模块**

Run: `ls skills/mockplus-context/scripts/`
Expected: `mockplus.py  cli.py  transform.py  client.py`

- [ ] **Step 3: 暂存**

`git rm` 已暂存,无需额外 `git add`。

---

## F. 测试改造

### Task 15: 更新 tests/requirements.txt

**Files:**
- Modify: `tests/requirements.txt`

- [ ] **Step 1: 读现状**

Run: `cat tests/requirements.txt`

- [ ] **Step 2: 改为(覆盖写入)**

```
pytest>=7
PyYAML>=6
```

- [ ] **Step 3: 安装**

```bash
pip install -r tests/requirements.txt
```
Expected: PyYAML 安装成功(若已装会显示 "Requirement already satisfied")

- [ ] **Step 4: 暂存**

```bash
git add tests/requirements.txt
```

---

### Task 16: 重生 fixtures/expected/*.yaml

**Files:**
- Delete: `tests/fixtures/expected/simple-text.json`
- Delete: `tests/fixtures/expected/nested-groups.json`
- Delete: `tests/fixtures/expected/with-slices.json`
- Delete: `tests/fixtures/expected/with-shared-styles.json`
- Delete: `tests/fixtures/expected/with-gradients.json`
- Create: `tests/fixtures/expected/simple-text.yaml`
- Create: `tests/fixtures/expected/nested-groups.yaml`
- Create: `tests/fixtures/expected/with-slices.yaml`
- Create: `tests/fixtures/expected/with-shared-styles.yaml`
- Create: `tests/fixtures/expected/with-gradients.yaml`

**策略:**先跑一次新 transform 生成 YAML(首次生成 = "黄金值"),然后人工 review 输出符合 spec §6 规范后写入 expected。test_transform.py(Task 17)会有 "首次生成模式"——若 expected 不存在,自动写入并 fail,提示人工 review。

- [ ] **Step 1: 删旧 JSON expected**

```bash
git rm tests/fixtures/expected/*.json
```

- [ ] **Step 2: 跑一次 transform 生成新 YAML(先不 commit)**

```bash
python3 - <<'PY'
import json, sys, yaml
sys.path.insert(0, 'skills/mockplus-context/scripts')
import transform
FIXTURES = 'tests/fixtures'
EXPECTED = 'tests/fixtures/expected'
FAKE_PAGE_META = {"id": "p-test", "name": "test", "path": "test",
                  "device": "ios1x", "imageURL": "", "updatedAt": ""}
for name in ["simple-text", "nested-groups", "with-slices",
             "with-shared-styles", "with-gradients"]:
    data = json.load(open(f"{FIXTURES}/{name}.json"))
    actual = transform.transform(data, FAKE_PAGE_META, "test-app")
    out = transform.serialize(actual, fmt="yaml")
    open(f"{EXPECTED}/{name}.yaml", "w").write(out)
    print(f"WROTE {EXPECTED}/{name}.yaml ({len(out)} bytes)")
PY
```
Expected: 5 个 `WROTE` 行

- [ ] **Step 3: 人工 review 5 份 YAML**

打开每份 `tests/fixtures/expected/*.yaml`,逐项核对:
- `metadata` 含 name/pageId/appId/device/size/backgroundColor
- `nodes` 是数组,每个 node 含 id/name/type(大写如 FRAME/TEXT),含 `layout`(引用 globalVars.styles.layout_NNNNNN)
- TEXT 节点含 `text: "..."` + `textStyle: <key>`,key 优先用 sharedStyle.name(若 fixture 里有 shared)
- 切图节点的 fills 引用一个 IMAGE fill(含 imageRef)
- `globalVars.styles` 中 fill/layout/stroke/effect 用 6 位序号
- `_meta.unhandledFields` 应为 `[]`(若不为空 → 说明 transform 还有字段没消费,先修 transform.py 再回来重生)

若有问题:回去修 `transform.py` → 重跑 step 2 → 再 review。

- [ ] **Step 4: 暂存**

```bash
git add tests/fixtures/expected/
```

---

### Task 17: 改 test_transform.py(YAML + 新 import)

**Files:**
- Modify: `tests/test_transform.py` (整文件重写)

**Reference:**
- 当前实现:`tests/test_transform.py`(53 行)
- v0.5 差异:用 yaml.safe_load 加载 expected;import 路径 `_transform` → `transform`;断言 `_meta.unhandledFields == []`

- [ ] **Step 1: 整文件重写**

```python
"""transform 黄金对照测试。v0.5:YAML expected。"""
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "skills" / "mockplus-context" / "scripts"))
import transform


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
    actual = transform.transform(data, FAKE_PAGE_META, "test-app")
    expected_fp = EXPECTED / f"{name}.yaml"
    if not expected_fp.exists():
        # 首次跑:写黄金值供 review,测试失败强制人工 review
        expected_fp.parent.mkdir(exist_ok=True)
        expected_fp.write_text(transform.serialize(actual, fmt="yaml"))
        pytest.fail(f"首次生成 {expected_fp},请 review 后重跑")
    expected = yaml.safe_load(open(expected_fp))
    assert actual == expected, f"transform 输出与 {expected_fp} 不一致"


def test_transform_tolerates_missing_basic():
    """容错降级:节点缺 basic 不应 crash。"""
    bad_data = {
        "layers": {"children": [
            {"bounds": {"left": 0, "top": 0, "width": 100, "height": 50}}
        ]},
        "size": {"width": 375, "height": 812},
    }
    out = transform.transform(bad_data, FAKE_PAGE_META, "test-app")
    assert len(out["nodes"]) == 1


def test_transform_unhandled_fields_clean_on_fixtures():
    """所有 fixtures 都应该不产生 unhandledFields(确保 LAYER_HANDLED/BASIC_HANDLED 完整)。"""
    for name in ["simple-text", "nested-groups", "with-slices",
                 "with-shared-styles", "with-gradients"]:
        data = json.load(open(FIXTURES / f"{name}.json"))
        out = transform.transform(data, FAKE_PAGE_META, "test-app")
        assert out["_meta"]["unhandledFields"] == [], \
            f"{name} 产生 unhandledFields: {out['_meta']['unhandledFields']}"
```

- [ ] **Step 2: 跑这个测试文件**

Run: `pytest tests/test_transform.py -v`
Expected: 7 passed(5 个 parametrize + 2 个独立)

- [ ] **Step 3: 暂存**

```bash
git add tests/test_transform.py
```

---

### Task 18: 改 test_assets.py(适配 client 模块 + --nodes 接口)

**Files:**
- Modify: `tests/test_assets.py` (整文件重写)

**说明:**v0.4 测试针对的 `_assets.py` 的 `--downloads` JSON 接口已经废除。v0.5 download 是 `--nodes hash,...`,语义是"从 cache 的 data.json 里查 hash 对应的 URL 再下"。所以原来的 host 校验测试已经无意义——v0.5 不再让用户传 URL。

测试改造方向:
- 删 host/format 校验类测试(`test_invalid_host_rejected` 等)——这套校验已不存在
- 保留下载基础设施测试(本地 http server + cached 跳过)——测 `client.download_slices`

- [ ] **Step 1: 整文件重写**

```python
"""client.download_slices 测试。用本地 http.server 起一个临时 PNG。"""
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "skills" / "mockplus-context" / "scripts"))
import client


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


def test_download_via_local_server(tmp_path):
    server = _serve()
    port = server.server_address[1]
    slices = [
        {"hash": "abc123",
         "bitmapURL": f"http://127.0.0.1:{port}/abc123.png",
         "svgURL": ""},
        {"hash": "def456",
         "bitmapURL": f"http://127.0.0.1:{port}/def456.png",
         "svgURL": ""},
    ]
    stats = client.download_slices(slices, tmp_path)
    server.shutdown()
    assert stats["ok"] == 2 and stats["fail"] == 0
    assert (tmp_path / "abc123.png").exists()
    assert (tmp_path / "def456.png").exists()


def test_download_skip_cached(tmp_path):
    server = _serve()
    port = server.server_address[1]
    (tmp_path / "abc.png").write_bytes(b"existing")
    slices = [{"hash": "abc",
               "bitmapURL": f"http://127.0.0.1:{port}/abc.png",
               "svgURL": ""}]
    stats = client.download_slices(slices, tmp_path)
    server.shutdown()
    assert stats["cached"] == 1
    assert (tmp_path / "abc.png").read_bytes() == b"existing"


def test_extract_slices_all():
    data = {
        "layers": {"children": [
            {"basic": {"name": "icon-a"}, "bounds": {"width": 24, "height": 24},
             "slice": {"bitmapURL": "https://img02.mockplus.cn/idoc/sketch/h1/x.png",
                       "svgURL": "https://img02.mockplus.cn/idoc/sketch/h1/x.svg"}},
            {"basic": {"name": "no-slice"}, "bounds": {"width": 100, "height": 50}},
        ]}
    }
    slices = client.extract_slices(data)
    assert len(slices) == 1
    assert slices[0]["hash"] == "h1"


def test_extract_slices_filter_by_hash():
    data = {
        "layers": {"children": [
            {"basic": {"sourceID": "s1"},
             "slice": {"bitmapURL": "https://img02.mockplus.cn/idoc/sketch/h1/a.png"}},
            {"basic": {"sourceID": "s2"},
             "slice": {"bitmapURL": "https://img02.mockplus.cn/idoc/sketch/h2/b.png"}},
        ]}
    }
    s = client.extract_slices(data, wanted={"h1"})
    assert len(s) == 1 and s[0]["hash"] == "h1"
```

- [ ] **Step 2: 跑这个测试文件**

Run: `pytest tests/test_assets.py -v`
Expected: 4 passed

- [ ] **Step 3: 暂存**

```bash
git add tests/test_assets.py
```

---

### Task 19: 改 test_tree.py(适配 cli 模块)

**Files:**
- Modify: `tests/test_tree.py` (改 import)

**Reference:**
- 当前 import:`from _tree import cmd_tree, _node_summary_json` 之类
- v0.5:`_tree.py` 砍了,逻辑搬进 `cli.py`,改 import:`from cli import action_tree, _node_summary_json`

- [ ] **Step 1: 读当前文件**

Run: `cat tests/test_tree.py`

- [ ] **Step 2: 改 import 段**

替换:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "mockplus-context" / "scripts"))
from _tree import cmd_tree, _node_summary_json
```
为:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "mockplus-context" / "scripts"))
import cli
from cli import _node_summary_json
```

并把测试里 `cmd_tree(args)` 改为 `cli.action_tree(args)`。

- [ ] **Step 3: 跑测试**

Run: `pytest tests/test_tree.py -v`
Expected: 全 pass

- [ ] **Step 4: 暂存**

```bash
git add tests/test_tree.py
```

---

### Task 20: 删 test_schema.py

**Files:**
- Delete: `tests/test_schema.py`

- [ ] **Step 1: 删除**

```bash
git rm tests/test_schema.py
```

---

### Task 21: 加 test_token_naming.py

**Files:**
- Create: `tests/test_token_naming.py`

这个任务**显式要求 TDD**(spec §7.3 列为新增测试),用 TDD 模板。

- [ ] **Step 1: 写失败的测试**

```python
"""TokenTable 命名策略测试(spec §6.1)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "skills" / "mockplus-context" / "scripts"))
import transform as T


def test_fill_uses_6_digit_seq():
    tt = T.TokenTable()
    k = tt.fill_solid({"value": {"r": 255, "g": 0, "b": 0, "a": 1}})
    assert k == "fill_000001"


def test_textstyle_uses_shared_style_name():
    tt = T.TokenTable()
    spec = {"font": {"size": 16, "color": {"value": {"r": 0, "g": 0, "b": 0, "a": 1}}}}
    k = tt.text_style(spec, preferred_name="01文字色1/16px/semibold/居中对齐 Style")
    assert k == "01文字色1/16px/semibold/居中对齐 Style"


def test_textstyle_falls_back_to_seq_when_no_shared():
    tt = T.TokenTable()
    spec = {"font": {"size": 16, "color": {"value": {"r": 0, "g": 0, "b": 0, "a": 1}}}}
    k = tt.text_style(spec)
    assert k == "textStyle_000001"


def test_textstyle_same_name_same_spec_reuses_key():
    tt = T.TokenTable()
    spec = {"font": {"size": 16, "color": {"value": {"r": 0, "g": 0, "b": 0, "a": 1}}}}
    k1 = tt.text_style(spec, preferred_name="MyStyle")
    k2 = tt.text_style(spec, preferred_name="MyStyle")
    assert k1 == k2 == "MyStyle"


def test_textstyle_same_name_diff_spec_adds_suffix():
    """两个 sharedStyle 同名但 spec 不同 → 后到的加 _2。"""
    tt = T.TokenTable()
    spec1 = {"font": {"size": 16, "color": {"value": {"r": 0, "g": 0, "b": 0, "a": 1}}}}
    spec2 = {"font": {"size": 18, "color": {"value": {"r": 0, "g": 0, "b": 0, "a": 1}}}}
    k1 = tt.text_style(spec1, preferred_name="MyStyle")
    k2 = tt.text_style(spec2, preferred_name="MyStyle")
    assert k1 == "MyStyle"
    assert k2 == "MyStyle_2"


def test_fill_dedup_by_fingerprint():
    """两个相同 fill 应该返回同一个 key。"""
    tt = T.TokenTable()
    c = {"value": {"r": 255, "g": 0, "b": 0, "a": 1}}
    assert tt.fill_solid(c) == tt.fill_solid(c) == "fill_000001"


def test_layout_basic():
    tt = T.TokenTable()
    k = tt.layout({"left": 10, "top": 20, "width": 100, "height": 50})
    assert k == "layout_000001"
    assert tt.styles[k] == {
        "mode": "none",
        "sizing": {"horizontal": "fixed", "vertical": "fixed"},
        "locationRelativeToParent": {"x": 10, "y": 20},
        "dimensions": {"width": 100, "height": 50},
    }
```

- [ ] **Step 2: 运行测试看是否通过(实现在 Task 5 已完成)**

Run: `pytest tests/test_token_naming.py -v`
Expected: 7 passed(Task 5 的 TokenTable 实现应该已经满足这些断言;若 fail 说明 Task 5 有 bug,回去修)

- [ ] **Step 3: 暂存**

```bash
git add tests/test_token_naming.py
```

---

## G. 文档

### Task 22: 重写 SKILL.md

**Files:**
- Modify: `skills/mockplus-context/SKILL.md` (整文件重写)

**Reference:**
- 备份版 `~/.claude/backups/mockplus-context.backup.20260523-183712/SKILL.md`(210 行,作为风格参考)
- spec §8.7

**目标长度:**~130 行

- [ ] **Step 1: 整文件重写**

```markdown
---
name: mockplus-context
description: 从 Mockplus(摹客 app.mockplus.cn)设计稿抓取**结构化 YAML + 切图**。**触发场景**:用户给出 Mockplus develop URL(形如 `https://app.mockplus.cn/app/<APPID>/develop/design/<PAGEID>`)、要求"读 Mockplus 设计稿"、"按 Mockplus 还原 UI"、"导出 Mockplus 切图"、把 Mockplus 页面转 Vue/Flutter/小程序。LLM 拿到 YAML(metadata + nodes + globalVars.styles)可直接生成代码,无需解析 sketch 原始 JSON,比让 LLM 看 PNG 截图精度高一个数量级。
---

# Mockplus Context (v0.5.0)

把 Mockplus develop URL 转换为**结构化 YAML**,LLM 直接消费。

启动时声明:**"Using mockplus-context to extract <PAGE_ID> from Mockplus."**

## 何时触发

- 用户给的输入是 `https://app.mockplus.cn/app/<APPID>/develop/design/<TARGET_ID>` 形式的 URL
- 用户要"读 Mockplus 设计稿"、"按 Mockplus 还原 UI"、"导出 Mockplus 切图"
- 任何后续要基于 Mockplus 数据生成代码(Vue / React / Flutter / 小程序)的前置步骤

**不触发:**
- 输入是 Figma URL(用 `figma-context` MCP)
- 输入只是一张孤立 PNG(让用户先找到对应 Mockplus 页面 URL)

## 前置条件(用户一次性配置 cookie)

```bash
python3 skills/mockplus-context/scripts/mockplus.py cookie set
# 浏览器(已登录 mockplus.cn)F12 → Application → Cookies → app.mockplus.cn
# 把全部 cookie 拼成一行粘贴,回车结束
```

Cookie 默认存到 `~/.config/mockplus/cookie`,有效期约 30 天。401 时让用户 `cookie set` 重配。

## LLM 工作流(收到 URL 时按这个顺序)

1. **检查 cookie**:`mockplus cookie status`,未配置则引导用户 `cookie set`
2. **若 URL 不确定是 page**(指向 group / 只有 APP_ID):`mockplus tree <APP_ID>` 浏览,从树里挑出具体 page id
3. **拿 YAML 数据**:`mockplus data <URL> --out page.yaml`(默认 YAML)
4. **扫 YAML 找切图**:看 `globalVars.styles` 里 `type: IMAGE` 的 fill,收集 `imageRef: <hash>`
5. **按需下切图**:`mockplus download <URL> --nodes <hash1>,<hash2> --out ./assets`
6. **进入下游**(代码生成 / 对照还原等)

要视觉对照?加 `--include-design` 或直接 `mockplus all <URL>` 一站式拿齐。

## 命令速查

```bash
mockplus data <URL> [--out PATH] [--format yaml|json] [--stats] [--refresh]
mockplus download <URL> [--nodes all|h1,h2] [--out DIR] [--include-design]
mockplus all <URL> [<OUT_DIR>]              # = data + download(all + design)
mockplus tree <APP_ID> [--format text|json] [--refresh]
mockplus cookie {set|test|status|clear|path}
```

> Mockplus API 物理约束:只能按**整页(page)** 拉数据。Group/sub-group 没有节点级 API,所以 `data` 只接受 page URL,group 浏览靠 `tree`。

## 输出 YAML 速览(`data` 产物)

```yaml
metadata:
  name: 采购申请单列表（老板）
  pageId: -hKyUPiOs
  device: ios1x
  size: { width: 375, height: 812 }
  backgroundColor: '#f5f5f5ff'
  components:                          # SymbolInstance 反推
    <libId>/<path>: { id, name, libraryName }

nodes:
  - id: <UUID>
    name: 合并转采购
    type: TEXT                         # FRAME/TEXT/INSTANCE/RECTANGLE/ELLIPSE/VECTOR
    layout: layout_000007              # 引用 globalVars.styles
    fills: fill_000001                 # 可选
    text: "合并转采购"
    textStyle: 01文字色1/16px/semibold/居中对齐 Style   # 设计师命名
    children: [...]

globalVars:
  styles:
    fill_000003:                       # 切图填充
      - type: IMAGE
        imageRef: 2b417ea8...          # ← LLM 拿这个调 download
        scaleMode: FILL
    layout_000007:
      mode: none
      locationRelativeToParent: { x: 266, y: 737 }
      dimensions: { width: 80, height: 22 }
    01文字色1/16px/semibold/居中对齐 Style:
      fontFamily: PingFang SC
      fontWeight: 600
      fontSize: 16

_meta:
  unhandledFields: []                  # Mockplus schema 升级时这里会列字段
```

**关键设计:**
- Token 复用:相同 fill/layout/effect 自动去重,节点上只放引用
- 文字样式 key 用设计师命名(`sharedStyle.name`),保留语义
- 切图节点 fills 数组里写 `IMAGE` fill,LLM 拿 `imageRef` 调 download

## 常见失败

| 现象 | 处理 |
|---|---|
| `cookie 未配置` (exit 10) | `mockplus cookie set` |
| `API code != 0` (exit 21) | cookie 过期 → `mockplus cookie set` 重配 |
| `URL 指向 group,先用 tree 浏览` (exit 22) | URL 不是 page,先 `tree` 找正确 page id |
| `_meta.unhandledFields` 非空 | Mockplus schema 升级了,反馈 issue |
| 切图下载失败 | CDN 临时不通,重跑 `download`(已存在的会跳过) |
| 中国境外节点超时 | `img02.mockplus.cn` 是华东 CDN,境外节点请挂回国代理 |

## Cache 与隐私

- 中间产物:`~/.cache/mockplus/<APP_ID>/`(可被 `MOCKPLUS_CACHE_DIR` 覆盖)
- cookie 只读,不上传;`~/.config/mockplus/cookie` 自动 `chmod 600`
- 用户切图产物在用户指定目录,不污染 git 仓库

## 进阶参考

- `references/examples.md` — 端到端调用样例
- `references/troubleshooting.md` — 完整错误码 + 诊断
```

- [ ] **Step 2: 行数检查**

Run: `wc -l skills/mockplus-context/SKILL.md`
Expected: 100-140 行

- [ ] **Step 3: 暂存**

```bash
git add skills/mockplus-context/SKILL.md
```

---

### Task 23: 重写 README.md

**Files:**
- Modify: `README.md` (整文件重写)

**Reference:**
- 当前 `README.md`(v0.4)
- spec §8.1
- 备份版 `README.md`(作为内容样板)

- [ ] **Step 1: 读现状,保留 badges 段**

Run: `head -10 README.md`(记下 badges 那 5 行,Task Step 2 要复用)

- [ ] **Step 2: 整文件重写**

```markdown
# mockplus-context

[![CI](https://github.com/MySwallow/mockplus-context/actions/workflows/ci.yml/badge.svg)](https://github.com/MySwallow/mockplus-context/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

> 从 Mockplus(摹客)设计稿抓取**结构化 YAML + 切图**。Python 实现,YAML 优先,按需下载。

供 Claude / Cursor 等 LLM 直接消费。粘贴一个 Mockplus develop URL,LLM 就能拿到分层 YAML(`metadata` + `nodes` + `globalVars.styles`),按需下载切图,然后还原 UI 代码。

## 精度对比

| 方式 | 精度 | 速度 |
|---|---|---|
| 让 LLM 看 PNG 截图猜 spec | 估算,常有 ±5px 误差,字号/字重靠猜 | 慢 |
| 用这个 skill | **从 Sketch 导出的原始 token**,字节级精确 | 一秒内 |

## 仓库布局

```
mockplus-context/                          # repo root
├── README.md / CHANGELOG.md / LICENSE     # 项目门面
├── docs/                                  # 给真人开发者/用户看
│   ├── architecture.md
│   ├── cookie.md
│   └── superpowers/                       # 内部 spec/plan(执行档案)
├── tests/                                 # pytest
└── skills/
    └── mockplus-context/                  # skill 自包含 - LLM 直接消费
        ├── SKILL.md                       # LLM 入口
        ├── scripts/                       # Python CLI(mockplus / cli / transform / client)
        └── references/                    # LLM 按需深读
            ├── examples.md
            └── troubleshooting.md
```

Cookie 默认在 `~/.config/mockplus/cookie`(系统级,跨多个 install 共享)。

## 5 分钟上手

```bash
# 1. clone
git clone https://github.com/MySwallow/mockplus-context.git
cd mockplus-context

# 2. 装 PyYAML
pip install PyYAML

# 3. 配 cookie(浏览器登录 mockplus.cn → F12 复制全部 cookie)
python3 skills/mockplus-context/scripts/mockplus.py cookie set

# 4. 拉数据
python3 skills/mockplus-context/scripts/mockplus.py data \
  'https://app.mockplus.cn/app/<APP>/develop/design/<PAGE>' --out page.yaml

# 5. 按需下切图(看 yaml 里 imageRef:<hash>)
python3 skills/mockplus-context/scripts/mockplus.py download \
  '<URL>' --nodes <hash1>,<hash2> --out ./assets

# 一站式拿齐 yaml + 切图 + 整页截图
python3 skills/mockplus-context/scripts/mockplus.py all '<URL>' ./my-page-dir
```

## 命令参考

| 命令 | 用途 |
|---|---|
| `mockplus data <URL> [--out PATH] [--format yaml\|json] [--stats]` | 拉结构化数据,默认 YAML 到 stdout |
| `mockplus download <URL> [--nodes all\|h1,h2] [--include-design]` | 按 hash 下切图,可加整页截图 |
| `mockplus all <URL> [<OUT_DIR>]` | 一站式 = data + download(all + design) |
| `mockplus tree <APP_ID> [--format text\|json]` | 树形浏览项目结构,找 page id |
| `mockplus cookie {set\|test\|status\|clear\|path}` | Cookie 管理 |

完整字段契约见 [`docs/architecture.md`](docs/architecture.md);Cookie 详细见 [`docs/cookie.md`](docs/cookie.md)。

## 升级(v0.4 → v0.5)

v0.5 是 breaking change,详见 [CHANGELOG.md](CHANGELOG.md) Migration 段。一句话总结:
- 命令重命名:`get-data` → `data`、`download-assets` → `download`、`inspect` → `data --stats`
- 输出默认从 JSON 改 YAML
- cookie 路径从 `skills/mockplus-context/config/cookie` 迁到 `~/.config/mockplus/cookie`
- download 接口改用 `--nodes hash,...`(从 YAML 里 `imageRef` 直取)

## 开发 / 测试

```bash
pip install -r tests/requirements.txt
pytest tests/
```

## 贡献

欢迎 PR。约定:
- 分支命名:`feat/<topic>` / `fix/<topic>` / `refactor/<topic>`
- 提交消息:`<type>: <description>`(type: feat/fix/refactor/docs/test/chore/perf/ci)
- Breaking change:在 CHANGELOG `Breaking` 段说明 + Migration 段提供命令映射

## License

MIT
```

- [ ] **Step 3: 暂存**

```bash
git add README.md
```

---

### Task 24: 写 CHANGELOG v0.5.0

**Files:**
- Modify: `CHANGELOG.md` (在 Unreleased 之后插入 v0.5.0)

**Reference:**
- spec §8.2 完整 CHANGELOG 文案

- [ ] **Step 1: 读当前 Unreleased 段**

Run: `head -20 CHANGELOG.md`

- [ ] **Step 2: 把 Unreleased 段下的内容滚到 v0.5.0,在 v0.4.0 之前插入新章节**

把 `## Unreleased` 段下原有的 Fixed/Changed 内容(关于 CI 修复、README 完善的部分)保留为"v0.4 后的 Unreleased 微调",并入 v0.5.0 章节的合适位置或单独保留一段。然后插入完整 v0.5.0 章节(在 `## v0.4.0 — 2026-05-22` 之前):

```markdown
## v0.5.0 — 2026-05-23

**合并最强子集:YAML 优先输出 + 一站式 all 命令 + 系统级 cookie。**

### Breaking
- 输出默认从 JSON 改 YAML(可用 `--format json` 切回)
- CLI 命令重命名:`get-data` → `data`、`download-assets` → `download`、`inspect` → `data --stats`
- cookie 文件默认路径从 `skills/mockplus-context/config/cookie` 迁到 `~/.config/mockplus/cookie`
- `download` 接口从 `--downloads '[{url,fileName},...]'` 改为 `--nodes all|h1,h2`(从 YAML 里 `imageRef` 直取)
- 删除 `inspect` 命令、`_explore.py`、`_schema.py`、`__init__.py`、`references/api-reference.md`(并入 SKILL.md)
- token key 命名:textStyle 改用 sharedStyle.name(原 `text_001`);其他 fill/layout/stroke/effect 改 6 位序号(原 `fill_001` → `fill_000001`)
- 节点字段:`bounds` 改为 `layout` 引用 + `globalVars.styles.layout_NNNNNN`;`text` 嵌套结构改为 `text + textStyle` 平铺;切图节点 `asset` 字段改为在 `fills` 数组里加 IMAGE fill
- 退出码 `50`(schema 校验失败)废弃
- cache 路径 `~/.cache/mockplus-context/` → `~/.cache/mockplus/`

### Added
- `all` 子命令:一站式 = data + download(all + design)
- `download --include-design` 同时下整页截图 `design.png`
- `data --stats`:nodes/styles/assets/unhandledFields 统计输出(替代 `inspect`)
- `download --nodes hash,...`:按 hash 选切图,直接对接 YAML 里 `imageRef`
- 颜色 alpha < 1 时输出 `rgba(r, g, b, a.xx)`(原 v0.4 是 `#RRGGBB (alpha=0.5)`)

### Changed
- Python 模块从 7 个合并到 4 个:`mockplus.py` / `cli.py` / `transform.py` / `client.py`
- SKILL.md 重写至 ~130 行(短 SKILL.md + `references/`)
- fixtures `expected/*.json` → `expected/*.yaml`(5 份重生)
- `tests/requirements.txt` 加 `PyYAML>=6`

### Removed
- `inspect` 命令(合并到 `data --stats`)
- `_explore.py`、`_schema.py`、`__init__.py`、`_api.py`、`_cookie.py`、`_assets.py`、`_transform.py`、`_tree.py`(并入新 4 模块)
- `references/api-reference.md`(并入 SKILL.md)

### Migration

旧命令 → 新命令:

| v0.4 | v0.5 |
|---|---|
| `mockplus get-data <URL>` | `mockplus data <URL>`(默认 YAML;要 JSON 加 `--format json`) |
| `mockplus inspect <URL>` | `mockplus data <URL> --stats` |
| `mockplus download-assets --downloads '[...]' --local-path X` | `mockplus download <URL> --nodes h1,h2 --out X` |
| (无对应) | `mockplus all <URL>`(新一站式) |

Cookie 迁移:

\`\`\`bash
mkdir -p ~/.config/mockplus && chmod 700 ~/.config/mockplus
mv skills/mockplus-context/config/cookie ~/.config/mockplus/cookie
chmod 600 ~/.config/mockplus/cookie
# 或者重跑一次 cookie set
python3 skills/mockplus-context/scripts/mockplus.py cookie set
\`\`\`

```

- [ ] **Step 3: 暂存**

```bash
git add CHANGELOG.md
```

---

### Task 25: 重写 docs/architecture.md

**Files:**
- Modify: `docs/architecture.md` (整文件重写)

**Reference:**
- spec §4(架构)、§6(输出契约)、§5.2(路径约定)

- [ ] **Step 1: 整文件重写**

```markdown
# Architecture (v0.5.0)

## 模块拆分

```
skills/mockplus-context/scripts/
├── mockplus.py      # 入口:argparse + 子命令 dispatch（~80 行）
├── cli.py           # 各 action 实现:data/download/all/tree/cookie（~250 行）
├── transform.py     # sketch JSON → 结构化 dict(YAML/JSON 可序列化)（~400 行）
└── client.py        # API 客户端 + cookie + CDN 下载 + cache 管理（~300 行）
```

**为什么 `client.py` 不叫 `io.py`**:Python 标准库已有 `io` 模块,子目录里 `from io import StringIO` 会被本地 `io.py` 遮蔽。

## 依赖关系

```
mockplus.py  →  cli.py  →  transform.py
                       \→  client.py
```

`cli.py` 是唯一引入命令行 IO 的层(stdout / stderr / exit code)。`transform.py` 与 `client.py` 是可被测试直接 import 的纯/显式 IO 模块。

## 数据流

```
URL → client.parse_url_or_short → client.fetch_index → client.flatten_pages
                                                                    ↓
                                                          client.get_page_data_cached
                                                                    ↓
                                                         transform.transform
                                                                    ↓
                                              transform.serialize(yaml|json)
                                                                    ↓
                                                            stdout / file
```

`download` 数据流:`URL → fetch_index → get_page_data_cached → client.extract_slices(wanted=...) → client.download_slices`。

## 关键设计:Token 表(`transform.TokenTable`)

- `globalVars.styles` 注册器,累积式
- fill/stroke/effect/layout 用 6 位序号 key(`fill_000001`),fingerprint 去重
- textStyle 优先用 `sharedStyle.name`(语义化);同名同 spec 复用,同名不同 spec 加 `_2`/`_3` 后缀;无 sharedStyle 退回序号 key
- 节点上只放引用,不内联 spec,YAML 体积大幅下降

## 关键设计:unhandledFields 探针

`transform.py` 维护 `LAYER_HANDLED` / `BASIC_HANDLED` 字段白名单。每次 transform 完一个节点,把没消费的字段路径塞进 `_meta.unhandledFields`(去重)。Mockplus 升级 sketch schema 时,新字段立刻出现在这个列表,提示需要更新 transform。

## 关键设计:容错降级

`extract_node` 递归 children 时单 child 抛异常会被捕获 → 占位节点 `{type: "_ERROR", _error: ...}` 替代 → 其他兄弟节点不受影响。`_meta.warnings` 记录降级事件。

## 路径约定

| 用途 | 默认 | 覆盖环境变量 |
|---|---|---|
| cookie 文件 | `~/.config/mockplus/cookie` | `MOCKPLUS_COOKIE_FILE` |
| API/cache 根 | `~/.cache/mockplus/<APP_ID>/` | `MOCKPLUS_CACHE_DIR` |
| 直接传 cookie | (无) | `MOCKPLUS_COOKIE` |
| `download` 输出 | `./mockplus-assets/<PAGE_ID>/` | `--out` |
| `all` 输出 | `./mockplus-cache/<APP_ID>/<PAGE_ID>/` | 第 2 个位置参数 |

## 退出码

```
0   成功
2   CLI 参数错 / transform 输出 assert 失败
10  cookie 未配置
11  --from-file 文件不存在
12  cookie 为空
14  HTTP 层失败
15  cookie test API 拒绝
21  index API code != 0
22  TARGET_ID 误判(group / notfound)
```

## 测试策略

- `tests/test_transform.py`:5 个 fixture 黄金对照(YAML expected),含 `unhandledFields == []` 断言
- `tests/test_assets.py`:本地 http.server 起 PNG 测 `client.download_slices` + `extract_slices`
- `tests/test_tree.py`:`cli.action_tree` text/json 输出
- `tests/test_token_naming.py`:TokenTable 命名策略(设计师命名优先、同名冲突后缀)
- 端到端(`all` 命令)依赖真 cookie + 真 CDN,作为手动 smoke,不入 CI
```

- [ ] **Step 2: 暂存**

```bash
git add docs/architecture.md
```

---

### Task 26: 更新 docs/cookie.md

**Files:**
- Modify: `docs/cookie.md`

- [ ] **Step 1: 读当前内容**

Run: `cat docs/cookie.md`

- [ ] **Step 2: 全文替换 cookie 路径**

替换:
- `skills/mockplus-context/config/cookie` → `~/.config/mockplus/cookie`
- 旧路径相关的目录创建步骤改为 `mkdir -p ~/.config/mockplus && chmod 700 ~/.config/mockplus`

- [ ] **Step 3: 在文档头部加 v0.5 迁移提示**

在第一个 `##` 章节之前插入:

```markdown
> **v0.4 → v0.5 迁移**:cookie 文件默认从 `skills/mockplus-context/config/cookie` 迁到系统级 `~/.config/mockplus/cookie`。如果你之前用的是仓库内路径,可以这样迁移:
>
> ```bash
> mkdir -p ~/.config/mockplus && chmod 700 ~/.config/mockplus
> mv skills/mockplus-context/config/cookie ~/.config/mockplus/cookie
> chmod 600 ~/.config/mockplus/cookie
> ```
```

- [ ] **Step 4: 暂存**

```bash
git add docs/cookie.md
```

---

### Task 27: 更新 references/(改 examples,改 troubleshooting,删 api-reference)

**Files:**
- Delete: `skills/mockplus-context/references/api-reference.md`
- Modify: `skills/mockplus-context/references/examples.md`
- Modify: `skills/mockplus-context/references/troubleshooting.md`

- [ ] **Step 1: 删 api-reference.md**

```bash
git rm skills/mockplus-context/references/api-reference.md
```

- [ ] **Step 2: 重写 examples.md**

整文件覆盖:

```markdown
# Examples

端到端调用样例(v0.5)。

## 例 1:单页拿 YAML

```bash
mockplus data 'https://app.mockplus.cn/app/<APP>/develop/design/<PAGE>' --out page.yaml
cat page.yaml | head -30
```

输出片段:

```yaml
metadata:
  name: 采购申请单列表（老板）
  pageId: -hKyUPiOs
  device: ios1x
  size: { width: 375, height: 812 }
nodes:
  - id: <UUID>
    name: 顶栏
    type: FRAME
    layout: layout_000001
    children: [...]
globalVars:
  styles:
    fill_000001:
      - '#FFFFFF'
    layout_000001:
      mode: none
      dimensions: { width: 375, height: 64 }
```

## 例 2:按 hash 下指定切图

LLM 在 page.yaml 里看到节点用 `fills: fill_000003`,而 `globalVars.styles.fill_000003` 是 `[{type: IMAGE, imageRef: 2b417ea8...}]`,则:

```bash
mockplus download '<URL>' --nodes 2b417ea8... --out ./assets
ls ./assets
# 2b417ea8....png
# 2b417ea8....svg(若 CDN 有)
# assets-manifest.json
```

## 例 3:一站式 + 视觉对照

```bash
mockplus all '<URL>' ./design-cache
ls ./design-cache
# data.yaml  design.png  assets/
```

## 例 4:URL 是 group 时先用 tree

```bash
mockplus tree <APP_ID>
# 📁 v1.7
#   📁 V1.7采购申请列表
#     📄 采购申请单列表(老板)  [-hKyUPiOs]  (375x812)
#     📄 ...

# JSON 格式给程序处理
mockplus tree <APP_ID> --format json | jq -r '.. | objects | select(.kind=="page") | "\(.id) \(.name)"'
```

## 例 5:回归检测 + 统计

```bash
mockplus data '<URL>' --stats --out /tmp/page.yaml
# stderr 含:
# ---- stats ----
# {
#   "nodes": 142,
#   "styles": 38,
#   "assetsImages": 7,
#   "typesSeen": {"FRAME": 23, "TEXT": 89, "INSTANCE": 12, ...},
#   "unhandledFields": [],
#   "warnings": []
# }
```
```

- [ ] **Step 3: 更新 troubleshooting.md(改命令名 + 删 schema/inspect 相关)**

读现状:`cat skills/mockplus-context/references/troubleshooting.md`

主要改动:
- 所有 `mockplus get-data` → `mockplus data`
- 所有 `mockplus download-assets` → `mockplus download`
- 所有 `mockplus inspect` → `mockplus data --stats`
- 删 `exit 50` 章节
- 删 `download-assets --downloads` 相关错误(`invalid host` / `unsupported format` / `filename must be png`)
- cookie 路径从 `<repo>/config/cookie` 改 `~/.config/mockplus/cookie`
- 加 `exit 22:URL 指向 group` 的处理示例(用 `mockplus tree`)

- [ ] **Step 4: 暂存**

```bash
git add skills/mockplus-context/references/
```

---

## H. CI

### Task 28: 更新 .github/workflows/ci.yml

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: 读现状**

Run: `cat .github/workflows/ci.yml`

- [ ] **Step 2: 确保 install 段含 PyYAML**

找到 `pip install` 段,确保依赖 `tests/requirements.txt`(Task 15 已加 PyYAML 进去)。如果 ci.yml 直接 `pip install pytest`(不读 requirements.txt),改为:

```yaml
- run: pip install -r tests/requirements.txt
```

确保 Python 矩阵保留 3.8 / 3.11 / 3.12。

- [ ] **Step 3: 跑一次 yamllint 或基本 sanity**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: 无输出(YAML 解析 OK)

- [ ] **Step 4: 暂存**

```bash
git add .github/workflows/ci.yml
```

---

## I. 验证

### Task 29: 跑 pytest 全绿

**Files:** (无修改)

- [ ] **Step 1: 跑完整测试套件**

Run: `pytest tests/ -v`
Expected:
- `test_transform.py`:7 passed(5 parametrize + 2 独立)
- `test_assets.py`:4 passed
- `test_tree.py`:全 pass
- `test_token_naming.py`:7 passed
- 总计 18+ passed,无 fail

- [ ] **Step 2: 跑 Python 3.8 / 3.11 / 3.12 矩阵(可选,有 pyenv/uv 时)**

Run(示例,有 pyenv 时):
```bash
for v in 3.8 3.11 3.12; do
  pyenv exec --python $v python3 -m pytest tests/ -q
done
```
Expected: 3 个版本都全绿

- [ ] **Step 3: 如有 fail,回到对应 Task 修正**

若 transform 黄金对照 fail:多半是 Task 16 重生时 transform 行为已变,或 Task 5-7 实现有偏差。先看 diff,再决定是修 transform 还是修 expected。

---

### Task 30: 手动 smoke `mockplus all <真实 URL>`

**前置:**有效 cookie 已配在 `~/.config/mockplus/cookie`,且能访问 mockplus.cn(国内或挂回国代理)。

**Files:** (无修改)

- [ ] **Step 1: cookie status**

```bash
python3 skills/mockplus-context/scripts/mockplus.py cookie status
```
Expected: 输出 `Path: ~/.config/mockplus/cookie` + `Days remaining: NN`

- [ ] **Step 2: 跑 all 命令**

```bash
python3 skills/mockplus-context/scripts/mockplus.py all \
  'https://app.mockplus.cn/app/<真实APP>/develop/design/<真实PAGE>' \
  /tmp/mockplus-smoke
```
Expected:
- stderr 显示进度("APP_ID=... PAGE_ID=... out=...")、"目标切图: N 个"、"OK: 下载 N (cached=...)"、"OK: design.png → ..."
- 最后打印 "==== 完成 ====" + 4 行产物路径
- 退出码 0

- [ ] **Step 3: 验证产物结构**

```bash
ls -la /tmp/mockplus-smoke/
# data.yaml  design.png  assets/

head -50 /tmp/mockplus-smoke/data.yaml
# 应看到 metadata: / nodes: / globalVars: / _meta:

# 检查 unhandledFields 为空
grep -A1 "unhandledFields" /tmp/mockplus-smoke/data.yaml
# unhandledFields: []

# 检查 token key 命名
grep -E "^[ ]+(fill_|layout_|stroke_|effect_)[0-9]{6}:" /tmp/mockplus-smoke/data.yaml | head -5
# 应有 6 位序号的 key

grep -E "^[ ]+\S+ Style:" /tmp/mockplus-smoke/data.yaml | head -5
# 应有设计师命名的 textStyle key(若 fixture 有 sharedStyle)

ls /tmp/mockplus-smoke/assets/ | head -10
# 切图文件 <hash>.png / <hash>.svg
```

- [ ] **Step 4: 验证 tree 命令**

```bash
python3 skills/mockplus-context/scripts/mockplus.py tree <真实APP>
# 输出树形结构,含 📁/📄 emoji
```

- [ ] **Step 5: 验证 data --stats**

```bash
python3 skills/mockplus-context/scripts/mockplus.py data '<URL>' --stats --out /tmp/p.yaml
# stderr 含 "---- stats ----" + JSON 统计
```

- [ ] **Step 6: 全过则准备提 PR**

```bash
git log --oneline refactor/merge-best-subset ^main
# 看本分支所有 commit 列表

git diff main --stat
# 看本分支总变更量
```

后续:用户自行 review staged changes 并 commit(每个 Task 都只 stage,未 commit);最后 push 分支 + 开 PR。

---

## 自审

### Spec 覆盖检查

| Spec 章节 | 实现任务 |
|---|---|
| §3 整体决策表 | 全计划遵循 |
| §4 架构(4 模块) | Task 1-13,client.py 替代 io.py 已在偏离 spec 段说明 |
| §5 CLI 接口契约 | Task 8-13 |
| §5.2 路径约定 | Task 1(cookie/cache 路径) + Task 11(download out) + Task 12(all out) |
| §5.3 产物目录结构 | Task 11(download) + Task 12(all 把切图放 assets/) |
| §5.4 退出码 | Task 1(10), Task 2(21), Task 8(11,12), Task 10(22), Task 13(2 + 默认) |
| §6 输出 YAML 形态 | Task 4-7 transform,Task 16 fixtures 验证 |
| §6.1 token key 命名规则 | Task 5 TokenTable + Task 21 TDD |
| §6.2 切图 hash → download 工作流 | Task 6(fill_image)+ Task 11(extract_slices + download) |
| §6.3 unhandledFields 探针 | Task 6(LAYER_HANDLED) + Task 17 断言 + Task 30 验证 |
| §7 测试改造 | Task 15-21 |
| §8.1 README | Task 23 |
| §8.2 CHANGELOG | Task 24 |
| §8.3 docs/architecture | Task 25 |
| §8.4 docs/cookie | Task 26 |
| §8.5 ci.yml | Task 28 |
| §8.6 references/ | Task 27 |
| §8.7 SKILL.md | Task 22 |
| §10 实施顺序 | 拆为 30 个细粒度 task |
| §11 验收标准 | Task 29(pytest) + Task 30(smoke) |

### 占位符扫描

- 无 TBD / TODO / fill in / implement later
- Task 27 step 3 让执行人改 troubleshooting.md 时需要"读现状再增量改",这是合理的(原文 162 行,贴全篇会让 plan 膨胀;增量替换指令明确)
- Task 24 step 2 同样是"在 X 之前插入新章节",需要执行人定位插入点;指令明确(在 `## v0.4.0 — 2026-05-22` 之前)

### 类型/命名一致性

- `client.write_cookie` ↔ Task 8 调用 ✓
- `client.cookie_status` ↔ Task 8 调用 ✓
- `client.test_cookie_api` ↔ Task 8 调用 ✓
- `client.extract_slices` ↔ Task 11 调用 ✓
- `client.download_slices` ↔ Task 11 调用 ✓
- `client.download_page_image` ↔ Task 11/12 调用 ✓
- `client.parse_url_or_short` / `fetch_index` / `flatten_pages` / `resolve_target_kind` / `get_page_data_cached` ↔ Task 10/11/12 调用 ✓
- `transform.transform` / `transform.serialize` / `transform.compute_stats` ↔ Task 10 调用 ✓
- `TokenTable.fill_solid` / `fill_gradient_linear` / `fill_gradient_radial` / `fill_image` / `stroke` / `shadow` / `layout` / `text_style` ↔ Task 6 调用 ✓
- argparse 字段名 `args.cmd / cookie_cmd / url / out / format / nodes / include_design / out_dir / app_id / from_file / refresh / stats` ↔ Task 8-12 调用一致 ✓
- 退出码 10/11/12/14/15/21/22 ↔ Task 1/2/8/10/13 ✓

### 已知未覆盖项

- **examples.md / troubleshooting.md 增量改造的具体行替换**(Task 27):指令是"找到 X 替换为 Y",没贴完整新文件——这是 trade-off,贴全篇会让 plan 长 200+ 行。执行人应能按指令准确改。
- **CHANGELOG Unreleased 段的微调内容如何并入**(Task 24):指令是"保留为 v0.5 章节合适位置或独立段",留了一点 judgement 空间;执行人合理判断即可。

---

## 执行选项

**Plan complete and saved to `docs/superpowers/plans/2026-05-23-mockplus-context-v0.5.md`。两种执行选择:**

**1. Subagent-Driven(推荐)** - 为每个任务调度一个全新子代理,任务之间评审,快速迭代。适合此 plan(30 个任务,子代理可并行/独立验证)。

**2. Inline Execution** - 在本会话中用 executing-plans skill 执行任务,批量执行加检查点。适合需要会话上下文连贯的场景。

**选哪种?**
