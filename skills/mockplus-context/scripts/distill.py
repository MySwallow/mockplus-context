#!/usr/bin/env python3
"""distill.py — YAML 机械蒸馏(LLM 消费省 token;v0.7 起默认开启,v0.8 加去噪)。

变换(v0.7 两项实测 8 页 −49%;v0.8 三项在 68 页真实语料上再 −10.5%):
1. `globalVars.styles` 里的 `layout_*` 查找表(每项 ~13 行,信息只有 x/y/w/h)
   内联为节点行内一行 `pos: {x: …, y: …, w: …, h: …}`;非默认 mode/sizing 以
   `mode:`/`hsz:`/`vsz:` 键保留。含未识别字段的 layout **放弃内联**(fail-safe,
   引用与定义原样保留)。
2. UUID(8-4-4-4-12)→ 前 8 位确定性截断(跨拉取稳定,判子 id 锚点不受影响;
   短 id 碰撞时整体放弃蒸馏)。imageRef 等 40 位资产哈希不动(download 要用)。
   前 8 位若会被 YAML 读成数字则该 id 保留全 UUID——文本级替换无法安全加
   引号,截断反而引入类型歧义(fc 实测 2600 节点命中 2 个,≈0.4%/id 概率)。
   歧义口径取 1.1/1.2 并集:PyYAML safe_load 非 str(八进制形 `03450216`),
   或 1.2 core schema 数字形(纯数字 `12345678`、浮点形 `1234E567`)。
3. (v0.8)容器节点 `absolutePosition` 三行块 → 行内 `abs: {x: …, y: …}`。
4. (v0.8)单一纯色 fill(`['#RRGGBB']` / `['rgba(…)']`)直写到节点 `fills: '#RRGGBB'`,
   删掉不再被引用的 `fill_*` 定义;渐变/切图 fill 仍是 `fill_*` 引用(imageRef 不动)。
5. (v0.8)图层名去噪:删 Sketch 自动命名(`编组 2`/`矩形备份 3`/`Rectangle Copy` 等)
   与 TEXT 节点里和文本内容完全相同的图层名。

文本级变换 + 出口自检:计数不变量 + 解析后逐节点语义比对(期望 = 按上述规则
从输入推导);任何一条不满足即抛 DistillError——调用方(cli.action_data)回退
输出未蒸馏原文,绝不输出半蒸馏产物。

独立 CLI(离线蒸馏既有文件):
  python3 distill.py <in.yaml> [<out.yaml>] [--check-only]
"""
import re
import sys

DISTILL_VERSION = 2

LAYOUT_BLOCK_RE = re.compile(r"^    (layout_\d+):\n((?:      .*\n)+)", re.M)
LAYOUT_KNOWN_KEYS = {"mode", "sizing", "horizontal", "vertical",
                     "locationRelativeToParent", "x", "y", "dimensions", "width", "height"}
UUID_RE = re.compile(
    r"\b([0-9A-Fa-f]{8})-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b")
ABS_BLOCK_RE = re.compile(
    r"^( +)absolutePosition:\n\1  x: (-?[\d.]+)\n\1  y: (-?[\d.]+)\n", re.M)
# 单一纯色 fill 定义:列表恰一项且为颜色字面量(下一行不能再是列表项)
SOLID_FILL_DEF_RE = re.compile(
    r"^    (fill_\d+):\n    - ('#[0-9A-Fa-f]{6}'|rgba\(\d+, \d+, \d+, [\d.]+\))\n(?!    - )",
    re.M)
SOLID_COLOR_RE = re.compile(r"^(#[0-9A-Fa-f]{6}|rgba\(\d+, \d+, \d+, [\d.]+\))$")
# Sketch/Mockplus 自动生成的图层名(68 页真实语料命中 5731 个,零语义)
_AUTO_NAME_BASES = ("编组|矩形|路径|形状结合|椭圆形|形状|线条|直线|蒙版|多边形|三角形|星形|位图|图层|"
                    "Rectangle|Oval|Group|Path|Combined Shape|Mask|Line|Shape|Polygon|"
                    "Triangle|Star|Bitmap|Layer")
AUTO_NAME_RE = re.compile(
    rf"^(?:{_AUTO_NAME_BASES})(?: ?\d+)?(?:(?: ?[Cc]opy| ?拷贝| ?副本|备份)(?: ?\d+)?)*$")


class DistillError(Exception):
    pass


def _grab(block, key):
    m = re.search(rf"{key}:\s*(-?[\d.]+)\s*$", block, re.M)
    return m.group(1) if m else None


def _parse_layouts(src):
    """返回 (可内联 {name: 一行 pos 串}, 跳过名单)。未识别字段 → 跳过(保真)。"""
    inline, skipped = {}, []
    for m in LAYOUT_BLOCK_RE.finditer(src):
        name, block = m.group(1), m.group(2)
        keys = set(re.findall(r"^\s+(\w+):", block, re.M))
        x, y = _grab(block, "x"), _grab(block, "y")
        w, h = _grab(block, "width"), _grab(block, "height")
        if not keys.issubset(LAYOUT_KNOWN_KEYS) or None in (x, y, w, h):
            skipped.append(name)
            continue
        extra = ""
        mode = re.search(r"mode:\s*(\S+)", block)
        hs = re.search(r"horizontal:\s*(\S+)", block)
        vs = re.search(r"vertical:\s*(\S+)", block)
        if mode and mode.group(1) != "none":
            extra += f", mode: {mode.group(1)}"
        if hs and hs.group(1) != "fixed":
            extra += f", hsz: {hs.group(1)}"
        if vs and vs.group(1) != "fixed":
            extra += f", vsz: {vs.group(1)}"
        inline[name] = f"{{x: {x}, y: {y}, w: {w}, h: {h}{extra}}}"
    return inline, skipped


def _count(pattern, text):
    return len(re.findall(pattern, text, re.M))


def _yaml_mod():
    import yaml
    return yaml


def _load(text):
    """解析 YAML(有 libyaml 用 C 版,最大页 0.07s vs 纯 Python 0.67s)。"""
    yaml = _yaml_mod()
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    return yaml.load(text, Loader=loader)


def _scalar(raw):
    """单行 YAML 标量原文 → 值;解析失败返回 None(调用方据此放弃该处变换)。"""
    try:
        return _yaml_mod().safe_load(raw)
    except Exception:
        return None


def _ambiguous(s):
    """8 位截断 id 是否会被 YAML 读成非字符串。"""
    # PyYAML(1.1)口径:safe_load 读出非字符串(如八进制形 03450216)
    try:
        if not isinstance(_yaml_mod().safe_load(s), str):
            return True
    except Exception:
        return True
    # YAML 1.2 core schema 口径(js-yaml/yq 等):纯数字=int、数字E数字=float
    return bool(re.fullmatch(r"\d+", s) or re.fullmatch(r"\d+[eE]\d+", s))


def uuid_map(text: str) -> dict:
    """全 UUID → 蒸馏后 id 的映射(与 apply_text 同一口径;outline/--node 复用)。

    前 8 位与 YAML 数字形歧义的 UUID 不在映射里(保留全 UUID);
    截断碰撞抛 DistillError(apply_text 据此整体放弃蒸馏)。
    """
    fulls = {m.group(0) for m in UUID_RE.finditer(text)}
    shortable = {f for f in fulls if not _ambiguous(f[:8])}
    if len({f[:8] for f in shortable}) != len(shortable):
        raise DistillError("UUID 前 8 位截断出现碰撞,放弃蒸馏")
    return {f: f[:8] for f in shortable}


def is_auto_name(name) -> bool:
    return isinstance(name, str) and bool(AUTO_NAME_RE.match(name))


def _name_droppable(node: dict) -> bool:
    name = node.get("name")
    return is_auto_name(name) or (node.get("type") == "TEXT" and name == node.get("text"))


def _drop_names(text: str) -> tuple:
    """删自动命名 + TEXT 里与文本相同的图层名。返回 (新文本, 自动命名数, 同文本数)。

    节点头固定为 `- id` / `name` / `type` 三行(transform 键序);name 或 text
    跨行(长串折行)时不动该节点——保守跳过,由出口语义比对兜底。
    隐含前提(transform.extract_node 键序):TEXT 节点的 `text` 排在任何列表值自有键之前;
    扫描遇到同缩进列表项即停,违反前提时只会少删、不会误删(出口比对防误删)。
    """
    lines = text.split("\n")
    drop, n_auto, n_text = set(), 0, 0
    for i in range(len(lines) - 2):
        m = re.match(r"^( *)- id: ", lines[i])
        if not m:
            continue
        key = m.group(1) + "  "
        nm = re.match(rf"^{key}name: (.+)$", lines[i + 1])
        ty = re.match(rf"^{key}type: (\S+)$", lines[i + 2])
        if not (nm and ty):
            continue
        name = _scalar(nm.group(1))
        if is_auto_name(name):
            drop.add(i + 1)
            n_auto += 1
            continue
        if ty.group(1) != "TEXT" or not isinstance(name, str):
            continue
        # 在本节点自有键里找 text(自有键 = 恰好 key 缩进、非列表项;遇 children 停)
        for j in range(i + 3, len(lines)):
            ln = lines[j]
            if not ln.startswith(key) or ln[len(key):len(key) + 1] in (" ", "-"):
                if ln.startswith(key + " "):
                    continue  # 上一个键的折行续行
                break
            if ln.startswith(key + "children:"):
                break
            if ln.startswith(key + "text: "):
                nxt = lines[j + 1] if j + 1 < len(lines) else ""
                single = not nxt.startswith(key + " ")
                if single and _scalar(ln[len(key) + 6:]) == name:
                    drop.add(i + 1)
                    n_text += 1
                break
    if not drop:
        return text, 0, 0
    return "\n".join(ln for k, ln in enumerate(lines) if k not in drop), n_auto, n_text


def _pos_of(spec: dict) -> dict:
    """layout 定义 → 期望的行内 pos(与 _parse_layouts 同口径,供语义比对)。"""
    loc = spec.get("locationRelativeToParent") or {}
    dim = spec.get("dimensions") or {}
    pos = {"x": loc.get("x", spec.get("x")), "y": loc.get("y", spec.get("y")),
           "w": dim.get("width", spec.get("width")), "h": dim.get("height", spec.get("height"))}
    sizing = spec.get("sizing") or {}
    if spec.get("mode", "none") != "none":
        pos["mode"] = spec["mode"]
    if sizing.get("horizontal", "fixed") != "fixed":
        pos["hsz"] = sizing["horizontal"]
    if sizing.get("vertical", "fixed") != "fixed":
        pos["vsz"] = sizing["vertical"]
    return pos


def _map_exact(obj, id_map):
    """把"整值等于全 UUID"的字符串换成短 id(文本里夹带的 UUID 子串不算)。"""
    if isinstance(obj, dict):
        return {k: _map_exact(v, id_map) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_map_exact(v, id_map) for v in obj]
    return id_map.get(obj, obj) if isinstance(obj, str) else obj


def _verify(src_doc, out_doc, id_map, inlined_layouts, inlined_fills):
    """出口语义比对:输出必须恰好等于"按蒸馏规则从输入推导出的期望"。"""
    s_styles = (src_doc.get("globalVars") or {}).get("styles") or {}
    o_styles = (out_doc.get("globalVars") or {}).get("styles") or {}

    def check(sn, on, path):
        if len(sn or []) != len(on or []):
            raise DistillError(f"语义比对:{path} 子节点数 {len(sn or [])}→{len(on or [])}")
        for a, b in zip(sn or [], on or []):
            exp = {}
            for k, v in a.items():
                if k == "children":
                    continue
                if k == "id":
                    exp["id"] = id_map.get(v, v)
                elif k == "layout" and v in inlined_layouts:
                    exp["pos"] = _pos_of(s_styles.get(v) or {})
                elif k == "absolutePosition" and "abs" in b:
                    exp["abs"] = v
                elif k == "fills" and v in inlined_fills:
                    exp["fills"] = inlined_fills[v]
                else:
                    exp[k] = v
            if "name" in exp and "name" not in b:
                if not _name_droppable(a):
                    raise DistillError(f"语义比对:节点 {a.get('id')} 的图层名被误删")
                exp.pop("name")
            got = {k: v for k, v in b.items() if k != "children"}
            if got != exp:
                diff = sorted(k for k in set(got) | set(exp) if got.get(k) != exp.get(k))
                raise DistillError(f"语义比对:节点 {a.get('id')} 字段不一致 {diff}")
            if "layout" in b and b["layout"] not in o_styles:
                raise DistillError(f"语义比对:残留引用 {b['layout']} 无定义")
            check(a.get("children"), b.get("children"), f"{path}/{a.get('id')}")

    check(src_doc.get("nodes"), out_doc.get("nodes"), "nodes")
    exp_styles = {k: v for k, v in s_styles.items()
                  if k not in inlined_layouts and k not in inlined_fills}
    if o_styles != exp_styles:
        raise DistillError("语义比对:globalVars.styles 与期望不一致")
    if _map_exact(src_doc.get("metadata"), id_map) != out_doc.get("metadata"):
        raise DistillError("语义比对:metadata 与期望不一致")


def apply_text(src: str) -> tuple:
    """蒸馏 YAML 文本。返回 (蒸馏文本, stats)。失败抛 DistillError。"""
    if "\ndistilled: true" in src or "\n  distilled: true" in src:
        raise DistillError("输入已是蒸馏产物,拒绝二次蒸馏")

    inline, skipped = _parse_layouts(src)
    if not inline:
        raise DistillError("未找到可内联的 layout 表(格式不符或已蒸馏)")

    # 1) 删已内联的 layout 定义
    def rm_def(m):
        return "" if m.group(1) in inline else m.group(0)
    out = LAYOUT_BLOCK_RE.sub(rm_def, src)

    # 2) 引用替换 layout: layout_N → pos: {…}(跳过名单保留原引用)
    def sub_ref(m):
        name = m.group(1)
        return "pos: " + inline[name] if name in inline else m.group(0)
    out = re.sub(r"layout: (layout_\d+)", sub_ref, out)

    # 3) 容器 absolutePosition 三行块 → 行内 abs
    out, abs_n = ABS_BLOCK_RE.subn(r"\1abs: {x: \2, y: \3}\n", out)

    # 4) 单一纯色 fill 直写到节点,删定义
    solid = {m.group(1): m.group(2) for m in SOLID_FILL_DEF_RE.finditer(out)}
    out = SOLID_FILL_DEF_RE.sub("", out)
    out, fills_n = re.subn(r"^( +)fills: (fill_\d+)$",
                           lambda m: (m.group(1) + "fills: " + solid[m.group(2)]
                                      if m.group(2) in solid else m.group(0)),
                           out, flags=re.M)
    fills_n -= _count(r"^ +fills: fill_\d+$", out)  # subn 连未命中的也计数,扣回

    # 5) 图层名去噪
    out, names_auto, names_text = _drop_names(out)

    # 6) UUID → 前 8 位(碰撞则放弃;前 8 位与 YAML 数字形歧义的 id 保留全 UUID)
    fulls_n = len({m.group(0) for m in UUID_RE.finditer(out)})
    id_map = uuid_map(out)
    out = UUID_RE.sub(lambda m: id_map.get(m.group(0), m.group(0)), out)

    # 7) _meta 打标(+legacy 坐标空间警示:v0.5 历史文件 locationRelativeToParent 名不副实
    #    存画布绝对坐标——蒸馏只搬值,消费方把这种 pos 当相对父坐标会全盘算错)
    legacy_space = "coordinateSpace: parent-relative" not in src
    stamp = f"_meta:\n  distilled: true\n  distillVersion: {DISTILL_VERSION}\n"
    if legacy_space:
        stamp += ("  distillWarnings:\n"
                  "  - '输入无 coordinateSpace: parent-relative 标记——pos 为输入原语义"
                  "(重建回退 / --coords absolute / 旧版产物是画布绝对坐标),勿当相对父坐标消费'\n")
    out, n = re.subn(r"^_meta:\n", stamp, out, count=1, flags=re.M)
    if n != 1:
        raise DistillError("_meta 块缺失,无法打蒸馏标")

    # ---- 出口不变量(任何一条不满足 = 整体放弃) ----
    if _count(r"^\s*- id: ", src) != _count(r"^\s*- id: ", out):
        raise DistillError("不变量破坏:节点行数变化")
    for pat, label in ((r"^\s*text: ", "text"), (r"^\s*textStyle: ", "textStyle"),
                       (r"^\s*fills: ", "fills"), (r"imageRef", "imageRef")):
        if _count(pat, src) != _count(pat, out):
            raise DistillError(f"不变量破坏:{label} 计数变化")
    for m in re.finditer(r"layout: (layout_\d+)", out):
        if not re.search(rf"^    {m.group(1)}:\n", out, re.M):
            raise DistillError(f"不变量破坏:残留引用 {m.group(1)} 无定义")
    try:
        d = _load(out)
        for k in ("metadata", "nodes", "globalVars", "_meta"):
            if k not in d:
                raise DistillError(f"不变量破坏:蒸馏后缺顶层键 {k}")
        if not d["_meta"].get("distilled"):
            raise DistillError("不变量破坏:distilled 标未生效")
        _verify(_load(src), d, id_map, set(inline),
                {k: _scalar(v) for k, v in solid.items()})
    except DistillError:
        raise
    except Exception as e:
        raise DistillError(f"蒸馏后 YAML 解析/比对失败: {e}")

    stats = {
        "bytes_before": len(src.encode("utf-8")),
        "bytes_after": len(out.encode("utf-8")),
        "saved_pct": 100 - len(out.encode("utf-8")) * 100 // max(1, len(src.encode("utf-8"))),
        "layouts_inlined": len(inline),
        "layouts_skipped": skipped,
        "abs_inlined": abs_n,
        "fills_inlined": fills_n,
        "names_dropped": {"auto": names_auto, "sameAsText": names_text},
        "uuids": len(id_map),
        "uuids_kept_full": fulls_n - len(id_map),
        "legacy_coordinate_space": legacy_space,
    }
    return out, stats


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    check_only = "--check-only" in args
    args = [a for a in args if a != "--check-only"]
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    src_path = args[0]
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    try:
        out, stats = apply_text(src)
    except DistillError as e:
        print(f"DISTILL-FAIL {src_path}: {e}", file=sys.stderr)
        return 1
    print(f"OK {src_path}: {stats['bytes_before']} -> {stats['bytes_after']} bytes "
          f"(-{stats['saved_pct']}%), layouts {stats['layouts_inlined']} inlined"
          f"{' skipped=' + ','.join(stats['layouts_skipped']) if stats['layouts_skipped'] else ''}, "
          f"uuid {stats['uuids']}", file=sys.stderr)
    if stats["legacy_coordinate_space"]:
        print(f"WARN {src_path}: 输入坐标空间非 parent-relative(画布绝对坐标?)——"
              f"pos 为原语义,已写 _meta.distillWarnings", file=sys.stderr)
    if check_only:
        return 0
    dst = args[1] if len(args) > 1 else src_path
    with open(dst, "w", encoding="utf-8") as f:
        f.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
