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
    # 注:type 字段在 Sketch 部分节点(如 MSShapeGroup)中可能为空,被 compact 移除;
    # 因此只校验 realType + id + bounds 这些稳定字段。
    for k in ("id", "realType", "bounds"):
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
    # 注:type 字段在 Sketch 部分节点(如 MSShapeGroup)中可能为空,被 compact 移除。
    "required": ["id", "realType", "bounds"],
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
