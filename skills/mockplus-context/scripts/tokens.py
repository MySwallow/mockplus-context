"""tokens.py — 设计 token 汇总(v0.9):颜色 / 文字样式 / 圆角 / 阴影 / 渐变,按使用次数排序。

对标 Figma 官方 MCP 的 get_variable_defs:告诉 agent 这一页 / 一组 / 整个项目实际用了
哪些值、各用了多少次,用来映射到项目已有 token 或生成规则文件。Mockplus 没有变量系统,
只能从节点引用反推。输入是 transform 产出的 result dict(蒸馏前,引用都在 globalVars 里)。

文字样式按"字体规格 + 颜色"合并(忽略对齐:同一规格左对齐/居中不算两个 token),
设计师命名作为别名列出(68 页语料 82% 的文本节点用了设计师命名的样式)。
"""
import json
import re
from collections import Counter
from typing import Dict, List, Optional

TEXT_SPEC_KEYS = ("fontFamily", "fontSize", "fontWeight", "lineHeight",
                  "letterSpacing", "color", "decoration")
MAX_NAMES = 5
_SEQ_TEXT_KEY_RE = re.compile(r"^textStyle_\d+$")
_DUP_SUFFIX_RE = re.compile(r"^(.*)_(\d+)$")
_TRAILING_ZERO_RE = re.compile(r"(\d)\.0+(?=px)")


def _norm_radius(value: str) -> str:
    """'8.0px' → '8px'(transform 对浮点圆角输出不统一,汇总时归一,避免同值拆成两个 token)。"""
    return _TRAILING_ZERO_RE.sub(r"\1", value)


def _fp(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def _designer_name(key: str, styles: dict) -> Optional[str]:
    """textStyle 引用 key → 设计师命名;序号 key(textStyle_N)返回 None。
    TokenTable 对"同名不同规格"加 `_2`/`_3` 后缀,基名存在时还原为基名。

    已知局限:只看字符串形状,设计师自己把变体命名为 `Body` / `Body_2` 时,
    `Body_2` 也会被还原成 `Body`(规格仍按实际值分条,只是别名合并)。"""
    if _SEQ_TEXT_KEY_RE.match(key):
        return None
    m = _DUP_SUFFIX_RE.match(key)
    if m and m.group(1) in styles:
        return m.group(1)
    return key


class TokenStats:
    """跨页累加器(内部构建器;add_page 只读入参 result)。"""

    def __init__(self):
        self.colors: Dict[str, Counter] = {}
        self.typography: Dict[str, dict] = {}
        self.radii: Counter = Counter()
        self.shadows: Dict[str, dict] = {}
        self.gradients: Counter = Counter()
        self.pages = 0

    def _color(self, value, role: str):
        if isinstance(value, str) and value:
            self.colors.setdefault(value, Counter())[role] += 1

    def add_page(self, result: dict) -> None:
        styles = result["globalVars"]["styles"]
        self.pages += 1

        def walk(nodes):
            for n in nodes or []:
                for item in styles.get(n.get("fills")) or []:
                    if isinstance(item, str):
                        self._color(item, "fill")
                    elif isinstance(item, dict) and item.get("gradient"):
                        self.gradients[item["gradient"]] += 1
                stroke = styles.get(n.get("strokes"))
                if isinstance(stroke, dict):
                    self._color(stroke.get("color"), "stroke")
                shadow = styles.get(n.get("effects"))
                if isinstance(shadow, dict):
                    entry = self.shadows.setdefault(_fp(shadow), {"spec": shadow, "uses": 0})
                    entry["uses"] += 1
                if isinstance(n.get("borderRadius"), str):
                    self.radii[_norm_radius(n["borderRadius"])] += 1
                key = n.get("textStyle")
                spec = styles.get(key) if n.get("type") == "TEXT" else None
                if isinstance(spec, dict):
                    self._text(spec, _designer_name(key, styles))
                walk(n.get("children"))

        walk(result.get("nodes"))

    def _text(self, spec: dict, name: Optional[str]) -> None:
        typo = {k: spec[k] for k in TEXT_SPEC_KEYS
                if k in spec and not (k == "letterSpacing" and spec[k] == 0)}
        entry = self.typography.setdefault(_fp(typo), {"spec": typo, "uses": 0, "names": Counter()})
        entry["uses"] += 1
        if name:
            entry["names"][name] += 1
        self._color(spec.get("color"), "text")

    def to_dict(self, scope_info: dict, failed: List[dict]) -> dict:
        def by_uses(items):
            return sorted(items, key=lambda e: (-e["uses"], _fp(e.get("value", e))))

        colors = by_uses({"value": v, "uses": sum(c.values()),
                          "roles": dict(sorted(c.items(), key=lambda x: -x[1]))}
                         for v, c in self.colors.items())
        typography = []
        for e in self.typography.values():
            row = dict(e["spec"])
            row["uses"] = e["uses"]
            names = [n for n, _ in e["names"].most_common(MAX_NAMES)]
            if names:
                row["names"] = names
            typography.append(row)
        typography.sort(key=lambda r: (-r["uses"], -(r.get("fontSize") or 0), _fp(r)))
        shadows = []
        for e in self.shadows.values():
            row = dict(e["spec"])
            row["uses"] = e["uses"]
            shadows.append(row)
        shadows.sort(key=lambda r: (-r["uses"], _fp(r)))

        out = {
            "scope": dict(scope_info, pages=self.pages),
            "colors": colors,
            "typography": typography,
            "radii": by_uses({"value": v, "uses": c} for v, c in self.radii.items()),
            "shadows": shadows,
            "gradients": by_uses({"value": v, "uses": c} for v, c in self.gradients.items()),
            "_meta": {
                "note": ("uses = 节点引用次数;colors.roles = 作为 文本/填充/描边 色的次数;"
                         "typography 按字体规格+颜色合并(忽略对齐),names 为设计师命名别名"),
                "pagesFailed": failed,
            },
        }
        return {k: v for k, v in out.items() if v != [] or k == "colors"}
