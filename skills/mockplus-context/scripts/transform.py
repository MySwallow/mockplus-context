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
    "ShapePath": "VECTOR",
    "Path": "VECTOR",
    "path": "VECTOR",        # Mockplus 偶尔小写
    "MSShapeGroup": "VECTOR",  # 形状组,统一按 VECTOR
    "Image": "IMAGE",        # 位图节点;图源常在父 SymbolInstance 或同级 MSSliceLayer 的 slice 上
    "MSSliceLayer": "SLICE", # Sketch 切片层;自带 slice.bitmapURL,与同级 Image 节点配对
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
        # Mockplus sharedStyle.type 实际值是 "TextStyle"(大写驼峰)
        shared = node.get("sharedStyle") or {}
        stype = (shared.get("type") or "").lower()
        preferred = shared.get("name") if "text" in stype else None
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
    # OrderedDict → dict(YAML 才能序列化)
    def _normalize(obj):
        if isinstance(obj, OrderedDict):
            return {k: _normalize(v) for k, v in obj.items()}
        if isinstance(obj, dict):
            return {k: _normalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_normalize(x) for x in obj]
        return obj

    normalized = _normalize(result)

    if fmt == "json":
        import json
        return json.dumps(normalized, ensure_ascii=False, indent=2)
    if fmt == "yaml":
        import yaml
        # default_flow_style=False(块格式),但 size/dimensions 等小 dict 想要 flow 风格
        # 简单起见全部块格式,可读性已够
        return yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False,
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
