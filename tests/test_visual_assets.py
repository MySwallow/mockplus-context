"""assets.py(v0.9)单测:缺切图检测(missingSlice)、截图裁剪(shot),
以及 CLI 端到端(预热离线缓存 + 本地生成的 design.png,子进程不触网)。"""
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
import assets  # noqa: E402
import cli  # noqa: E402
import distill  # noqa: E402
import scope  # noqa: E402
import transform  # noqa: E402


# ------------------------------------------------------------
# 合成页面:只放判定需要的字段
# ------------------------------------------------------------

def _page(nodes, styles_extra=None):
    """nodes 用 (id, type, name, (x, y, w, h), children, extra) 描述;坐标为相对父。"""
    styles = dict(styles_extra or {})
    seq = [0]

    def build(spec):
        nid, typ, name, (x, y, w, h), kids, extra = spec
        seq[0] += 1
        key = f"layout_{seq[0]:06d}"
        styles[key] = {"mode": "none",
                       "locationRelativeToParent": {"x": x, "y": y},
                       "dimensions": {"width": w, "height": h}}
        node = {"id": nid, "name": name, "type": typ, "layout": key, **(extra or {})}
        if kids:
            node["children"] = [build(k) for k in kids]
        return node

    return {
        "metadata": {"name": "p", "pageId": "p1", "size": {"width": 375, "height": 812}},
        "nodes": [build(s) for s in nodes],
        "globalVars": {"styles": styles},
        "_meta": {"coordinateSpace": "parent-relative"},
    }


def _by_id(result):
    return {n["id"]: n for n, _d, _b, _a in scope._walk(result)}


PATH = ("P1", "VECTOR", "路径", (0, 0, 16, 16), None, None)


def test_icon_named_instance_without_slice_is_marked_before_children():
    r = _page([("I1", "INSTANCE", "icon/箭头-右", (10, 10, 16, 16), [PATH], None)])
    out = assets.mark_missing_slices(r)
    node = _by_id(out)["I1"]
    assert node["missingSlice"] == "icon"
    assert list(node)[-2:] == ["missingSlice", "children"]
    assert "missingSlice" not in _by_id(out)["P1"], "只标最外层命中节点"


def test_icon_with_slice_in_subtree_is_not_marked():
    img = {"fill_000001": [{"type": "IMAGE", "imageRef": "abc", "scaleMode": "FILL"}]}
    sliced = ("P1", "VECTOR", "路径", (0, 0, 16, 16), None, {"fills": "fill_000001"})
    r = _page([("I1", "INSTANCE", "icon/删除", (0, 0, 16, 16), [sliced], None)], img)
    assert assets.missing_counts(assets.mark_missing_slices(r)) == {"icon": 0, "vector": 0}


def test_wide_container_named_arrow_recurses_to_real_icon():
    inner = ("I2", "INSTANCE", "icon/箭头-右", (50, 4, 12, 12), [PATH], None)
    r = _page([("C1", "INSTANCE", "04表单/02后缀/箭头", (0, 0, 62, 20), [inner], None)])
    out = _by_id(assets.mark_missing_slices(r))
    assert "missingSlice" not in out["C1"]
    assert out["I2"]["missingSlice"] == "icon"


@pytest.mark.parametrize("spec,expected", [
    (("V1", "VECTOR", "路径", (0, 0, 16, 16), None, None), "vector"),
    (("V1", "VECTOR", "形状结合", (0, 0, 11, 18), None, None), "vector"),   # 0.61:窄箭头仍算
    (("V1", "VECTOR", "矩形", (0, 0, 16, 16), None, None), None),          # CSS 可画的基本形
    (("V1", "VECTOR", "路径", (0, 0, 20, 40), None, None), None),          # 柱状图柱子
    (("V1", "VECTOR", "路径", (0, 0, 60, 60), None, None), None),          # 超尺寸
    (("V1", "VECTOR", "路径", (0, 0, 4, 4), None, None), None),            # 太小(圆点)
    (("S1", "INSTANCE", "07按钮/05开关/小/开", (0, 0, 40, 30), [PATH], None), None),
])
def test_vector_heuristic(spec, expected):
    out = _by_id(assets.mark_missing_slices(_page([spec])))
    assert out[spec[0]].get("missingSlice") == expected


def test_status_bar_subtree_is_skipped():
    status = ("SB", "INSTANCE", "01导航栏/02状态栏/白底", (0, 0, 375, 20),
              [("B1", "VECTOR", "Battery", (340, 4, 24, 12), None, None),
               ("W1", "VECTOR", "路径", (300, 4, 16, 12), None, None)], None)
    assert assets.missing_counts(assets.mark_missing_slices(_page([status]))) == \
        {"icon": 0, "vector": 0}


def test_group_with_text_is_not_icon_but_its_icon_child_is():
    """图标 + 文字标签的组合:整组不算图标,组内的矢量图标单独标出。"""
    texty = ("G1", "FRAME", "编组", (0, 100, 40, 40),
             [PATH, ("T1", "TEXT", "x", (0, 20, 20, 10), None, {"text": "x"})], None)
    out = _by_id(assets.mark_missing_slices(_page([texty])))
    assert "missingSlice" not in out["G1"]
    assert out["P1"]["missingSlice"] == "vector"


def test_mark_does_not_mutate_input_and_note():
    r = _page([("I1", "INSTANCE", "icon/删除", (0, 0, 16, 16), [PATH], None)])
    before = copy.deepcopy(r)
    out = assets.mark_missing_slices(r)
    assert r == before
    assert "1 个疑似图标没有切图" in assets.missing_slice_note(out)
    assert assets.missing_slice_note(r) is None


def test_counts_follow_node_scope():
    """计数按节点现数:--node 裁掉的缺切图节点不再计入(不存 _meta,不会失真)。"""
    a = ("I1", "INSTANCE", "icon/删除", (0, 0, 16, 16), [PATH], None)
    b = ("F1", "FRAME", "卡片", (0, 100, 200, 100),
         [("I2", "INSTANCE", "icon/添加", (10, 10, 16, 16), [PATH], None)], None)
    marked = assets.mark_missing_slices(_page([a, b]))
    sub, _ = scope.select(marked, ["F1"])
    assert assets.missing_counts(marked)["icon"] == 2
    assert assets.missing_counts(sub)["icon"] == 1


def test_marked_real_fixture_still_distills():
    data = json.loads((FIXTURES / "nested-groups.json").read_text(encoding="utf-8"))
    marked = assets.mark_missing_slices(transform.transform(data, {"id": "p"}, "a"))
    out, _ = distill.apply_text(transform.serialize(marked))
    assert yaml.safe_load(out)["_meta"]["distilled"] is True


# ------------------------------------------------------------
# 截图裁剪
# ------------------------------------------------------------

def test_px_box_scales_pads_and_clips():
    assert assets.px_box((10, 20, 16, 16), 2, 0, 750, 1624) == (20, 40, 32, 32)
    assert assets.px_box((10, 20, 16, 16), 2, 4, 750, 1624) == (12, 32, 48, 48)
    assert assets.px_box((-5, -5, 20, 20), 2, 0, 750, 1624) == (0, 0, 30, 30)
    assert assets.px_box((400, 900, 20, 20), 2, 0, 750, 1624) is None


def test_png_size_rejects_non_png(tmp_path):
    bad = tmp_path / "x.png"
    bad.write_bytes(b"not a png at all, definitely")
    with pytest.raises(assets.CropError):
        assets.png_size(bad)


def _make_png(path: Path, size=(100, 60)):
    Image = pytest.importorskip("PIL.Image")
    im = Image.new("RGB", size, "white")
    im.paste((255, 0, 0), (10, 20, 40, 50))
    im.save(path)


def test_crop_with_pillow(tmp_path):
    src, dest = tmp_path / "s.png", tmp_path / "d.png"
    _make_png(src)
    assert assets.png_size(src) == (100, 60)
    assert assets.crop_png(src, dest, (10, 20, 30, 30)) == "pillow"
    assert assets.png_size(dest) == (30, 30)


def test_crop_without_pillow_uses_sips_or_explains(tmp_path, monkeypatch):
    src, dest = tmp_path / "s.png", tmp_path / "d.png"
    _make_png(src)
    monkeypatch.setitem(sys.modules, "PIL", None)  # 模拟没装 Pillow
    if sys.platform == "darwin" and shutil.which("sips"):
        assert assets.crop_png(src, dest, (10, 20, 30, 30)) == "sips"
        assert assets.png_size(dest) == (30, 30)
    else:
        with pytest.raises(assets.CropError, match="Pillow"):
            assets.crop_png(src, dest, (10, 20, 30, 30))


# ------------------------------------------------------------
# CLI 端到端(shot / data 的缺切图提示)
# ------------------------------------------------------------

INDEX = {"code": 0, "payload": {"pages": [{
    "_id": "pg1", "name": "测试页", "device": "ios1x",
    "size": {"width": 375, "height": 812},
    "dataURL": "https://example.com/pg1.json",
    "imageURL": "https://example.com/pg1.png",
}]}}


@pytest.fixture
def cache_dir(tmp_path):
    page = tmp_path / "app1" / "pg1"
    page.mkdir(parents=True)
    (tmp_path / "app1" / "_index.json").write_text(
        json.dumps(INDEX, ensure_ascii=False), encoding="utf-8")
    shutil.copy(FIXTURES / "nested-groups.json", page / "data.json")
    _make_png(page / "design.png", size=(750, 1624))
    t = (page / "data.json").stat().st_mtime + 10  # 截图比页面数据新 → 不触发重下
    os.utime(page / "design.png", (t, t))
    return tmp_path


def _run(cache, *argv):
    env = {**os.environ, "MOCKPLUS_CACHE_DIR": str(cache), "MOCKPLUS_COOKIE": "fake=1"}
    return subprocess.run([sys.executable, str(SCRIPTS / "mockplus.py"), *argv],
                          env=env, capture_output=True, text=True, encoding="utf-8",
                          cwd=str(ROOT))


def test_cli_shot_node_crops_at_detected_scale(cache_dir, tmp_path):
    out = tmp_path / "shots"
    r = _run(cache_dir, "shot", "app1:pg1", "--node", "FACADE03", "--out", str(out))
    assert r.returncode == 0, r.stderr
    data = json.loads((FIXTURES / "nested-groups.json").read_text(encoding="utf-8"))
    res = transform.transform(data, {"id": "pg1"}, "app1")
    (_node, box), = scope.locate(res, ["FACADE03"])
    w, h = assets.png_size(out / "FACADE03.png")
    assert (w, h) == (round(box[2] * 2), round(box[3] * 2))
    assert "@2x" in r.stdout


def test_cli_shot_without_node_copies_full_design(cache_dir, tmp_path):
    out = tmp_path / "shots"
    r = _run(cache_dir, "shot", "app1:pg1", "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert assets.png_size(out / "design.png") == (750, 1624)


def test_cli_shot_unknown_node_exits_23(cache_dir, tmp_path):
    r = _run(cache_dir, "shot", "app1:pg1", "--node", "DEADBEEF", "--out", str(tmp_path))
    assert r.returncode == 23


def test_cli_shot_page_without_image_exits_24(cache_dir, tmp_path):
    idx = copy.deepcopy(INDEX)
    idx["payload"]["pages"][0]["imageURL"] = ""
    (cache_dir / "app1" / "_index.json").write_text(json.dumps(idx), encoding="utf-8")
    r = _run(cache_dir, "shot", "app1:pg1", "--node", "FACADE03", "--out", str(tmp_path))
    assert r.returncode == 24 and "imageURL" in r.stderr


# ------------------------------------------------------------
# 截图缓存:原子替换 + 重下失败沿用旧图;文件名防穿越
# ------------------------------------------------------------

@pytest.fixture
def design_cache(tmp_path, monkeypatch):
    page = tmp_path / "app1" / "pg1"
    page.mkdir(parents=True)
    (page / "data.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli.client, "cache_root", lambda: tmp_path)
    return page


def _fake_download(ok: bool):
    def download(_page_meta, dest):
        if ok:
            dest.write_bytes(b"NEW")
        return ok
    return download


def _make_stale(page):
    (page / "design.png").write_bytes(b"OLD")
    t = (page / "data.json").stat().st_mtime - 10  # 截图比页面数据旧 → 需要重下
    os.utime(page / "design.png", (t, t))


def test_design_png_redownload_replaces_atomically(design_cache, monkeypatch):
    _make_stale(design_cache)
    (design_cache / "design.png.part").write_bytes(b"STALE-PART")  # 上次中断残留
    monkeypatch.setattr(cli.client, "download_page_image", _fake_download(True))
    path = cli._ensure_design_png("app1", {"id": "pg1"}, refresh=False)
    assert path.read_bytes() == b"NEW"
    assert not (design_cache / "design.png.part").exists()


def test_design_png_redownload_failure_keeps_old(design_cache, monkeypatch, capsys):
    _make_stale(design_cache)
    monkeypatch.setattr(cli.client, "download_page_image", _fake_download(False))
    path = cli._ensure_design_png("app1", {"id": "pg1"}, refresh=False)
    assert path.read_bytes() == b"OLD"
    assert "沿用旧截图" in capsys.readouterr().err


def test_design_png_first_download_failure_raises(design_cache, monkeypatch):
    monkeypatch.setattr(cli.client, "download_page_image", _fake_download(False))
    with pytest.raises(assets.CropError, match="下载失败"):
        cli._ensure_design_png("app1", {"id": "pg1"}, refresh=False)


def test_fresh_design_png_is_not_redownloaded(design_cache, monkeypatch):
    (design_cache / "design.png").write_bytes(b"OLD")
    t = (design_cache / "data.json").stat().st_mtime + 10
    os.utime(design_cache / "design.png", (t, t))

    def boom(*_a):
        raise AssertionError("新鲜截图不该重下")
    monkeypatch.setattr(cli.client, "download_page_image", boom)
    assert cli._ensure_design_png("app1", {"id": "pg1"}, refresh=False).read_bytes() == b"OLD"


@pytest.mark.parametrize("raw,safe", [
    ("AB12CD08", "AB12CD08"),
    ("04553673-D1D3-40A3-91D2-79FD08A9114C", "04553673-D1D3-40A3-91D2-79FD08A9114C"),
    ("../../etc/x", "______etc_x"),
    ("a/b\\c", "a_b_c"),
    ("", "_"),
])
def test_safe_filename(raw, safe):
    assert cli._safe_filename(raw) == safe
