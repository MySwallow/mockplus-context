"""tokens.py(v0.9 设计 token 汇总)单测 + CLI 端到端(页 / 分组 / 全项目,离线缓存)。"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "mockplus-context" / "scripts"
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))
import tokens  # noqa: E402
import transform  # noqa: E402

BODY = {"fontFamily": "PingFang SC", "fontSize": 14, "fontWeight": 400, "fontStyle": "Regular",
        "color": "#262626", "lineHeight": 20, "letterSpacing": 0}


def _page(nodes, styles):
    return {"metadata": {}, "nodes": nodes, "globalVars": {"styles": styles}, "_meta": {}}


def _text(key):
    return {"id": "t", "type": "TEXT", "textStyle": key, "text": "x"}


def test_designer_name_rules():
    styles = {"Body": {}, "Body_2": {}, "Solo_2": {}, "textStyle_000001": {}}
    assert tokens._designer_name("textStyle_000001", styles) is None
    assert tokens._designer_name("Body_2", styles) == "Body", "撞名后缀还原基名"
    assert tokens._designer_name("Solo_2", styles) == "Solo_2", "基名不存在时原样保留"


def test_typography_merges_alignment_and_drops_zero_letter_spacing():
    styles = {
        "Body/左对齐": {**BODY, "textAlignHorizontal": "LEFT"},
        "Body/居中": {**BODY, "textAlignHorizontal": "CENTER"},
        "textStyle_000001": {**BODY, "textAlignHorizontal": "RIGHT"},
    }
    st = tokens.TokenStats()
    st.add_page(_page([_text("Body/左对齐"), _text("Body/左对齐"), _text("Body/居中"),
                       _text("textStyle_000001")], styles))
    (row,) = st.to_dict({"kind": "page"}, [])["typography"]
    assert row["uses"] == 4
    assert row["names"] == ["Body/左对齐", "Body/居中"], "按次数排序,未命名的不进别名"
    assert "letterSpacing" not in row and "textAlignHorizontal" not in row
    assert "fontStyle" not in row, "fontStyle 与 fontWeight 重复,不进 token"


def test_colors_count_roles_across_pages():
    styles = {"fill_000001": ["#FFFFFF"], "stroke_000001": {"width": 1, "color": "#FFFFFF"},
              "Body": BODY}
    page = _page([{"id": "a", "type": "VECTOR", "fills": "fill_000001", "strokes": "stroke_000001"},
                  _text("Body")], styles)
    st = tokens.TokenStats()
    st.add_page(page)
    st.add_page(page)
    out = st.to_dict({"kind": "group"}, [])
    assert out["scope"]["pages"] == 2
    white = next(c for c in out["colors"] if c["value"] == "#FFFFFF")
    assert white["uses"] == 4 and white["roles"] == {"fill": 2, "stroke": 2}
    assert out["colors"][0]["value"] == "#FFFFFF", "按使用次数降序"


def test_radii_normalized_and_gradients_shadows_collected():
    styles = {"fill_000001": [{"type": "GRADIENT_LINEAR", "gradient": "linear-gradient(90deg, #000 0%)"}],
              "effect_000001": {"type": "outside", "offsetY": 2, "blur": 8, "color": "#000000"}}
    nodes = [{"id": "a", "type": "VECTOR", "borderRadius": "8px", "fills": "fill_000001"},
             {"id": "b", "type": "VECTOR", "borderRadius": "8.0px", "effects": "effect_000001"}]
    st = tokens.TokenStats()
    st.add_page(_page(nodes, styles))
    out = st.to_dict({"kind": "page"}, [])
    assert out["radii"] == [{"value": "8px", "uses": 2}]
    assert out["gradients"][0]["uses"] == 1
    assert out["shadows"][0]["blur"] == 8 and out["shadows"][0]["uses"] == 1


def test_empty_sections_dropped_and_failures_recorded():
    st = tokens.TokenStats()
    st.add_page(_page([], {}))
    out = st.to_dict({"kind": "app"}, [{"id": "x", "name": "n", "error": "boom"}])
    assert out["colors"] == [] and "typography" not in out and "radii" not in out
    assert out["_meta"]["pagesFailed"][0]["id"] == "x"


def test_real_fixture_page():
    data = json.loads((FIXTURES / "with-shared-styles.json").read_text(encoding="utf-8"))
    st = tokens.TokenStats()
    st.add_page(transform.transform(data, {"id": "p"}, "a", coords="absolute"))
    out = st.to_dict({"kind": "page"}, [])
    assert out["colors"] and out["typography"]
    assert any("names" in t for t in out["typography"]), "夹具里有设计师命名样式"


# ------------------------------------------------------------
# CLI(离线缓存:pg1 有数据,pg2 缺数据且 dataURL 不可达 → 记为失败页)
# ------------------------------------------------------------

INDEX = {"code": 0, "payload": {"pages": [{
    "_id": "grp", "name": "模块", "isGroup": True, "children": [
        {"_id": "pg1", "name": "页一", "parentID": "grp", "device": "ios1x",
         "size": {"width": 375, "height": 812}, "dataURL": "https://example.invalid/1.json"},
    ]}, {
    "_id": "pg2", "name": "页二", "device": "ios1x",
    "size": {"width": 375, "height": 812}, "dataURL": "https://example.invalid/2.json"},
]}}


@pytest.fixture
def cache_dir(tmp_path):
    (tmp_path / "app1" / "pg1").mkdir(parents=True)
    (tmp_path / "app1" / "_index.json").write_text(
        json.dumps(INDEX, ensure_ascii=False), encoding="utf-8")
    shutil.copy(FIXTURES / "with-shared-styles.json", tmp_path / "app1" / "pg1" / "data.json")
    return tmp_path


def _run(cache, *argv):
    env = {**os.environ, "MOCKPLUS_CACHE_DIR": str(cache), "MOCKPLUS_COOKIE": "fake=1"}
    return subprocess.run([sys.executable, str(SCRIPTS / "mockplus.py"), *argv],
                          env=env, capture_output=True, text=True, encoding="utf-8",
                          cwd=str(ROOT), timeout=120)


def test_cli_tokens_page(cache_dir):
    r = _run(cache_dir, "tokens", "app1:pg1")
    assert r.returncode == 0, r.stderr
    doc = yaml.safe_load(r.stdout)
    assert doc["scope"] == {"kind": "page", "id": "pg1", "name": "页一", "pages": 1}


def test_cli_tokens_group_collects_pages_under_group(cache_dir):
    r = _run(cache_dir, "tokens", "app1:grp", "--format", "json")
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert doc["scope"]["kind"] == "group" and doc["scope"]["pages"] == 1


def test_cli_tokens_app_records_failed_page_and_continues(cache_dir):
    r = _run(cache_dir, "tokens", "app1")
    assert r.returncode == 0, r.stderr
    doc = yaml.safe_load(r.stdout)
    assert doc["scope"]["pages"] == 1
    assert [f["id"] for f in doc["_meta"]["pagesFailed"]] == ["pg2"]
    assert "WARN: 页面 pg2 跳过" in r.stderr


def test_cli_tokens_unknown_target_exits_22(cache_dir):
    r = _run(cache_dir, "tokens", "app1:nope")
    assert r.returncode == 22 and "mockplus tree app1" in r.stderr
