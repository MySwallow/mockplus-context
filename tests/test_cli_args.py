"""mockplus.py 参数面契约:--coords 回滚通道在 data 与 all 两个入口都可用。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "skills" / "mockplus-context" / "scripts"))
import mockplus


def test_data_coords_default_relative():
    ns = mockplus.build_parser().parse_args(["data", "a:b"])
    assert ns.coords == "relative"


def test_all_accepts_coords_absolute():
    ns = mockplus.build_parser().parse_args(
        ["all", "a:b", "--coords", "absolute"])
    assert ns.coords == "absolute"


def test_shot_and_tokens_argument_surface():
    p = mockplus.build_parser()
    ns = p.parse_args(["shot", "a:b", "--node", "X1", "--pad", "4"])
    assert (ns.node, ns.pad) == ("X1", 4)
    assert p.parse_args(["shot", "a:b"]).node is None
    assert p.parse_args(["tokens", "APP"]).format == "yaml"
    with pytest.raises(SystemExit):
        p.parse_args(["shot", "a:b", "--pad", "-2"])
