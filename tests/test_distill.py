"""distill.py 单测:UUID 截断的 YAML 数字形歧义防护(v0.7 补丁)。

背景:distill 是文本级替换,截断出的 8 位 id 不带引号。若前 8 位恰为
YAML 1.1 数字形(八进制 `03450216`、纯数字 `12345678`、浮点形 `1234E567`),
safe_load 会把 id 读成 int/float——id 锚点静默变类型。策略:此类 id 保留全 UUID。
fc 实测:2600 节点命中 2 个(库存盘点新建页 03450216、看板页 04553673)。
"""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "mockplus-context" / "scripts"))
import distill  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "expected" / "nested-groups.yaml"

# 与 fixture 内 FACADE15 同形的歧义 UUID(前 8 位分别为八进制形/纯数字/浮点形)
OCTAL_UUID = "03450216-574D-4B8E-9FD1-04A226A0D287"
DIGIT_UUID = "12345678-0000-4000-8000-000000000000"
FLOAT_UUID = "1234E567-0000-4000-8000-000000000000"
NORMAL_KEPT = "FACADE08"  # fixture 里的正常 id,应照常截断


def _swap(src: str, old_prefix: str, new_uuid: str) -> str:
    """把 fixture 里某个合成 UUID 整体替换为目标 UUID。"""
    import re
    m = re.search(rf"{old_prefix}-[0-9A-Fa-f-]+", src)
    assert m, f"fixture 中找不到 {old_prefix}"
    return src.replace(m.group(0), new_uuid)


def test_ambiguous_prefix_keeps_full_uuid():
    src = FIXTURE.read_text()
    src = _swap(src, "FACADE15", OCTAL_UUID)
    out, stats = distill.apply_text(src)
    assert OCTAL_UUID in out, "八进制形前缀的 id 必须保留全 UUID"
    assert f"id: {NORMAL_KEPT}\n" in out or f"id: {NORMAL_KEPT}" in out, "正常 id 仍应截断"
    assert stats["uuids_kept_full"] == 1


def test_ambiguous_ids_stay_strings_after_roundtrip():
    src = FIXTURE.read_text()
    src = _swap(src, "FACADE15", OCTAL_UUID)
    src = _swap(src, "FACADE11", DIGIT_UUID)
    src = _swap(src, "FACADE13", FLOAT_UUID)
    out, stats = distill.apply_text(src)
    assert stats["uuids_kept_full"] == 3
    doc = yaml.safe_load(out)

    ids = []

    def walk(n):
        if isinstance(n, dict):
            if "id" in n:
                ids.append(n["id"])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for i in n:
                walk(i)

    walk(doc["nodes"])
    non_str = [i for i in ids if not isinstance(i, str)]
    assert not non_str, f"蒸馏产物 round-trip 后出现非字符串 id: {non_str}"
    assert OCTAL_UUID in ids and DIGIT_UUID in ids and FLOAT_UUID in ids


def test_clean_fixture_all_shortened_and_invariants_hold():
    src = FIXTURE.read_text()
    out, stats = distill.apply_text(src)
    assert stats["uuids_kept_full"] == 0
    assert stats["uuids"] > 0
    doc = yaml.safe_load(out)
    assert doc["_meta"]["distilled"] is True


def test_prefix_collision_still_aborts():
    src = FIXTURE.read_text()
    # 两个不同 UUID 共享前 8 位(均非数字形)→ 应整体放弃
    src = _swap(src, "FACADE15", "ABCDEF01-1111-4111-8111-111111111111")
    src = _swap(src, "FACADE11", "ABCDEF01-2222-4222-8222-222222222222")
    with pytest.raises(distill.DistillError, match="碰撞"):
        distill.apply_text(src)


def test_legacy_coordinate_space_warned():
    """输入无 coordinateSpace: parent-relative(v0.5 历史文件/relayout 回退/--coords absolute)
    → _meta.distillWarnings 警示 + stats 标记;正常 v0.6+ 输入无警示。"""
    src = FIXTURE.read_text()
    assert "coordinateSpace: parent-relative" in src
    out, stats = distill.apply_text(src)
    assert stats["legacy_coordinate_space"] is False
    assert "distillWarnings" not in out

    legacy = src.replace("  coordinateSpace: parent-relative\n", "")
    out2, stats2 = distill.apply_text(legacy)
    assert stats2["legacy_coordinate_space"] is True
    doc = yaml.safe_load(out2)
    warns = doc["_meta"]["distillWarnings"]
    assert isinstance(warns, list) and any("勿当相对父坐标" in w for w in warns)


# ------------------------------------------------------------
# v0.8 去噪:abs 行内化 / 单色 fill 直写 / 图层名去噪 + 出口语义比对
# ------------------------------------------------------------

EXPECTED_DIR = FIXTURE.parent


def _nodes_by_id(doc):
    out = {}

    def walk(ns):
        for n in ns or []:
            out[n["id"]] = n
            walk(n.get("children"))
    walk(doc["nodes"])
    return out


def test_abs_block_inlined():
    src = FIXTURE.read_text(encoding="utf-8")
    out, stats = distill.apply_text(src)
    assert "absolutePosition:" not in out
    assert "  abs: {x: 0, y: 428}\n" in out
    assert stats["abs_inlined"] == src.count("absolutePosition:")


def test_solid_fill_inlined_and_defs_removed():
    out, stats = distill.apply_text(FIXTURE.read_text(encoding="utf-8"))
    doc = yaml.safe_load(out)
    nodes = _nodes_by_id(doc)
    assert nodes["FACADE08"]["fills"] == "#F5F5F5"
    assert not any(k.startswith("fill_") for k in doc["globalVars"]["styles"]), \
        "该夹具的 fill 全是单色,定义应全部删掉"
    assert stats["fills_inlined"] > 0


@pytest.mark.parametrize("fixture", ["with-gradients.yaml", "with-slices.yaml"])
def test_gradient_and_image_fills_stay_as_refs(fixture):
    src = (EXPECTED_DIR / fixture).read_text(encoding="utf-8")
    out, _ = distill.apply_text(src)
    doc = yaml.safe_load(out)
    styles = doc["globalVars"]["styles"]
    for n in _nodes_by_id(doc).values():
        f = n.get("fills")
        if isinstance(f, str) and f.startswith("fill_"):
            assert f in styles
            assert isinstance(styles[f][0], dict), "留作引用的只能是渐变/切图"
    assert out.count("imageRef") == src.count("imageRef")


def test_auto_and_same_as_text_names_dropped():
    out, stats = distill.apply_text(FIXTURE.read_text(encoding="utf-8"))
    nodes = _nodes_by_id(yaml.safe_load(out))
    for nid in ("FACADE08", "FACADE16", "FACADE02"):  # Rectangle / Path / Shape
        assert "name" not in nodes[nid]
    assert "name" not in nodes["FACADE15"], "TEXT 图层名 == 文本内容,应删"
    assert nodes["FACADE04"]["name"] == "Inside Page", "TEXT 图层名 != 文本内容,保留"
    assert nodes["FACADE11"]["name"] == "Home Indicator"
    assert stats["names_dropped"] == {"auto": 3, "sameAsText": 1}


@pytest.mark.parametrize("name", [
    "编组", "编组 2", "矩形备份 3", "编组 2备份 3", "Rectangle 2 Copy 2备份 6",
    "矩形 copy备份 2", "Group", "Rectangle Copy", "形状结合", "椭圆形", "路径备份"])
def test_is_auto_name_positive(name):
    assert distill.is_auto_name(name)


@pytest.mark.parametrize("name", [
    "背景", "编组标题", "Lines", "Rectangle Copy [6 16]", "商品卡片", "层叠 3",
    "Home Indicator", "", None, 12])
def test_is_auto_name_negative(name):
    assert not distill.is_auto_name(name)


@pytest.mark.parametrize("fixture", sorted(p.name for p in EXPECTED_DIR.glob("*.yaml")))
def test_every_fixture_distills_and_passes_semantic_check(fixture):
    src = (EXPECTED_DIR / fixture).read_text(encoding="utf-8")
    out, _ = distill.apply_text(src)
    assert yaml.safe_load(out)["_meta"]["distillVersion"] == 2


def test_semantic_check_catches_wrongly_dropped_name(monkeypatch):
    """文本级去噪若误删有语义的图层名,出口语义比对必须整体拒绝。"""
    def bad_drop(text):
        return text.replace("  name: Home Indicator\n", ""), 0, 0
    monkeypatch.setattr(distill, "_drop_names", bad_drop)
    with pytest.raises(distill.DistillError, match="误删"):
        distill.apply_text(FIXTURE.read_text(encoding="utf-8"))


def test_uuid_inside_text_content_aborts_instead_of_rewriting():
    """文本内容里夹带 UUID 时,全局截断会改写文本——语义比对拒绝,回退未蒸馏原文。"""
    src = FIXTURE.read_text(encoding="utf-8").replace(
        "text: Submit\n", "text: order ABCDEF01-1111-4111-8111-111111111111\n")
    with pytest.raises(distill.DistillError, match="语义比对"):
        distill.apply_text(src)


def test_uuid_map_matches_distilled_ids():
    src = FIXTURE.read_text(encoding="utf-8")
    out, _ = distill.apply_text(src)
    id_map = distill.uuid_map(src)
    assert id_map["FACADE08-0000-4000-8000-000000000000"] == "FACADE08"
    assert set(_nodes_by_id(yaml.safe_load(out))) <= set(id_map.values())
