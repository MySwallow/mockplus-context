"""assets.py — 视觉资产(v0.9):缺切图检测 + 按区块裁剪整页截图。

Mockplus 只导出设计师标注过的切图(Figma 能导出任意节点,Mockplus 不能)。68 页真实
语料:图标类节点 91% 没有切图、半数页面一张切图都没有。实现守则要求"切图原样原位用",
没切图的图标必须显式标出来,否则 agent 只能自绘或找图标库凑。

检测规则(68 页语料校准):小尺寸(8~48,宽高比 0.5~2)、子树无文本,且
- `icon`:图层名/组件名含 icon/图标/箭头/arrow —— 抽样全部是真图标
- `vector`:子树含非矩形/椭圆/背景的矢量路径,宽高比收紧到 0.6~1.67 并排除开关类控件
  —— 多数是图标,仍可能混入少量可 CSS 绘制的形状,需对照截图判断
只标最外层命中节点;状态栏 / Home Indicator / 键盘等系统 UI 整棵跳过。
"""
import math
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

import scope

ICON_NAME_RE = re.compile(r"icon|图标|箭头|arrow|(?:^|[/_\-\s])ic(?:[_\-]|$)", re.I)
SYSTEM_UI_RE = re.compile(r"状态栏|status ?bar|home ?indicator|键盘|keyboard", re.I)
PRIMITIVE_RE = re.compile(r"^(?:矩形|Rectangle|椭圆形|Oval|背景|Background|bg|蒙版|Mask)", re.I)
CONTROL_RE = re.compile(r"开关|switch|toggle", re.I)  # 控件组件,不是图标
ICON_MIN, ICON_MAX = 8, 48
ICON_ASPECT = (0.5, 2.0)      # 名称命中 icon 时
VECTOR_ASPECT = (0.6, 1 / 0.6)  # 仅凭矢量路径判断时收紧:排除柱状图柱子(20x40)等细长形状

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


class CropError(Exception):
    """截图裁剪失败。消息可直接展示给用户/LLM。"""


# ------------------------------------------------------------
# 缺切图检测
# ------------------------------------------------------------

def _image_fill_keys(styles: dict) -> set:
    return {k for k, v in styles.items()
            if isinstance(v, list) and v and isinstance(v[0], dict) and v[0].get("type") == "IMAGE"}


def _subtree(node: dict):
    yield node
    for c in node.get("children") or []:
        yield from _subtree(c)


def _icon_kind(node: dict, box, label: str) -> Optional[str]:
    """节点像图标则返回 'icon' / 'vector',否则 None(不看有没有切图)。"""
    if node.get("type") == "TEXT" or box is None:
        return None
    w, h = box[2], box[3]
    if min(w, h) < ICON_MIN or max(w, h) > ICON_MAX:
        return None
    aspect = w / h
    nodes = list(_subtree(node))
    if any(n.get("type") == "TEXT" for n in nodes):
        return None
    if ICON_NAME_RE.search(label):
        return "icon" if ICON_ASPECT[0] <= aspect <= ICON_ASPECT[1] else None
    if not VECTOR_ASPECT[0] <= aspect <= VECTOR_ASPECT[1] or CONTROL_RE.search(label):
        return None
    if any(n.get("type") == "VECTOR" and not PRIMITIVE_RE.match(n.get("name") or "")
           for n in nodes):
        return "vector"
    return None


def _insert_before_children(node: dict, key: str, value) -> dict:
    out = {k: v for k, v in node.items() if k != "children"}
    out[key] = value
    if "children" in node:
        out["children"] = node["children"]
    return out


def mark_missing_slices(result: dict) -> dict:
    """给"像图标但没有切图"的最外层节点加 `missingSlice: icon|vector`。
    返回新 result,不修改入参。计数不落 _meta(--node 裁剪后会失真),用 missing_counts 现数。"""
    img_keys = _image_fill_keys(result["globalVars"]["styles"])
    boxes = {id(n): b for n, _d, b, _a in scope._walk(result)}

    def rec(nodes, in_system: bool):
        out = []
        for n in nodes or []:
            label = f"{n.get('name') or ''} {n.get('componentId') or ''}"
            system = in_system or bool(SYSTEM_UI_RE.search(label))
            kind = None if system else _icon_kind(n, boxes.get(id(n)), label)
            if kind:
                has_slice = any(x.get("fills") in img_keys for x in _subtree(n))
                out.append(n if has_slice else _insert_before_children(n, "missingSlice", kind))
                continue
            kids = n.get("children")
            out.append({**n, "children": rec(kids, system)} if kids else n)
        return out

    new = dict(result)
    new["nodes"] = rec(result.get("nodes"), False)
    return new


def missing_counts(result: dict) -> dict:
    counts = {"icon": 0, "vector": 0}
    for root in result.get("nodes") or []:
        for n in _subtree(root):
            if n.get("missingSlice") in counts:
                counts[n["missingSlice"]] += 1
    return counts


def missing_slice_note(result: dict) -> Optional[str]:
    counts = missing_counts(result)
    total = counts["icon"] + counts["vector"]
    if not total:
        return None
    return (f"NOTE: {total} 个疑似图标没有切图"
            f"(icon {counts['icon']} / vector {counts['vector']},节点标 missingSlice)——"
            f"Mockplus 只导出设计师标注的切图;按 SKILL「实现守则」处理,不要自绘")


# ------------------------------------------------------------
# 截图裁剪
# ------------------------------------------------------------

def png_size(path: Path) -> Tuple[int, int]:
    """读 PNG IHDR 拿宽高(不依赖 Pillow)。非 PNG 抛 CropError。"""
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != _PNG_SIG or head[12:16] != b"IHDR":
        raise CropError(f"{path} 不是有效 PNG")
    return struct.unpack(">II", head[16:24])


def px_box(box, scale: float, pad: float, img_w: int, img_h: int):
    """设计坐标框(x, y, w, h)→ 像素裁剪框,外扩 pad(设计单位)并裁到图内;全在图外返回 None。"""
    x0 = max(0, math.floor((box[0] - pad) * scale))
    y0 = max(0, math.floor((box[1] - pad) * scale))
    x1 = min(img_w, math.ceil((box[0] + box[2] + pad) * scale))
    y1 = min(img_h, math.ceil((box[1] + box[3] + pad) * scale))
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def crop_png(src: Path, dest: Path, box) -> str:
    """按像素框裁剪 PNG。优先 Pillow,macOS 退到系统自带 sips。返回所用后端名。"""
    x, y, w, h = box
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image is not None:
        with Image.open(src) as im:
            im.crop((x, y, x + w, y + h)).save(dest)
        return "pillow"
    if sys.platform == "darwin" and shutil.which("sips"):
        r = subprocess.run(
            ["sips", "--cropToHeightWidth", str(h), str(w), "--cropOffset", str(y), str(x),
             str(src), "--out", str(dest)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or not dest.exists():
            raise CropError(f"sips 裁剪失败: {(r.stderr or r.stdout).strip()[:200]}")
        return "sips"
    raise CropError("没有可用的裁剪工具:`pip install Pillow`(macOS 自带 sips 也可)")
