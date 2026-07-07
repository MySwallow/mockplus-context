"""relayout(v0.6 包含树重建 + 相对坐标)黄金用例与不变量测试。

黄金用例来自真实语料复现的最小夹具:导航条纹(矩形)与压在其上的文本
在授权树里是兄弟,重建后必须成为父子且相对坐标正确。
"""
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "skills" / "mockplus-context" / "scripts"))
import relayout
import transform

FIXTURES = Path(__file__).parent / "fixtures"
ALL_FIXTURES = ["simple-text", "nested-groups", "with-slices",
                "with-shared-styles", "with-gradients"]
META = {
    "id": "p-test", "name": "test", "path": "test",
    "device": "ios1x", "imageURL": "", "updatedAt": "",
}

# 夹具节点 id 已脱敏为 FACADE 占位(见 fixtures/*.json);语义见行尾注释
TEXT_ID = "FACADE15-0000-4000-8000-000000000000"      # 底部提示文本
RECT_ID = "FACADE08-0000-4000-8000-000000000000"      # 矩形(375x48 条纹)
INST_ID = "FACADE03-0000-4000-8000-000000000000"      # 吸底按钮 INSTANCE
INST_CHILD_ID = "FACADE04-0000-4000-8000-000000000000"
HOME_INDICATOR_ID = "FACADE11-0000-4000-8000-000000000000"  # 几何上落在 INSTANCE 内


def _tf(name, coords="relative"):
    data = json.load(open(FIXTURES / f"{name}.json"))
    return transform.transform(data, META, "test-app", coords=coords)


def _find(nodes, nid):
    for n in nodes:
        if n.get("id") == nid:
            return n
        hit = _find(n.get("children") or [], nid)
        if hit:
            return hit
    return None


def _pairs(nodes, parent=None):
    """yield (node, parent_node_or_None) 全树。"""
    for n in nodes:
        yield n, parent
        yield from _pairs(n.get("children") or [], n)


def _loc(result, node):
    spec = result["globalVars"]["styles"][node["layout"]]
    p = spec["locationRelativeToParent"]
    d = spec["dimensions"]
    return float(p["x"]), float(p["y"]), float(d["width"]), float(d["height"])


def _abs_map(name):
    """coords=absolute 跑一遍,得到 id → 画布绝对 (x,y,w,h) 基准。"""
    r = _tf(name, coords="absolute")
    out = {}
    for n, _ in _pairs(r["nodes"]):
        if n.get("layout"):
            out[n["id"]] = _loc(r, n)
    return out


# ============================================================
# 黄金用例(nested-groups)
# ============================================================

def test_golden_sibling_becomes_child_with_relative_coords():
    r = _tf("nested-groups")
    # 文本不再是根层节点
    assert _find([n for n in r["nodes"]], TEXT_ID) is not None
    assert all(n["id"] != TEXT_ID for n in r["nodes"])
    # 而是矩形的子节点,rel = (155, 440-428) = (155, 12)
    rect = _find(r["nodes"], RECT_ID)
    text = _find(rect.get("children") or [], TEXT_ID)
    assert text is not None
    x, y, _, _ = _loc(r, text)
    assert (x, y) == (155, 12)
    # 成为容器的矩形要落盘绝对坐标(决策⑥:仅容器)
    assert rect["absolutePosition"] == {"x": 0, "y": 428}
    assert "absolutePosition" not in text


def test_instance_internals_frozen_and_relative():
    r = _tf("nested-groups")
    inst = _find(r["nodes"], INST_ID)
    kids = inst.get("children") or []
    assert [c["id"] for c in kids] == [INST_CHILD_ID]  # 内部结构原样
    x, y, _, _ = _loc(r, kids[0])
    assert (x, y) == (266, 19)  # 737 - 718
    assert inst["absolutePosition"] == {"x": 0, "y": 718}


def test_instance_does_not_adopt_strays():
    """HomeIndicator/形状节点 几何上落在 INSTANCE 框内,但 INSTANCE 不收养(决策②)。"""
    r = _tf("nested-groups")
    top_ids = [n["id"] for n in r["nodes"]]
    assert HOME_INDICATOR_ID in top_ids
    inst = _find(r["nodes"], INST_ID)
    assert all(c["id"] != HOME_INDICATOR_ID for c in inst.get("children") or [])
    m = r["_meta"]["relayout"]
    assert m["reparented"] == 1 and m["adopted"] == 0


# ============================================================
# 不变量(全部夹具)
# ============================================================

@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_reversibility_bit_exact(name):
    """相对坐标沿父链累加必须精确还原绝对坐标。"""
    r = _tf(name)
    base = _abs_map(name)

    def walk(nodes, ox, oy):
        for n in nodes:
            nx, ny = ox, oy
            if n.get("layout"):
                x, y, _, _ = _loc(r, n)
                ax, ay = ox + x, oy + y
                bx, by, _, _ = base[n["id"]]
                assert (ax, ay) == (bx, by), f"{name}:{n['id']} 不可逆"
                nx, ny = ax, ay
            walk(n.get("children") or [], nx, ny)

    walk(r["nodes"], 0.0, 0.0)


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_containment_within_epsilon(name):
    """每个子矩形 ⊆ 父矩形(±ε);夹具 keptViolations 均为 0,可全量断言。"""
    r = _tf(name)
    base = _abs_map(name)
    eps = relayout.EPS_CONTAIN
    assert r["_meta"]["relayout"]["keptViolations"] == 0
    for n, p in _pairs(r["nodes"]):
        if p is None or not n.get("layout") or not p.get("layout"):
            continue
        cx, cy, cw, ch = base[n["id"]]
        px, py, pw, ph = base[p["id"]]
        assert px - eps <= cx and py - eps <= cy, f"{name}:{n['id']}"
        assert cx + cw <= px + pw + eps and cy + ch <= py + ph + eps, f"{name}:{n['id']}"


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_node_set_preserved(name):
    """重建只移动节点,不增不减。"""
    rel_ids = sorted(n["id"] for n, _ in _pairs(_tf(name)["nodes"]))
    abs_ids = sorted(n["id"] for n, _ in _pairs(_tf(name, "absolute")["nodes"]))
    assert rel_ids == abs_ids


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_deterministic_and_idempotent(name):
    r1 = _tf(name)
    r2 = _tf(name)
    assert transform.serialize(r1) == transform.serialize(r2)  # 确定性
    again = relayout.apply(r1)  # 已是 parent-relative → 原样返回
    assert transform.serialize(again) == transform.serialize(r1)


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_meta_markers(name):
    rel = _tf(name)
    assert rel["_meta"]["coordinateSpace"] == "parent-relative"
    m = rel["_meta"]["relayout"]
    assert set(m) == {"reparented", "adopted", "ambiguousTies",
                      "keptViolations", "zFilter", "zEvidence"}


# ============================================================
# --coords absolute 回滚通道
# ============================================================

@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_coords_absolute_keeps_v05_semantics(name):
    r = _tf(name, coords="absolute")
    assert r["_meta"]["coordinateSpace"] == "absolute-artboard"
    assert "relayout" not in r["_meta"]
    for n, _ in _pairs(r["nodes"]):
        assert "absolutePosition" not in n
        assert "adoptedBy" not in n


def test_coords_absolute_matches_v05_tree_shape():
    """absolute 模式下文本仍是根层兄弟(v0.5 树形不变)。"""
    r = _tf("nested-groups", coords="absolute")
    assert any(n["id"] == TEXT_ID for n in r["nodes"])


# ============================================================
# 类型映射
# ============================================================

def test_mask_real_type_mapped():
    assert transform.REAL_TYPE_TO_V5["mask"] == "MASK"


# ============================================================
# 合成输入:安全网与统计分支(审查 HIGH-2 补齐)
# ============================================================

def _lay(x, y, w, h):
    return {"mode": "none",
            "sizing": {"horizontal": "fixed", "vertical": "fixed"},
            "locationRelativeToParent": {"x": x, "y": y},
            "dimensions": {"width": w, "height": h}}


def _mk(nodes, styles, w=375, h=812):
    return {
        "metadata": {"name": "t", "pageId": "p", "appId": "a",
                     "size": {"width": w, "height": h}},
        "nodes": nodes,
        "globalVars": {"styles": styles},
        "_meta": {"transformVersion": transform.TRANSFORM_VERSION,
                  "coordinateSpace": "absolute-artboard", "warnings": []},
    }


def test_layout_key_never_collides_with_designer_named_token():
    """设计师共享样式名恰好形如 layout_000002 → 新编号必须避开(审查 HIGH-1)。"""
    styles = {
        "L_bg": _lay(0, 0, 200, 100),
        "L_t": _lay(10, 10, 50, 20),
        "layout_000002": {"fontFamily": "PingFang SC", "fontSize": 16},
    }
    nodes = [
        {"id": "t", "type": "TEXT", "layout": "L_t",
         "textStyle": "layout_000002", "text": "x"},
        {"id": "bg", "type": "VECTOR", "layout": "L_bg"},
    ]
    r = relayout.apply(_mk(nodes, styles))
    s = r["globalVars"]["styles"]
    # 撞名 token 内容原封不动,且仍是 textStyle 语义
    assert s["layout_000002"] == {"fontFamily": "PingFang SC", "fontSize": 16}
    # 文本被嵌进背景,其新 layout key 跳过了被占用的 000002
    bg = r["nodes"][0]
    assert bg["id"] == "bg" and bg["children"][0]["id"] == "t"
    t = bg["children"][0]
    assert t["layout"] != "layout_000002"
    assert s[t["layout"]]["locationRelativeToParent"] == {"x": 10, "y": 10}
    assert t["textStyle"] == "layout_000002"


def test_kept_violation_counted_not_modified():
    """子完全在授权父之外且组内无候选 → 维持原位,keptViolations 计数。"""
    styles = {"Lg": _lay(0, 0, 50, 50), "Lo": _lay(200, 200, 30, 10)}
    nodes = [{"id": "grp", "type": "FRAME", "layout": "Lg", "children": [
        {"id": "out", "type": "TEXT", "layout": "Lo", "text": "x"}]}]
    r = relayout.apply(_mk(nodes, styles))
    m = r["_meta"]["relayout"]
    assert m["keptViolations"] == 1 and m["reparented"] == 0
    out = r["nodes"][0]["children"][0]
    assert out["id"] == "out"  # 树形不变
    # rel 仍如实改写(200-0),可逆性优先于包含美观
    assert r["globalVars"]["styles"][out["layout"]]["locationRelativeToParent"] == \
        {"x": 200, "y": 200}


def test_ambiguous_tie_deterministic():
    """两个等面积容器都包含子节点 → ambiguousTies 计数,tie-break 取更贴近的下层。"""
    styles = {"Lt": _lay(10, 10, 10, 10),
              "La": _lay(0, 0, 100, 100), "Lb": _lay(0, 0, 100, 100)}
    nodes = [
        {"id": "t", "type": "TEXT", "layout": "Lt", "text": "x"},
        {"id": "A", "type": "VECTOR", "layout": "La"},
        {"id": "B", "type": "VECTOR", "layout": "Lb"},
    ]
    r1 = relayout.apply(_mk(nodes, styles))
    r2 = relayout.apply(_mk(nodes, styles))
    assert r1["_meta"]["relayout"]["ambiguousTies"] == 1
    winner = r1["nodes"][0]
    assert winner["id"] == "A"  # 距子最近的下方一层(sib 最小的候选)
    assert winner["children"][0]["id"] == "t"
    assert transform.serialize(r1) == transform.serialize(r2)  # 平局也确定性


def test_z_filter_disabled_on_weak_evidence():
    """作用域内包含对方向证据 <80% → 本页禁用 z 过滤 + 告警,退化为纯几何判定。"""
    styles = {"Lbg": _lay(0, 0, 200, 200), "Lt": _lay(10, 10, 10, 10)}
    nodes = [
        {"id": "bg", "type": "VECTOR", "layout": "Lbg"},  # 容器在数组更前(方向反了)
        {"id": "t", "type": "TEXT", "layout": "Lt", "text": "x"},
    ]
    r = relayout.apply(_mk(nodes, styles))
    m = r["_meta"]["relayout"]
    assert m["zFilter"] == "off" and m["zEvidence"] == "0:1"
    assert any("z 方向证据不足" in w for w in r["_meta"]["warnings"])
    assert r["nodes"][0]["children"][0]["id"] == "t"  # 禁用后仍按几何嵌套


def test_abort_falls_back_on_irreversible_floats():
    """可逆性校验失败 → 整体回退 v0.5 语义(树形/坐标原样)+ 告警,绝不输出坏树。"""
    styles = {"Lp": _lay(-1e16, 0, 2e16, 100), "Lc": _lay(1.1, 5, 10, 10)}
    nodes = [{"id": "p", "type": "VECTOR", "layout": "Lp", "children": [
        {"id": "c", "type": "TEXT", "layout": "Lc", "text": "x"}]}]
    src = _mk(nodes, styles)
    r = relayout.apply(src)
    assert r["_meta"]["coordinateSpace"] == "absolute-artboard"
    assert "relayout" not in r["_meta"]
    assert any("不可逆" in w for w in r["_meta"]["warnings"])
    assert r["nodes"] == nodes  # 未被改写
    assert r["globalVars"]["styles"]["Lc"]["locationRelativeToParent"] == \
        {"x": 1.1, "y": 5}


def test_dangling_layout_ref_dropped_with_warning():
    nodes = [{"id": "a", "type": "TEXT", "layout": "nope", "text": "x"}]
    r = relayout.apply(_mk(nodes, {}))
    assert "layout" not in r["nodes"][0]
    assert any("无法解析" in w for w in r["_meta"]["warnings"])


def test_empty_page():
    r = relayout.apply(_mk([], {}))
    assert r["_meta"]["coordinateSpace"] == "parent-relative"
    assert r["_meta"]["relayout"]["reparented"] == 0


def test_adopted_children_order_reflects_true_stacking():
    """收养节点与原生子的顺序 = 原文档层叠真值(先序即自顶向下,两方向都验)。"""
    styles = {"Ll": _lay(45, 45, 10, 10), "Lc": _lay(0, 0, 200, 200),
              "Li": _lay(40, 40, 20, 20)}
    child = {"id": "I", "type": "TEXT", "layout": "Li", "text": "y"}
    stray = {"id": "L", "type": "TEXT", "layout": "Ll", "text": "x"}
    box = {"id": "C", "type": "VECTOR", "layout": "Lc", "children": [dict(child)]}

    # ① stray 在容器子树之前(盖在整组上面)→ 收养后排第一(最顶)
    r = relayout.apply(_mk([dict(stray), dict(box)], dict(styles)))
    assert [c["id"] for c in r["nodes"][0]["children"]] == ["L", "I"]

    # ② stray 在容器子树之后(垫在整组下面;方向证据反 → z 过滤自动关)→ 排最后(最底)
    r2 = relayout.apply(_mk([dict(box), dict(stray)], dict(styles)))
    assert [c["id"] for c in r2["nodes"][0]["children"]] == ["I", "L"]


def test_unexpected_exception_falls_back_to_absolute(monkeypatch):
    """兜底守护:relayout 内部任何未预期异常都不得炸掉导出,整体回退 v0.5 语义。"""
    def _boom(*a, **kw):
        raise RuntimeError("synthetic defect")

    monkeypatch.setattr(relayout, "_contains", _boom)
    src = _tf("simple-text", coords="absolute")
    out = relayout.apply(src)
    assert out["_meta"]["coordinateSpace"] == "absolute-artboard"
    assert "relayout" not in out["_meta"]
    assert any("意外异常" in w and "RuntimeError" in w
               for w in out["_meta"]["warnings"])
    assert out["nodes"] == src["nodes"]  # 原树原样保留


def test_transform_rejects_unknown_coords():
    """coords 非法值必须快失败,不得静默按 absolute 翻转坐标语义。"""
    with pytest.raises(ValueError, match="relative|absolute"):
        _tf("simple-text", coords="relativ")
