import sys
from pathlib import Path
import json

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _schema import validate_lite, validate_full

EXPECTED = Path(__file__).parent / "fixtures" / "expected"


def test_validate_lite_on_all_fixtures():
    for fp in EXPECTED.glob("*.json"):
        validate_lite(json.load(open(fp)))


def test_validate_full_on_all_fixtures():
    # 装了 jsonschema 时跑严格校验,否则 no-op
    for fp in EXPECTED.glob("*.json"):
        validate_full(json.load(open(fp)))


def test_validate_lite_rejects_missing_metadata():
    with pytest.raises(ValueError, match="missing top-level key 'metadata'"):
        validate_lite({"globalVars": {}, "nodes": [], "_meta": {}})


def test_validate_lite_rejects_wrong_bounds():
    """bounds 用 {x,y,w,h} 应该被拒。"""
    bad = {
        "metadata": {"appId": "x", "pageId": "y", "canvas": {"width": 1, "height": 1}},
        "globalVars": {"styles": {}, "sharedStyles": {}},
        "nodes": [{
            "id": "n1", "type": "rect", "realType": "ShapePath",
            "bounds": {"x": 0, "y": 0, "w": 100, "h": 50},  # 错的字段名
        }],
        "_meta": {},
    }
    with pytest.raises(ValueError, match="missing 'top'"):
        validate_lite(bad)
