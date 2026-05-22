import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _api
import _tree


SAMPLE = json.load(open(Path(__file__).parent / "fixtures" / "_index-sample.json"))


def test_flatten_pages_extracts_2_pages_2_groups():
    pages, groups = _api.flatten_pages(SAMPLE)
    assert len(pages) == 2
    assert len(groups) == 2
    assert {p["id"] for p in pages} == {"p-001", "p-003"}


def test_tree_text_format_lists_all_nodes(capsys):
    with patch("_tree.fetch_index", return_value=SAMPLE):
        class Args:
            app_id = "appX"
            format = "text"
            refresh = False
        _tree.cmd_tree(Args())
    out = capsys.readouterr().out
    assert "📁 v1" in out
    assert "📁 采购模块" in out
    assert "📄 申请页" in out
    assert "📄 首页" in out
    # 混合树:首页 跟 采购模块 同级,缩进相同
    lines = out.splitlines()
    indent_caigou = next(l for l in lines if "采购模块" in l).split("📁")[0]
    indent_shouye = next(l for l in lines if "首页" in l).split("📄")[0]
    assert indent_caigou == indent_shouye


def test_tree_json_format_returns_structured(capsys):
    with patch("_tree.fetch_index", return_value=SAMPLE):
        class Args:
            app_id = "appX"
            format = "json"
            refresh = False
        _tree.cmd_tree(Args())
    out = json.loads(capsys.readouterr().out)
    assert out[0]["id"] == "g-root"
    assert out[0]["kind"] == "group"
    children = out[0]["children"]
    assert any(c["id"] == "g-sub1" and c["kind"] == "group" for c in children)
    assert any(c["id"] == "p-003" and c["kind"] == "page" for c in children)
