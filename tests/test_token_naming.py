"""TokenTable 命名策略测试(spec §6.1)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "skills" / "mockplus-context" / "scripts"))
import transform as T


def test_fill_uses_6_digit_seq():
    tt = T.TokenTable()
    k = tt.fill_solid({"value": {"r": 255, "g": 0, "b": 0, "a": 1}})
    assert k == "fill_000001"


def test_textstyle_uses_shared_style_name():
    tt = T.TokenTable()
    spec = {"font": {"size": 16, "color": {"value": {"r": 0, "g": 0, "b": 0, "a": 1}}}}
    k = tt.text_style(spec, preferred_name="01文字色1/16px/semibold/居中对齐 Style")
    assert k == "01文字色1/16px/semibold/居中对齐 Style"


def test_textstyle_falls_back_to_seq_when_no_shared():
    tt = T.TokenTable()
    spec = {"font": {"size": 16, "color": {"value": {"r": 0, "g": 0, "b": 0, "a": 1}}}}
    k = tt.text_style(spec)
    assert k == "textStyle_000001"


def test_textstyle_same_name_same_spec_reuses_key():
    tt = T.TokenTable()
    spec = {"font": {"size": 16, "color": {"value": {"r": 0, "g": 0, "b": 0, "a": 1}}}}
    k1 = tt.text_style(spec, preferred_name="MyStyle")
    k2 = tt.text_style(spec, preferred_name="MyStyle")
    assert k1 == k2 == "MyStyle"


def test_textstyle_same_name_diff_spec_adds_suffix():
    """两个 sharedStyle 同名但 spec 不同 → 后到的加 _2。"""
    tt = T.TokenTable()
    spec1 = {"font": {"size": 16, "color": {"value": {"r": 0, "g": 0, "b": 0, "a": 1}}}}
    spec2 = {"font": {"size": 18, "color": {"value": {"r": 0, "g": 0, "b": 0, "a": 1}}}}
    k1 = tt.text_style(spec1, preferred_name="MyStyle")
    k2 = tt.text_style(spec2, preferred_name="MyStyle")
    assert k1 == "MyStyle"
    assert k2 == "MyStyle_2"


def test_fill_dedup_by_fingerprint():
    """两个相同 fill 应该返回同一个 key。"""
    tt = T.TokenTable()
    c = {"value": {"r": 255, "g": 0, "b": 0, "a": 1}}
    assert tt.fill_solid(c) == tt.fill_solid(c) == "fill_000001"


def test_layout_basic():
    tt = T.TokenTable()
    k = tt.layout({"left": 10, "top": 20, "width": 100, "height": 50})
    assert k == "layout_000001"
    assert tt.styles[k] == {
        "mode": "none",
        "sizing": {"horizontal": "fixed", "vertical": "fixed"},
        "locationRelativeToParent": {"x": 10, "y": 20},
        "dimensions": {"width": 100, "height": 50},
    }
