#!/usr/bin/env python3
"""distill.py — YAML 机械蒸馏(v0.7,无损语义变换,LLM 消费省 token)。

两个变换(实测 8 页 −49%):
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

文本级变换 + 出口不变量自检;任何不变量不满足即抛 DistillError——调用方
(cli.action_data)回退输出未蒸馏原文,绝不输出半蒸馏产物。

独立 CLI(离线蒸馏既有文件):
  python3 distill.py <in.yaml> [<out.yaml>] [--check-only]
"""
import re
import sys

DISTILL_VERSION = 1

LAYOUT_BLOCK_RE = re.compile(r"^    (layout_\d+):\n((?:      .*\n)+)", re.M)
LAYOUT_KNOWN_KEYS = {"mode", "sizing", "horizontal", "vertical",
                     "locationRelativeToParent", "x", "y", "dimensions", "width", "height"}
UUID_RE = re.compile(
    r"\b([0-9A-Fa-f]{8})-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b")


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

    # 3) UUID → 前 8 位(碰撞则放弃;前 8 位与 YAML 数字形歧义的 id 保留全 UUID)
    import yaml as _yaml

    def _ambiguous(s):
        # PyYAML(1.1)口径:safe_load 读出非字符串(如八进制形 03450216)
        try:
            if not isinstance(_yaml.safe_load(s), str):
                return True
        except Exception:
            return True
        # YAML 1.2 core schema 口径(js-yaml/yq 等):纯数字=int、数字E数字=float
        return bool(re.fullmatch(r"\d+", s) or re.fullmatch(r"\d+[eE]\d+", s))

    fulls = {m.group(0) for m in UUID_RE.finditer(out)}
    shortable = {f for f in fulls if not _ambiguous(f[:8])}
    shorts = {f[:8] for f in shortable}
    if len(shorts) != len(shortable):
        raise DistillError("UUID 前 8 位截断出现碰撞,放弃蒸馏")
    uuids_n = len(shortable)
    kept_full = len(fulls) - uuids_n
    out = UUID_RE.sub(lambda m: m.group(1) if m.group(0) in shortable else m.group(0), out)

    # 4) _meta 打标(+legacy 坐标空间警示:v0.5 历史文件 locationRelativeToParent 名不副实
    #    存画布绝对坐标——蒸馏只搬值,消费方把这种 pos 当相对父坐标会全盘算错)
    legacy_space = "coordinateSpace: parent-relative" not in src
    stamp = f"_meta:\n  distilled: true\n  distillVersion: {DISTILL_VERSION}\n"
    if legacy_space:
        stamp += ("  distillWarnings:\n"
                  "  - '输入无 coordinateSpace: parent-relative 标记——pos 为输入原语义"
                  "(v0.5 历史文件是画布绝对坐标),勿当相对父坐标消费'\n")
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
        import yaml
        d = yaml.safe_load(out)
        for k in ("metadata", "nodes", "globalVars", "_meta"):
            if k not in d:
                raise DistillError(f"不变量破坏:蒸馏后缺顶层键 {k}")
        if not d["_meta"].get("distilled"):
            raise DistillError("不变量破坏:distilled 标未生效")
    except DistillError:
        raise
    except Exception as e:
        raise DistillError(f"蒸馏后 YAML 解析失败: {e}")

    stats = {
        "bytes_before": len(src.encode("utf-8")),
        "bytes_after": len(out.encode("utf-8")),
        "saved_pct": 100 - len(out.encode("utf-8")) * 100 // max(1, len(src.encode("utf-8"))),
        "layouts_inlined": len(inline),
        "layouts_skipped": skipped,
        "uuids": uuids_n,
        "uuids_kept_full": kept_full,
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
        print(f"WARN {src_path}: 输入坐标空间非 parent-relative(v0.5 历史文件?)——"
              f"pos 为原语义,已写 _meta.distillWarnings", file=sys.stderr)
    if check_only:
        return 0
    dst = args[1] if len(args) > 1 else src_path
    with open(dst, "w", encoding="utf-8") as f:
        f.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
