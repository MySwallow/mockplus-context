"""mockplus.py 参数面契约:--coords 回滚通道在 data 与 all 两个入口都可用。"""
import sys
from pathlib import Path

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
