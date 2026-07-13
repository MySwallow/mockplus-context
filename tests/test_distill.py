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
