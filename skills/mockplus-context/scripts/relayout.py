"""relayout.py - Level-1 包含树重建 + 相对坐标改写(v0.6.0 后处理 pass)。

输入/输出都是 transform.transform() 的 result dict;纯函数,不修改入参。
transform 在 coords="relative"(默认)时调用 apply();失败自动回退原样并告警,
绝不输出半成品树。

核心事实(5 页真实语料 1582 节点实证,详见 CHANGELOG v0.6.0):
- v0.5 的 locationRelativeToParent 名不副实,存的是画布绝对坐标;
- 授权 children 树是可信骨架(99%+ 几何一致),但兄弟层的视觉包含不表达
  (91%+ 节点存在"视觉被包含、树上却是兄弟"的更紧容器);
- 导出数组顺序:前 = 顶层(与 Sketch 原生 bottom-first 相反,作用域内 382:4 实证)。

算法:作用域化重建 —— 授权容器是硬边界,只在每个容器的直接子之间
把兄弟嵌进兄弟(最小面积包含者胜出);INSTANCE 内部结构冻结、也不接受收养,
唯一跨界是收养进兄弟授权 FRAME(打 adoptedBy: geometry 标记)。
"""
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

EPS_CONTAIN = 1.0    # 包含判定容差(px):吸收半像素网格与贴边(语料 ε∈[0.5,2] 零敏感)
EPS_STACK = 0.5      # 完全重合(纯堆叠)判定容差;必须比 EPS_CONTAIN 紧——
                     # 大容差会把"小图形 vs 略大容器"误判为堆叠(图表页实证)
FULL_CANVAS_RATIO = 0.95  # 画板作用域内双轴 ≥95% 画布 → 整页背景,不做父
Z_EVIDENCE_MIN = 0.8      # 作用域内 z 方向证据低于此 → 本页禁用 z 过滤(只减护栏不改判定)
AREA_TIE = 0.5            # 最小面积平局带宽(px²),平局走确定性 tie-break

# 可为父:分区/卡片背景大多是矢量圆角矩形(语料里 19/21 新父是 VECTOR)
PARENT_ELIGIBLE = {"FRAME", "RECTANGLE", "ELLIPSE", "VECTOR", "IMAGE"}
# 不可为父且冻结不重挂:SLICE/MASK 是导出/裁剪元数据;TEXT 行框包含纯属巧合
# (语料 0 例真实 TEXT 容器);INSTANCE 不收养——注入外来子会污染组件实例结构。
FROZEN_TYPES = {"SLICE", "MASK"}


def _norm(v: float):
    """整数值浮点 → int(YAML 更干净);半像素保留 .5。"""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _fp(spec: Any) -> str:
    """token spec → 可比较指纹(dict 按 key 排序)。"""
    if isinstance(spec, dict):
        return repr(sorted((k, _fp(v)) for k, v in spec.items()))
    if isinstance(spec, list):
        return repr([_fp(x) for x in spec])
    return repr(spec)


def _geom_of(node: dict, styles: dict) -> Optional[Tuple[float, float, float, float]]:
    """节点 → (x, y, w, h) 画布绝对坐标;拿不到几何(_ERROR 等)返回 None。"""
    lk = node.get("layout")
    if not lk:
        return None
    spec = styles.get(lk)
    if not isinstance(spec, dict):
        return None
    loc = spec.get("locationRelativeToParent") or {}
    dim = spec.get("dimensions") or {}
    try:
        return (float(loc["x"]), float(loc["y"]),
                float(dim["width"]), float(dim["height"]))
    except (KeyError, TypeError, ValueError):
        return None


def _area(g) -> float:
    return g[2] * g[3]


def _contains(p, c, eps: float) -> bool:
    return (p[0] - eps <= c[0] and p[1] - eps <= c[1]
            and p[0] + p[2] + eps >= c[0] + c[2]
            and p[1] + p[3] + eps >= c[1] + c[3])


def _eqb(p, c, eps: float) -> bool:
    return (abs(p[0] - c[0]) <= eps and abs(p[1] - c[1]) <= eps
            and abs(p[2] - c[2]) <= eps and abs(p[3] - c[3]) <= eps)


# ============================================================
# 主入口
# ============================================================

def apply(result: dict) -> dict:
    """对 transform result 应用包含树重建 + 相对坐标改写。

    返回新 result dict(不修改入参)。任何失败——显式校验不过或未预期异常——
    都返回原 result,仅在 _meta.warnings 追加原因(宁可维持 v0.5 绝对坐标
    语义,也绝不输出坏树、绝不让重建缺陷升级为整次导出失败)。
    """
    try:
        return _apply_inner(result)
    except Exception as e:  # 兜底:覆盖未预期缺陷(schema 漂移、深树递归上限等)
        return _abort(result, f"relayout: 意外异常({type(e).__name__}: {e}),回退绝对坐标")


def _apply_inner(result: dict) -> dict:
    meta = result.get("_meta") or {}
    if meta.get("coordinateSpace") == "parent-relative":
        return result  # 幂等:已是相对坐标,拒绝二次改写

    size = (result.get("metadata") or {}).get("size") or {}
    styles = (result.get("globalVars") or {}).get("styles") or {}
    try:
        cw, ch = float(size["width"]), float(size["height"])
    except (KeyError, TypeError, ValueError):
        return _abort(result, "relayout: metadata.size 缺失,跳过重建")

    # ---- 1. 展平为记录表(0 号 = 虚拟画板根) ----
    recs: List[dict] = [{
        "i": 0, "sib": -1, "ap": None, "node": None, "type": "",
        "geom": (0.0, 0.0, cw, ch), "inside_inst": False, "kids": [],
    }]
    # 被非 layout 字段引用的 token key(fills/strokes/effects/textStyle)。
    # textStyle key 是设计师自由命名,可能恰好形如 layout_NNNNNN ——
    # 新 layout 编号必须避开,否则会静默覆盖(审查 HIGH-1)。
    reserved_keys = set()

    def walk(node: dict, ap: int, sib: int, inside_inst: bool) -> None:
        r = {
            "i": len(recs), "sib": sib, "ap": ap, "node": node,
            "type": node.get("type", ""),
            "geom": _geom_of(node, styles),
            "inside_inst": inside_inst, "kids": [],
        }
        recs.append(r)
        recs[ap]["kids"].append(r["i"])
        for f in ("fills", "strokes", "effects", "textStyle"):
            v = node.get(f)
            if isinstance(v, str):
                reserved_keys.add(v)
        for j, c in enumerate(node.get("children") or []):
            if isinstance(c, dict):
                walk(c, r["i"], j, inside_inst or r["type"] == "INSTANCE")

    for j, n in enumerate(result.get("nodes") or []):
        if isinstance(n, dict):
            walk(n, 0, j, False)

    def frozen(r: dict) -> bool:
        return (r["type"] in FROZEN_TYPES or r["type"].startswith("_")
                or r["geom"] is None)

    # ---- 2. 作用域 = 授权容器(画板根 + 非 INSTANCE、非实例内部的有子节点) ----
    scopes = [recs[0]] + [r for r in recs[1:]
                          if r["kids"] and r["type"] != "INSTANCE"
                          and not r["inside_inst"] and not frozen(r)]

    # ---- 3. z 方向自检(只统计作用域内兄弟包含对;决策③) ----
    later = earlier = 0
    for sc in scopes:
        ms = [recs[k] for k in sc["kids"] if recs[k]["geom"] is not None]
        for a in ms:
            for b in ms:
                if a is b or _eqb(a["geom"], b["geom"], EPS_STACK):
                    continue
                if _area(a["geom"]) <= _area(b["geom"]):
                    continue
                if _contains(a["geom"], b["geom"], EPS_CONTAIN):
                    if a["sib"] > b["sib"]:
                        later += 1     # 容器在数组更后(更底)= 前顶后底,预期方向
                    else:
                        earlier += 1
    total_pairs = later + earlier
    z_on = total_pairs == 0 or later / total_pairs >= Z_EVIDENCE_MIN
    warnings: List[str] = []
    if not z_on:
        warnings.append(
            f"relayout: z 方向证据不足({later}:{earlier}),本页禁用 z 过滤")

    # ---- 4. 逐作用域指派几何父 ----
    final = {r["i"]: r["ap"] for r in recs[1:]}
    ties = reparented = adopted = 0
    for sc in scopes:
        members = [recs[k] for k in sc["kids"]]
        is_root = sc["i"] == 0
        for c in members:
            if frozen(c):
                continue
            cg = c["geom"]
            cands = []
            for p in members:
                if p is c or p["geom"] is None:
                    continue
                if p["type"] not in PARENT_ELIGIBLE:
                    continue
                pg = p["geom"]
                if is_root and pg[2] >= FULL_CANVAS_RATIO * cw \
                        and pg[3] >= FULL_CANVAS_RATIO * ch:
                    continue  # 整页背景保持根层兄弟
                if _eqb(pg, cg, EPS_STACK):
                    continue  # 纯堆叠保持兄弟
                if _area(pg) <= _area(cg):
                    continue  # 面积严格递减 ⇒ 父链天然无环
                if not _contains(pg, cg, EPS_CONTAIN):
                    continue
                if z_on and p["sib"] <= c["sib"]:
                    continue  # 容器必须画在内容物下面(数组更后)
                cands.append(p)
            if not cands:
                continue
            amin = min(_area(p["geom"]) for p in cands)
            pool = [p for p in cands if _area(p["geom"]) - amin < AREA_TIE]
            if len(pool) > 1:
                ties += 1
            best = min(pool, key=lambda p: (p["sib"], p["i"]))  # 最贴近子的下方一层
            final[c["i"]] = best["i"]

    # ---- 5. 组装最终树 + 校验(失败整体回退) ----
    kids_final: Dict[int, List[int]] = {r["i"]: [] for r in recs}
    for r in recs[1:]:
        kids_final[final[r["i"]]].append(r["i"])
    for v in kids_final.values():
        # 全局先序 = 严格自顶向下的层叠序:前=顶在每一层成立时,任意两节点
        # (含跨作用域收养对)的上下关系由其兄弟路径字典序决定,即先序位置——
        # 收养节点原本盖在(或垫在)目标容器整棵子树之上/之下,排序后语义不变。
        v.sort()

    seen = set()
    stack = [0]
    while stack:
        i = stack.pop()
        if i in seen:
            return _abort(result, "relayout: 检测到环,回退")
        seen.add(i)
        stack.extend(kids_final[i])
    if len(seen) != len(recs):
        return _abort(result, "relayout: 节点覆盖不完整,回退")

    kept_violations = 0
    for r in recs[1:]:
        pi = final[r["i"]]
        p = recs[pi]
        if r["geom"] is None or p["geom"] is None:
            continue
        if pi != r["ap"]:
            reparented += 1
            if not _contains(p["geom"], r["geom"], EPS_CONTAIN):
                return _abort(result, "relayout: 几何父包含违例,回退")
            if p["kids"]:  # 新父是授权容器 → 跨界收养
                adopted += 1
        elif not _contains(p["geom"], r["geom"], EPS_CONTAIN):
            kept_violations += 1  # 沿用授权父但溢出(实例内文本溢出等),仅记录

    # 可逆性:沿父链累加 rel 必须精确还原绝对坐标(坐标在 0.5 网格上,减法精确)
    for r in recs[1:]:
        if r["geom"] is None:
            continue
        ox, oy, i = 0.0, 0.0, final[r["i"]]
        chain = []
        while i != 0:
            chain.append(i)
            i = final[i]
        for i in chain:
            g = recs[i]["geom"]
            if g is not None:
                ox, oy = g[0], g[1]
                break
        if (ox + (r["geom"][0] - ox) != r["geom"][0]
                or oy + (r["geom"][1] - oy) != r["geom"][1]):
            return _abort(result, "relayout: 相对坐标不可逆,回退")

    # ---- 6. 重排节点 + 重编 layout token + 重建 styles 顺序 ----
    lay_keys: Dict[str, str] = {}   # 指纹 → 新 layout key
    lay_seq = [0]                   # 编号器(跳过 reserved_keys 后不再连续)
    styles_new: "OrderedDict[str, Any]" = OrderedDict()

    def intern_layout(spec: dict) -> str:
        f = _fp(spec)
        if f in lay_keys:
            return lay_keys[f]
        while True:
            lay_seq[0] += 1
            key = f"layout_{lay_seq[0]:06d}"
            if key not in reserved_keys:
                break  # 避开设计师命名恰好形如 layout_NNNNNN 的保留 token
        lay_keys[f] = key
        styles_new[key] = spec
        return key

    def keep_style(key: Optional[str]) -> None:
        if key and key not in styles_new and key in styles:
            styles_new[key] = styles[key]

    def emit(i: int, ox: float, oy: float) -> dict:
        r = recs[i]
        node = r["node"]
        g = r["geom"]
        kids = kids_final[i]
        new: Dict[str, Any] = {}
        for k, v in node.items():
            if k == "children":
                continue
            if k == "layout":
                if g is None:  # 畸形 layout token:丢引用并告警,避免悬空/撞名
                    warnings.append(f"relayout: 节点 {node.get('id')} layout token 无法解析,已移除引用")
                    continue
                spec = dict(styles.get(v) or {})
                spec["locationRelativeToParent"] = {
                    "x": _norm(g[0] - ox), "y": _norm(g[1] - oy)}
                new["layout"] = intern_layout(spec)
                if kids:  # 决策⑥:仅容器落盘绝对坐标,叶子定位 = 父 abs + 自身 rel
                    new["absolutePosition"] = {"x": _norm(g[0]), "y": _norm(g[1])}
                if final[i] != r["ap"] and recs[final[i]]["kids"]:
                    new["adoptedBy"] = "geometry"
                continue
            new[k] = v
            if k in ("fills", "strokes", "effects", "textStyle"):
                keep_style(v)
        nx, ny = (g[0], g[1]) if g is not None else (ox, oy)
        if kids:
            new["children"] = [emit(k, nx, ny) for k in kids]
        return new

    nodes_new = [emit(i, 0.0, 0.0) for i in kids_final[0]]
    for k, v in styles.items():  # 兜底:未被引用的非 layout token 原样保留
        if k not in styles_new and not k.startswith("layout_"):
            styles_new[k] = v

    meta_new = dict(meta)
    meta_new["coordinateSpace"] = "parent-relative"
    meta_new["relayout"] = {
        "reparented": reparented,
        "adopted": adopted,
        "ambiguousTies": ties,
        "keptViolations": kept_violations,
        "zFilter": "on" if z_on else "off",
        "zEvidence": f"{later}:{earlier}",
    }
    meta_new["warnings"] = list(meta.get("warnings") or []) + warnings

    out = dict(result)
    out["nodes"] = nodes_new
    gv = dict(result.get("globalVars") or {})
    gv["styles"] = styles_new
    out["globalVars"] = gv
    out["_meta"] = meta_new
    return out


def _abort(result: dict, reason: str) -> dict:
    """校验失败:返回原 result(v0.5 绝对坐标语义),仅追加告警。"""
    out = dict(result)
    meta = dict(result.get("_meta") or {})
    meta["warnings"] = list(meta.get("warnings") or []) + [reason]
    out["_meta"] = meta
    return out
