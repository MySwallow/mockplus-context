"""scope.py(v0.8 两级取数)单测:--node 子树裁剪、outline 大纲、token 预算提示,
以及 CLI 端到端(预热离线缓存,子进程不触网)。"""
import copy
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
import mockplus  # noqa: E402
import scope  # noqa: E402
import transform  # noqa: E402

PAGE_META = {"id": "p-test", "name": "test", "path": "test"}
TEXT_ID = "FACADE15-0000-4000-8000-000000000000"      # Rectangle(0,428) 内的 TEXT,rel (155,12)
RECT_ID = "FACADE08-0000-4000-8000-000000000000"      # 容器 VECTOR,abs (0,428)
INSTANCE_ID = "FACADE03-0000-4000-8000-000000000000"  # INSTANCE 容器,abs (0,718)


@pytest.fixture
def result():
    data = json.loads((FIXTURES / "nested-groups.json").read_text(encoding="utf-8"))
    return transform.transform(data, PAGE_META, "test-app")


# ------------------------------------------------------------
# select(--node)
# ------------------------------------------------------------

def test_select_leaf_gets_canvas_abs_and_only_referenced_styles(result):
    out, notes = scope.select(result, ["FACADE15"])
    assert notes == []
    (root,) = out["nodes"]
    assert root["id"] == TEXT_ID
    assert root["absolutePosition"] == {"x": 155, "y": 440}  # 父 abs (0,428) + rel (155,12)
    assert list(root).index("absolutePosition") == list(root).index("layout") + 1
    assert set(out["globalVars"]["styles"]) == {root["layout"], root["textStyle"]}
    assert "components" not in out["metadata"], "子树不含 INSTANCE,组件注册表应清空"
    assert out["_meta"]["scope"]["nodes"] == [TEXT_ID]


def test_select_container_keeps_components_it_uses(result):
    out, _ = scope.select(result, [INSTANCE_ID])
    assert out["nodes"][0]["absolutePosition"] == {"x": 0, "y": 718}
    assert list(out["metadata"]["components"]) == [out["nodes"][0]["componentId"]]


def test_select_accepts_lowercase_prefix_and_full_uuid(result):
    a, _ = scope.select(result, ["facade15"])
    b, _ = scope.select(result, [TEXT_ID])
    assert a["nodes"][0]["id"] == b["nodes"][0]["id"] == TEXT_ID


def test_select_skips_descendant_of_selected_ancestor(result):
    out, notes = scope.select(result, [RECT_ID, TEXT_ID])
    assert [n["id"] for n in out["nodes"]] == [RECT_ID]
    assert len(notes) == 1 and "祖先" in notes[0]


@pytest.mark.parametrize("query,match", [
    ("DEADBEEF", "不存在"),
    ("FAC", "太短"),
])
def test_select_errors_are_actionable(result, query, match):
    with pytest.raises(scope.ScopeError, match=match):
        scope.select(result, [query])


def test_select_ambiguous_prefix_lists_candidates(result):
    r = copy.deepcopy(result)
    r["nodes"][1]["id"] = "FACADE15-9999-4000-8000-000000000000"  # 与 TEXT_ID 共享前 8 位
    with pytest.raises(scope.ScopeError, match="匹配到 2 个"):
        scope.select(r, ["FACADE15"])


def test_select_does_not_mutate_input(result):
    before = copy.deepcopy(result)
    scope.select(result, ["FACADE15", INSTANCE_ID])
    assert result == before


def test_selected_subtree_survives_distill(result):
    import distill
    out, _ = scope.select(result, [INSTANCE_ID])
    text, _ = distill.apply_text(transform.serialize(out))
    doc = yaml.safe_load(text)
    assert doc["nodes"][0]["abs"] == {"x": 0, "y": 718}
    assert doc["_meta"]["scope"]["nodes"] == ["FACADE03"]


# ------------------------------------------------------------
# outline
# ------------------------------------------------------------

def test_outline_lists_containers_and_top_level_in_reading_order(result):
    import distill
    id_map = distill.uuid_map(transform.serialize(result))
    text = scope.render_outline(result, id_map, page_tokens=1234, fetch_hint="HINT")
    lines = text.splitlines()
    assert lines[0].startswith("# 页面: test (p-test)") and "1234 token" in lines[0]
    assert lines[2] == "# 下钻: HINT"
    body = lines[3:]
    assert len(body) == len(result["nodes"]), "该夹具顶层 9 个节点,只有顶层,嵌套里无容器"
    ys = [float(ln.split("@")[1].split(",")[1].split(" ")[0]) for ln in body]
    assert ys == sorted(ys), "同级应按 y 从上到下"
    rect = next(ln for ln in body if "#FACADE08" in ln)
    assert '"Rectangle"' not in rect, "自动命名不显示"
    assert "n=1" in rect and 'text="No more items"' in rect
    assert "-0000-" not in text, "id 应与蒸馏产物一致(短 id)"


def test_outline_depth_zero_hides_nested(result):
    text = scope.render_outline(result, max_depth=0)
    assert all(not ln.startswith("  ") for ln in text.splitlines())


# ------------------------------------------------------------
# token 预算
# ------------------------------------------------------------

def test_estimate_tokens_counts_cjk_as_one():
    assert scope.estimate_tokens("中文字") == 3
    assert scope.estimate_tokens("a" * 32) == 10


def test_budget_hint_points_to_outline_then_node():
    assert scope.budget_hint("x" * 100, "A:P", scoped=False, budget=1000) is None
    msg = scope.budget_hint("x" * 10000, "A:P", scoped=False, budget=1000)
    assert "mockplus outline A:P" in msg and "--node" in msg
    scoped = scope.budget_hint("x" * 10000, "A:P", scoped=True, budget=1000)
    assert "更小的子区块" in scoped


# ------------------------------------------------------------
# CLI(参数面 + 离线端到端)
# ------------------------------------------------------------

def test_parser_data_node_and_outline_depth():
    p = mockplus.build_parser()
    assert p.parse_args(["data", "a:b", "--node", "X1,X2"]).node == "X1,X2"
    assert p.parse_args(["data", "a:b"]).node is None
    assert p.parse_args(["outline", "a:b", "--depth", "2"]).depth == 2
    with pytest.raises(SystemExit):
        p.parse_args(["outline", "a:b", "--depth", "-1"])


INDEX = {"code": 0, "payload": {"pages": [{
    "_id": "pg1", "name": "测试页", "device": "ios1x",
    "size": {"width": 375, "height": 812},
    "dataURL": "https://example.com/pg1.json",
}]}}


@pytest.fixture
def cache_dir(tmp_path):
    (tmp_path / "app1" / "pg1").mkdir(parents=True)
    (tmp_path / "app1" / "_index.json").write_text(
        json.dumps(INDEX, ensure_ascii=False), encoding="utf-8")
    shutil.copy(FIXTURES / "nested-groups.json", tmp_path / "app1" / "pg1" / "data.json")
    return tmp_path


def _run(cache, *argv):
    env = {**os.environ, "MOCKPLUS_CACHE_DIR": str(cache), "MOCKPLUS_COOKIE": "fake=1"}
    return subprocess.run([sys.executable, str(SCRIPTS / "mockplus.py"), *argv],
                          env=env, capture_output=True, text=True, encoding="utf-8",
                          cwd=str(ROOT))


def test_cli_outline(cache_dir):
    r = _run(cache_dir, "outline", "app1:pg1")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("# 页面: 测试页 (pg1)")
    assert "mockplus data app1:pg1 --node" in r.stdout
    assert "#FACADE08" in r.stdout


def test_cli_data_node(cache_dir):
    r = _run(cache_dir, "data", "app1:pg1", "--node", "FACADE03")
    assert r.returncode == 0, r.stderr
    doc = yaml.safe_load(r.stdout)
    assert [n["id"] for n in doc["nodes"]] == ["FACADE03"]
    assert doc["_meta"]["distilled"] is True


def test_cli_data_node_unknown_exits_23(cache_dir):
    r = _run(cache_dir, "data", "app1:pg1", "--node", "DEADBEEF")
    assert r.returncode == 23
    assert "mockplus outline" in r.stderr
