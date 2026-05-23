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
        expected_fp.parent.mkdir(exist_ok=True)
        expected_fp.write_text(transform.serialize(actual, fmt="yaml"))
        pytest.fail(f"首次生成 {expected_fp},请 review 后重跑")
    expected = yaml.safe_load(open(expected_fp))
    # 把 actual 也走一遍 yaml 往返,确保 OrderedDict 等结构等价比较
    actual_normalized = yaml.safe_load(transform.serialize(actual, fmt="yaml"))
    assert actual_normalized == expected, f"transform 输出与 {expected_fp} 不一致"


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
