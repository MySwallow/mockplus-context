"""transform 黄金对照测试。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "mockplus-context" / "scripts"))
from _transform import transform


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
    actual = transform(data, FAKE_PAGE_META, "test-app")
    expected_fp = EXPECTED / f"{name}.json"
    if not expected_fp.exists():
        # 首次跑: 写黄金值供 review,测试失败强制人工 review
        expected_fp.parent.mkdir(exist_ok=True)
        expected_fp.write_text(json.dumps(actual, ensure_ascii=False, indent=2))
        pytest.fail(f"首次生成 {expected_fp},请 review 后重跑")
    expected = json.load(open(expected_fp))
    assert actual == expected, f"transform 输出与 {expected_fp} 不一致"


def test_transform_tolerates_missing_basic():
    """T17 容错降级:节点缺 basic 不应 crash。"""
    bad_data = {
        "layers": {
            "children": [
                {"bounds": {"left": 0, "top": 0, "width": 100, "height": 50}}
            ]
        },
        "size": {"width": 375, "height": 812},
    }
    out = transform(bad_data, FAKE_PAGE_META, "test-app")
    assert len(out["nodes"]) == 1
