"""scope.py — 两级取数(v0.8):整页大纲 + 按节点裁子树。

对标 Figma 官方 MCP 的 get_metadata(稀疏大纲)→ get_design_context(按节点下钻):
大页先看 outline 选区块,再 `data --node <id>` 只拉该区块。Mockplus API 只能整页
取数,但整页转换结果在本地——两者都是纯本地操作,不增加 API 调用。

输入输出都是 transform(+relayout)产出的 result dict(蒸馏前),不修改入参。
"""
import re
from typing import Dict, List, Optional, Tuple

from distill import is_auto_name

# Claude Code 单次工具响应默认上限 25k token;粗估有误差,留 20% 余量
TOKEN_BUDGET = 20000

_CJK_RE = re.compile(r"[　-〿一-鿿＀-￯]")
_STYLE_REF_KEYS = ("layout", "fills", "strokes", "effects", "textStyle")


class ScopeError(Exception):
    """--node 解析失败(不存在/不唯一)。消息可直接展示给用户/LLM。"""


def estimate_tokens(text: str) -> int:
    """粗估 token:中日韩字符按 1 字 1 token,其余按 3.2 字符 1 token。"""
    cjk = len(_CJK_RE.findall(text))
    return int(cjk + (len(text) - cjk) / 3.2)


def budget_hint(text: str, url: str, scoped: bool,
                budget: int = TOKEN_BUDGET) -> Optional[str]:
    """输出超预算时给出可执行的缩小范围建议;未超返回 None。"""
    est = estimate_tokens(text)
    if est <= budget:
        return None
    if scoped:
        return (f"WARN: 输出约 {est} token(>{budget}),单次读取可能被截断;"
                f"所选区块仍偏大,从 `mockplus outline {url}` 里挑更小的子区块再 --node")
    return (f"WARN: 输出约 {est} token(>{budget}),单次读取可能被截断;"
            f"建议先 `mockplus outline {url}` 看区块结构,"
            f"再 `mockplus data {url} --node <id>[,<id>...]` 按区块拉取")


# ------------------------------------------------------------
# 几何
# ------------------------------------------------------------

def _rect(node: dict, styles: dict) -> Optional[Tuple[float, float, float, float]]:
    spec = styles.get(node.get("layout")) or {}
    loc = spec.get("locationRelativeToParent") or {}
    dim = spec.get("dimensions") or {}
    vals = (loc.get("x"), loc.get("y"), dim.get("width"), dim.get("height"))
    return None if None in vals else vals


def _walk(result: dict):
    """深度优先遍历,产出 (node, depth, 画布绝对 (x, y, w, h) 或 None, 祖先 id 元组)。"""
    styles = result["globalVars"]["styles"]
    relative = (result.get("_meta") or {}).get("coordinateSpace") == "parent-relative"

    def rec(nodes, depth, ox, oy, ancestors):
        for n in nodes or []:
            r = _rect(n, styles)
            box = None
            if r is not None:
                x, y = (ox + r[0], oy + r[1]) if relative else (r[0], r[1])
                box = (x, y, r[2], r[3])
            yield n, depth, box, ancestors
            nx, ny = (box[0], box[1]) if box else (ox, oy)
            yield from rec(n.get("children"), depth + 1, nx, ny, ancestors + (n.get("id"),))

    yield from rec(result.get("nodes"), 0, 0.0, 0.0, ())


def _num(v: float):
    return int(v) if float(v).is_integer() else round(v, 1)


def _descendants(node: dict) -> int:
    return sum(1 + _descendants(c) for c in node.get("children") or [])


# ------------------------------------------------------------
# --node 子树裁剪
# ------------------------------------------------------------

def _resolve(index: Dict[str, tuple], query: str) -> str:
    q = query.strip().upper()
    if q in index:
        return q
    if len(q) < 8:
        raise ScopeError(f"--node {query!r} 太短:至少给 8 位(outline / 蒸馏 YAML 里的 id)")
    hits = [k for k in index if k.startswith(q)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ScopeError(f"--node {query!r} 在本页不存在;先 `mockplus outline <URL>` "
                         f"查看可用区块 id(注意 id 属于当前页,换页后不通用)")
    raise ScopeError(f"--node {query!r} 匹配到 {len(hits)} 个节点,请给完整 UUID: "
                     + ", ".join(index[h][0].get("id") for h in hits[:5]))


def _referenced_styles(nodes: List[dict]) -> set:
    refs = set()
    for n in nodes:
        for k in _STYLE_REF_KEYS:
            if isinstance(n.get(k), str):
                refs.add(n[k])
        refs |= _referenced_styles(n.get("children") or [])
    return refs


def _component_ids(nodes: List[dict]) -> set:
    ids = set()
    for n in nodes:
        if n.get("componentId"):
            ids.add(n["componentId"])
        ids |= _component_ids(n.get("children") or [])
    return ids


def _with_abs(node: dict, box, relative: bool) -> dict:
    """子树根补画布绝对锚点(叶子原本没有),对齐整页截图用;键序插在 layout 之后。"""
    if not relative or box is None or "absolutePosition" in node:
        return node
    out = {}
    for k, v in node.items():
        out[k] = v
        if k == "layout":
            out["absolutePosition"] = {"x": _num(box[0]), "y": _num(box[1])}
    return out


def _index(result: dict) -> Dict[str, tuple]:
    """大写 id → (node, 画布绝对框, 祖先 id 元组)。"""
    index = {}
    for n, _depth, box, anc in _walk(result):
        if isinstance(n.get("id"), str):
            index[n["id"].upper()] = (n, box, anc)
    return index


def locate(result: dict, queries: List[str]) -> List[Tuple[dict, Optional[tuple]]]:
    """按 --node 口径解析 id,返回 [(node, 画布绝对框)](按给定顺序去重)。失败抛 ScopeError。"""
    if not queries:
        raise ScopeError("--node 为空")
    index = _index(result)
    keys = []
    for q in queries:
        key = _resolve(index, q)
        if key not in keys:
            keys.append(key)
    return [(index[k][0], index[k][1]) for k in keys]


def select(result: dict, queries: List[str]) -> Tuple[dict, List[str]]:
    """裁出 queries 指定的子树。返回 (新 result, 提示信息列表)。

    - 匹配:完整 UUID,或 ≥8 位唯一前缀(大小写不敏感);失败抛 ScopeError
    - 同时选中祖先与后代时只保留祖先(后代已包含在内)
    - globalVars.styles / metadata.components 只保留子树实际引用的项
    """
    if not queries:
        raise ScopeError("--node 为空")
    relative = (result.get("_meta") or {}).get("coordinateSpace") == "parent-relative"
    index = _index(result)

    chosen = []
    for q in queries:
        key = _resolve(index, q)
        if key not in chosen:
            chosen.append(key)
    notes = []
    kept = []
    for key in chosen:
        anc = {a.upper() for a in index[key][2] if isinstance(a, str)}
        dup = anc & set(chosen)
        if dup:
            notes.append(f"--node {index[key][0].get('id')} 已包含在所选祖先节点内,跳过")
            continue
        kept.append(key)

    roots = [_with_abs(index[k][0], index[k][1], relative) for k in kept]
    refs = _referenced_styles(roots)
    styles = {k: v for k, v in result["globalVars"]["styles"].items() if k in refs}

    md = dict(result.get("metadata") or {})
    comp_ids = _component_ids(roots)
    comps = {k: v for k, v in (md.get("components") or {}).items() if k in comp_ids}
    if comps:
        md["components"] = comps
    else:
        md.pop("components", None)

    meta = dict(result.get("_meta") or {})
    meta["scope"] = {
        "nodes": [index[k][0].get("id") for k in kept],
        "pageNodes": len(index),
        "note": "子树根的 pos 仍相对原父节点;abs(未蒸馏为 absolutePosition)是画布绝对锚点,对照 design.png",
    }

    out = dict(result)
    out["metadata"] = md
    out["nodes"] = roots
    gv = dict(result.get("globalVars") or {})
    gv["styles"] = styles
    out["globalVars"] = gv
    out["_meta"] = meta
    return out, notes


# ------------------------------------------------------------
# outline 大纲
# ------------------------------------------------------------

def _top_text(node: dict, boxes: dict, limit: int = 24) -> Optional[str]:
    """子树里视觉上最靠上(再靠左)的一段文本,作为区块辨识预览。"""
    best = None
    stack = [node]
    while stack:
        n = stack.pop()
        if n.get("type") == "TEXT" and isinstance(n.get("text"), str) and n["text"].strip():
            box = boxes.get(id(n))
            key = (box[1], box[0]) if box else (float("inf"), float("inf"))
            if best is None or key < best[0]:
                best = (key, n["text"])
        stack.extend(n.get("children") or [])
    if best is None:
        return None
    t = " ".join(best[1].split())
    return t if len(t) <= limit else t[:limit] + "…"


def render_outline(result: dict, id_map: Optional[dict] = None,
                   max_depth: Optional[int] = None,
                   page_tokens: Optional[int] = None,
                   fetch_hint: str = "") -> str:
    """整页大纲:容器节点(有子节点)+ 顶层节点 + 缺切图节点,每个一行。

    行格式:`[TYPE] "图层名" #id @x,y wxh n=子孙数 text="子树最靠上的文本"`
    坐标为画布绝对坐标;同级按阅读顺序(y 再 x)排,不是 YAML 里的图层 z 序;
    自动命名(编组/矩形…)不显示;id 与蒸馏 YAML 一致。
    """
    id_map = id_map or {}
    md = result.get("metadata") or {}
    size = md.get("size") or {}
    total = sum(1 for _ in _walk(result))
    head = (f"# 页面: {md.get('name', '')} ({md.get('pageId', '')})  "
            f"画布 {size.get('width')}x{size.get('height')}  节点 {total}")
    if page_tokens is not None:
        head += f"  整页 YAML 约 {page_tokens} token"
    lines = [head,
             "# 坐标 = 画布绝对坐标(对照 design.png);同级按位置从上到下排;"
             "n = 子孙节点数;text = 子树最靠上的文本"]
    if fetch_hint:
        lines.append(f"# 下钻: {fetch_hint}")
    missing = sum(1 for n, _d, _b, _a in _walk(result) if n.get("missingSlice"))
    if missing:
        lines.append(f"# 疑似图标无切图 {missing} 个(行尾 missingSlice=icon|vector),"
                     f"处理见 SKILL「实现守则」;截图参考: mockplus shot <URL> --node <id>")

    # 以节点对象身份为键:前提是本次调用内 result 不被改写/替换节点(render 只读)
    boxes = {id(n): box for n, _d, box, _a in _walk(result)}

    def reading_order(nodes):
        def key(n):
            b = boxes.get(id(n))
            return (b[1], b[0]) if b else (float("inf"), float("inf"))
        return sorted(nodes or [], key=key)

    def emit(nodes, depth):
        for n in reading_order(nodes):
            kids = n.get("children") or []
            if kids or depth == 0 or n.get("missingSlice"):
                lines.append("  " * depth + _outline_line(n, boxes.get(id(n)), kids, boxes, id_map))
            if kids and (max_depth is None or depth < max_depth):
                emit(kids, depth + 1)

    emit(result.get("nodes"), 0)
    return "\n".join(lines) + "\n"


def _outline_line(n: dict, box, kids: list, boxes: dict, id_map: dict) -> str:
    parts = [f"[{n.get('type', '?')}]"]
    name = n.get("name")
    if name and not is_auto_name(name) and not (n.get("type") == "TEXT" and name == n.get("text")):
        parts.append(f'"{name}"')
    nid = n.get("id", "")
    parts.append(f"#{id_map.get(nid, nid)}")
    if box is not None:
        parts.append(f"@{_num(box[0])},{_num(box[1])} {_num(box[2])}x{_num(box[3])}")
    if kids:
        parts.append(f"n={_descendants(n)}")
    text = _top_text(n, boxes)
    if text:
        parts.append(f'text="{text}"')
    if n.get("missingSlice"):
        parts.append(f"missingSlice={n['missingSlice']}")
    return " ".join(parts)
