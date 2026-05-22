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


# ---------- 字段省略(compact) ----------

def compact(d: dict) -> dict:
    """删 null / [] / {} / '' 值,保留 0 和 False。"""
    return {k: v for k, v in d.items()
            if v is not None and v != [] and v != {} and v != ""}


# ---------- 切图 URL → hash(切图引用复用) ----------

def url_to_hash(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    m = re.search(r"/sketch/([^/]+)/", u)
    return m.group(1) if m else u.rsplit("/", 1)[-1].rsplit(".", 1)[0]


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
            "fontWeightName": font.get("fontWeight", ""),
            "fontDisplayName": font.get("name", ""),
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
            "type": s.get("type", "outside"),
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
            "position": b.get("type", "center"),
            "dash": list(dash) if dash else None,
        })
        return self._intern("stroke", spec) if spec else None

    def shared(self, ss: dict, refs: List[str]) -> Optional[str]:
        """ss = node.sharedStyle = {id, name, type}; 返回 sharedStyle.id 作为 key。"""
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


# ---------- 单节点提取 ----------

class TransformContext:
    def __init__(self):
        self.bank = StyleBank()
        self.unhandled = set()
        self.warnings = []
        self.input_field_count = 0
        self.seen_symbol_ids = set()

    def warn(self, msg: str):
        self.warnings.append(msg)


# 一个 layer 节点上我们消费的顶层字段
LAYER_HANDLED = {
    "basic", "bounds", "fill", "stroke", "effect", "text", "slice",
    "sharedStyle", "children",
}

# basic 子字段我们消费的
BASIC_HANDLED = {
    "id", "sourceID", "type", "realType", "name", "opacity",
    "libraryID", "libraryName", "imageID", "containerSourceName",
    "symbolId", "symbolMasterId",
}


def extract_node(node: dict, ctx: TransformContext, parent_path: List[str]) -> dict:
    basic = node.get("basic") or {}
    name = basic.get("name", "")
    btype = basic.get("type", "")
    rtype = basic.get("realType", "")
    opacity = basic.get("opacity", 1)
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

    csn = basic.get("containerSourceName")
    if csn:
        out["sourceComponent"] = csn

    lib_id = basic.get("libraryID")
    lib_name = basic.get("libraryName")
    if lib_id or lib_name:
        out["library"] = compact({"id": lib_id, "name": lib_name})

    img_id = basic.get("imageID")
    if img_id:
        out["imageId"] = img_id

    sm_id = basic.get("symbolMasterId")
    s_id = basic.get("symbolId")
    if sm_id or s_id:
        sym = compact({"masterId": sm_id, "symbolId": s_id})
        if sym:
            out["symbol"] = sym
            if nid in ctx.seen_symbol_ids:
                ctx.warn(f"SymbolInstance sourceID {nid} 重复出现,可能不稳定")
            ctx.seen_symbol_ids.add(nid)

    text = node.get("text") or {}
    text_styles = text.get("styles") or []
    if text_styles:
        st = text_styles[0]
        if len(text_styles) > 1:
            ctx.warn(f"node {nid} 有 {len(text_styles)} 段 text.styles,仅取首段")
        out["text"] = {"value": st.get("value", ""), "style": ctx.bank.text(st)}

    fill = node.get("fill") or {}
    fc = fill.get("colors") or []
    if fc:
        refs = [ctx.bank.fill(c) for c in fc]
        out["fills"] = [r for r in refs if r]

    stroke = node.get("stroke") or {}
    borders = stroke.get("borders") or []
    dash = stroke.get("dash") or []
    if borders:
        refs = [ctx.bank.stroke(b, dash=dash) for b in borders]
        out["strokes"] = [r for r in refs if r]
    radius = stroke.get("radius")
    if radius and any(r > 0 for r in radius):
        out["radius"] = [round_num(r) for r in radius]

    eff = node.get("effect") or {}
    shadows = eff.get("shadows") or []
    if shadows:
        refs = [ctx.bank.shadow(s) for s in shadows]
        out["shadows"] = [r for r in refs if r]

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

    shared = node.get("sharedStyle") or {}
    if shared.get("id"):
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

    for k in node.keys():
        if k not in LAYER_HANDLED:
            ctx.unhandled.add(f"layer.{k}")
    for k in basic.keys():
        if k not in BASIC_HANDLED:
            ctx.unhandled.add(f"layer.basic.{k}")
    ctx.input_field_count += len(node) + len(basic)

    # T17 容错降级:children 递归也包 try/except
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

    return compact(out)


# ---------- metadata ----------

def build_metadata(data: dict, page_meta: dict, app_id: str) -> dict:
    canvas = data.get("size") or {}
    artboard_scale = data.get("artboardScale", 1)
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
        "pageName": data.get("pageName", ""),
        "path": page_meta.get("path", ""),
        "device": page_meta.get("device", "") or data.get("device", ""),
        "canvas": {
            "width": canvas.get("width"),
            "height": canvas.get("height"),
        },
        "backgroundColor": normalize_bg(data.get("backgroundColor", "")),
        "updatedAt": page_meta.get("updatedAt", ""),
        "source": data.get("source", ""),
        "artboardScale": artboard_scale,
        "pluginVersion": data.get("pluginVersion", ""),
        "pageImage": page_image,
    }
    return compact(md)


# ---------- 顶层 ----------

def transform(data: dict, page_meta: dict, app_id: str) -> dict:
    ctx = TransformContext()
    layers = data.get("layers") or {}
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
