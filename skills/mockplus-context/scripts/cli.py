"""cli.py - 各子命令的 action 实现。

调用约定:每个 action_<name>(args) 返回退出码 int。
- args 是 argparse.Namespace
- 标准输出走 stdout(用户/下游消费)
- 进度 / 错误走 stderr
"""
import argparse as _argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import List

import assets
import client
import scope
import tokens as _tokens
import transform as _transform


# ============================================================
# cookie
# ============================================================

def action_cookie(args) -> int:
    sub = args.cookie_cmd

    if sub == "set":
        if getattr(args, "from_file", None):
            p = Path(args.from_file)
            if not p.exists():
                print(f"ERR: 文件不存在: {p}", file=sys.stderr)
                return 11
            content = p.read_text(encoding="utf-8")
        elif sys.stdin.isatty():
            print("粘贴 cookie(单行),回车结束:", file=sys.stderr)
            content = sys.stdin.readline()
        else:
            content = sys.stdin.read()
        if not content.strip():
            print("ERR: cookie 为空", file=sys.stderr)
            return 12
        client.write_cookie(content)
        print(f"OK: cookie 已写入 {client.cookie_file_path()}", file=sys.stderr)
        return 0

    if sub == "test":
        return client.test_cookie_api(args.app_id)

    if sub == "status":
        s = client.cookie_status()
        if not s["exists"]:
            print(f"Status:  未配置(运行 `mockplus cookie set`)")
            print(f"Path:    {s['path']}")
            return 0
        print(f"Path:    {s['path']}")
        print(f"Mode:    {s['mode']}")
        if "set_at" in s:
            print(f"SetAt:   {time.ctime(s['set_at'])}")
        if "expires_at" in s:
            print(f"Expires: {time.ctime(s['expires_at'])} ({s['days_left']} 天后)")
        return 0

    if sub == "clear":
        fp = client.cookie_file_path()
        if fp.exists():
            fp.unlink()
            print(f"OK: 已删除 {fp}", file=sys.stderr)
        return 0

    if sub == "path":
        print(client.cookie_file_path())
        return 0

    return 2


# ============================================================
# tree
# ============================================================

def _node_summary_json(node: dict) -> dict:
    is_group = node.get("isGroup", False)
    out = {
        "id": node.get("_id"),
        "name": node.get("name", ""),
        "kind": "group" if is_group else "page",
    }
    if not is_group:
        size = node.get("size") or {}
        if size:
            out["size"] = {"width": size.get("width"), "height": size.get("height")}
        if node.get("device"):
            out["device"] = node["device"]
    children = node.get("children") or []
    if children:
        out["children"] = [_node_summary_json(c) for c in children]
    return out


def action_tree(args) -> int:
    idx = client.fetch_index(args.app_id, refresh=args.refresh)

    if args.format == "json":
        out = [_node_summary_json(root) for root in idx["payload"]["pages"]]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # text 格式
    def walk(node, depth):
        indent = "  " * depth
        if node.get("isGroup", False):
            print(f"{indent}📁 {node.get('name','?')}  [{node['_id']}]")
        else:
            size = node.get("size") or {}
            sz = f"({size.get('width','?')}x{size.get('height','?')})" if size else ""
            print(f"{indent}📄 {node.get('name','?')}  [{node['_id']}]  {sz}")
        for c in node.get("children", []):
            walk(c, depth + 1)

    for root in idx["payload"]["pages"]:
        walk(root, 0)

    # 孤儿 page 警告
    pages, groups = client.flatten_pages(idx)
    group_ids = {g["id"] for g in groups}
    for p in pages:
        parent = p.get("parentID", "")
        if parent and parent not in group_ids:
            print(f"⚠️  孤儿 page {p['id']} (parentID={parent} 不在树里): {p['name']}",
                  file=sys.stderr)
    return 0


# ============================================================
# data
# ============================================================


def _load_page(url: str, refresh: bool, coords: str):
    """URL → (rc, (app_id, target_id, page_meta, result))。rc != 0 时错误已打到 stderr。

    result 已做缺切图标记(v0.9,节点 missingSlice)。"""
    app_id, target_id = client.parse_url_or_short(url)
    kind = client.resolve_target_kind(app_id, target_id, refresh=refresh)
    if kind == "group":
        print(f"ERR: URL 指向 group,先用 `mockplus tree {app_id}` 浏览找到具体 page id",
              file=sys.stderr)
        return 22, None
    if kind != "page":
        print(f"ERR: TARGET_ID={target_id} 不是 page(kind={kind})", file=sys.stderr)
        return 22, None

    idx = client.fetch_index(app_id, refresh=refresh)
    pages, _ = client.flatten_pages(idx)
    page_meta = next(p for p in pages if p["id"] == target_id)

    data = client.get_page_data_cached(app_id, page_meta, refresh=refresh)
    result = _transform.transform(data, page_meta, app_id, coords=coords)
    return 0, (app_id, target_id, page_meta, assets.mark_missing_slices(result))


def _parse_node_arg(value) -> List[str]:
    return [x for x in (value or "").split(",") if x.strip()]


def action_data(args) -> int:
    rc, ctx = _load_page(args.url, args.refresh, getattr(args, "coords", "relative"))
    if rc != 0:
        return rc
    _app_id, _target_id, _page_meta, result = ctx

    # 校验:断言关键字段(替代砍掉的 _schema.py)
    try:
        assert "metadata" in result and result["metadata"].get("pageId"), "metadata.pageId 缺失"
        assert isinstance(result["nodes"], list), "nodes 不是 list"
        assert isinstance(result["globalVars"]["styles"], dict), "globalVars.styles 不是 dict"
    except AssertionError as e:
        print(f"ERR: transform 输出校验失败: {e}", file=sys.stderr)
        return 2

    # v0.8:--node 只输出指定子树(整页已在本地,纯本地裁剪)
    node_arg = getattr(args, "node", None)
    if node_arg is not None:
        try:
            result, notes = scope.select(result, _parse_node_arg(node_arg))
        except scope.ScopeError as e:
            print(f"ERR: {e}", file=sys.stderr)
            return 23
        for note in notes:
            print(f"NOTE: {note}", file=sys.stderr)

    # 输出(v0.7:YAML 默认经 distill 蒸馏;--raw 或蒸馏失败回退原文,绝不出半成品)
    out_text = _transform.serialize(result, fmt=args.format)
    if args.format == "yaml" and not getattr(args, "raw", False):
        try:
            import distill
            out_text, dstats = distill.apply_text(out_text)
            names = dstats["names_dropped"]
            print(f"OK: distilled -{dstats['saved_pct']}% "
                  f"(layouts {dstats['layouts_inlined']} inlined, uuid {dstats['uuids']}, "
                  f"fills {dstats['fills_inlined']} inlined, "
                  f"names -{names['auto'] + names['sameAsText']})",
                  file=sys.stderr)
            if dstats.get("legacy_coordinate_space"):
                print("WARN: 输入坐标空间非 parent-relative——pos 为原语义(勿当相对父坐标),"
                      "已写 _meta.distillWarnings", file=sys.stderr)
        except Exception as e:
            print(f"WARN: distill 失败,已回退未蒸馏原文: {e}", file=sys.stderr)
    if args.out and args.out != "-":
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"OK: 写入 {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(out_text)
        if not out_text.endswith("\n"):
            sys.stdout.write("\n")

    for hint in (assets.missing_slice_note(result),
                 scope.budget_hint(out_text, args.url, scoped=node_arg is not None)):
        if hint:
            print(hint, file=sys.stderr)

    # --stats:额外输出统计到 stderr
    if args.stats:
        stats = _transform.compute_stats(result)
        print("---- stats ----", file=sys.stderr)
        print(json.dumps(stats, ensure_ascii=False, indent=2), file=sys.stderr)
    return 0


# ============================================================
# outline
# ============================================================

def action_outline(args) -> int:
    rc, ctx = _load_page(args.url, args.refresh, "relative")
    if rc != 0:
        return rc
    app_id, target_id, _page_meta, result = ctx

    # 整页 token 粗估 + id 口径与 `data` 蒸馏产物一致(蒸馏失败则 data 输出全 UUID)
    import distill
    raw = _transform.serialize(result, fmt="yaml")
    try:
        distilled, _ = distill.apply_text(raw)
        id_map = distill.uuid_map(raw)
        tokens = scope.estimate_tokens(distilled)
    except distill.DistillError:
        id_map, tokens = {}, scope.estimate_tokens(raw)

    hint = f"mockplus data {app_id}:{target_id} --node <id>[,<id>...]"
    sys.stdout.write(scope.render_outline(result, id_map, args.depth, tokens, hint))
    return 0


def _short_id_map(result: dict) -> dict:
    """与蒸馏产物同口径的短 id 映射;蒸馏会放弃时返回空映射(用全 UUID)。"""
    import distill
    raw = _transform.serialize(result, fmt="yaml")
    try:
        distill.apply_text(raw)
        return distill.uuid_map(raw)
    except distill.DistillError:
        return {}


# ============================================================
# shot(v0.9:按区块裁剪整页截图)
# ============================================================

def _safe_filename(s: str) -> str:
    """外部 id 拼文件名前只留安全字符,杜绝 `../` 之类路径穿越。"""
    return re.sub(r"[^0-9A-Za-z_-]", "_", s) or "_"


def _ensure_design_png(app_id: str, page_meta: dict, refresh: bool) -> Path:
    """整页截图缓存到 cache/<APP>/<PAGE>/design.png;页面数据比截图新时重下。

    先下到临时文件,成功后原子替换;重下失败时沿用旧截图并告警(与页面数据的过期缓存兜底一致)。
    """
    design = client.cache_root() / app_id / page_meta["id"] / "design.png"
    data_fp = design.with_name("data.json")
    stale = design.exists() and (
        refresh or (data_fp.exists() and design.stat().st_mtime < data_fp.stat().st_mtime))
    if design.exists() and not stale:
        return design
    tmp = design.with_name("design.png.part")
    if tmp.exists():
        tmp.unlink()  # 上次中断的残留;不删会被下载器当成"已缓存"
    if client.download_page_image(page_meta, tmp):
        os.replace(tmp, design)
        return design
    if design.exists():
        print("WARN: 截图重下失败,沿用旧截图(可能不是最新设计)", file=sys.stderr)
        return design
    raise assets.CropError("design.png 下载失败(CDN 不通或链接过期,可加 --refresh 重试)")


def action_shot(args) -> int:
    rc, ctx = _load_page(args.url, args.refresh, "relative")
    if rc != 0:
        return rc
    app_id, target_id, page_meta, result = ctx
    if not page_meta.get("imageURL"):
        print("ERR: 该页没有整页截图(imageURL 为空)", file=sys.stderr)
        return 24
    canvas_w = (result["metadata"].get("size") or {}).get("width")
    if not canvas_w:
        print("ERR: 页面缺画布宽度,无法换算截图倍率", file=sys.stderr)
        return 24
    try:
        design = _ensure_design_png(app_id, page_meta, args.refresh)
        img_w, img_h = assets.png_size(design)
    except assets.CropError as e:
        print(f"ERR: {e}", file=sys.stderr)
        return 24
    scale = img_w / canvas_w
    out_dir = Path(args.out) if args.out else Path(f"./mockplus-shots/{_safe_filename(target_id)}")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.node is None:
        dest = out_dir / "design.png"
        shutil.copyfile(design, dest)
        print(f"{dest}  整页 {img_w}x{img_h}px @{scale:g}x")
        return 0

    try:
        located = scope.locate(result, _parse_node_arg(args.node))
    except scope.ScopeError as e:
        print(f"ERR: {e}", file=sys.stderr)
        return 23
    id_map = _short_id_map(result)
    written = 0
    for node, box in located:
        nid = id_map.get(node["id"], node["id"])
        pb = assets.px_box(box, scale, args.pad, img_w, img_h) if box else None
        if pb is None:
            print(f"WARN: #{nid} 无几何信息或完全在截图外,跳过", file=sys.stderr)
            continue
        dest = out_dir / f"{_safe_filename(nid)}.png"
        try:
            assets.crop_png(design, dest, pb)
        except assets.CropError as e:
            print(f"ERR: {e}(#{nid} 像素框 x={pb[0]} y={pb[1]} w={pb[2]} h={pb[3]})",
                  file=sys.stderr)
            return 24
        written += 1
        print(f"{dest}  #{nid} @{scope._num(box[0])},{scope._num(box[1])} "
              f"{scope._num(box[2])}x{scope._num(box[3])} → {pb[2]}x{pb[3]}px @{scale:g}x")
    return 0 if written else 24


# ============================================================
# tokens(v0.9:设计 token 汇总)
# ============================================================

def _pages_under(group_id: str, pages: list, groups: list) -> list:
    parent = {g["id"]: g.get("parentID") for g in groups}

    def under(pid) -> bool:
        seen = set()
        while pid and pid not in seen:
            if pid == group_id:
                return True
            seen.add(pid)
            pid = parent.get(pid)
        return False

    return [p for p in pages if under(p.get("parentID"))]


def action_tokens(args) -> int:
    try:
        app_id, target_id = client.parse_url_or_short(args.target)
    except ValueError as e:
        print(f"ERR: {e}", file=sys.stderr)
        return 2
    idx = client.fetch_index(app_id, refresh=args.refresh)
    pages, groups = client.flatten_pages(idx)
    page = next((p for p in pages if p["id"] == target_id), None)
    group = next((g for g in groups if g["id"] == target_id), None)
    if target_id is None:
        info, chosen = {"kind": "app", "id": app_id}, pages
    elif page:
        info, chosen = {"kind": "page", "id": page["id"], "name": page["name"]}, [page]
    elif group:
        info = {"kind": "group", "id": group["id"], "name": group["path"]}
        chosen = _pages_under(group["id"], pages, groups)
    else:
        print(f"ERR: {target_id} 在项目 {app_id} 里既不是页面也不是分组;"
              f"先 `mockplus tree {app_id}` 查 id", file=sys.stderr)
        return 22
    if not chosen:
        print("ERR: 该范围内没有页面", file=sys.stderr)
        return 22

    stats, failed = _tokens.TokenStats(), []
    for i, pm in enumerate(chosen, 1):
        if len(chosen) > 1:
            print(f"[{i}/{len(chosen)}] {pm['name']}", file=sys.stderr)
        try:
            data = client.get_page_data_cached(app_id, pm, refresh=args.refresh)
            stats.add_page(_transform.transform(data, pm, app_id, coords="absolute"))
        except Exception as e:  # 单页失败不拖垮整体汇总:告警 + 记入 _meta.pagesFailed
            # 带上异常类型,区分网络/数据问题(URLError…)与代码回归(KeyError…)
            err = f"{type(e).__name__}: {e}"
            failed.append({"id": pm["id"], "name": pm["name"], "error": err[:200]})
            print(f"WARN: 页面 {pm['id']} 跳过: {err}", file=sys.stderr)
    if stats.pages == 0:
        print("ERR: 所有页面都拉取/转换失败,见上方 WARN", file=sys.stderr)
        return 14

    out_text = _transform.serialize(stats.to_dict(info, failed), fmt=args.format)
    if args.out and args.out != "-":
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"OK: {stats.pages} 页 token 汇总写入 {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(out_text if out_text.endswith("\n") else out_text + "\n")
    est = scope.estimate_tokens(out_text)
    if est > scope.TOKEN_BUDGET:
        print(f"WARN: 汇总约 {est} token(>{scope.TOKEN_BUDGET}),单次读取可能被截断;"
              f"可缩小范围(分组 / 单页),或分段读取 --out 文件", file=sys.stderr)
    return 0


# ============================================================
# download
# ============================================================

def action_download(args) -> int:
    app_id, target_id = client.parse_url_or_short(args.url)
    kind = client.resolve_target_kind(app_id, target_id, refresh=False)
    if kind != "page":
        print(f"ERR: TARGET_ID={target_id} 不是 page(kind={kind})", file=sys.stderr)
        return 22

    idx = client.fetch_index(app_id, refresh=False)
    pages, _ = client.flatten_pages(idx)
    page_meta = next(p for p in pages if p["id"] == target_id)
    data = client.get_page_data_cached(app_id, page_meta, refresh=False)

    # 解析 --nodes
    wanted = None
    if args.nodes and args.nodes != "all":
        wanted = set(args.nodes.split(","))

    slices = client.extract_slices(data, wanted=wanted)
    out_dir = Path(args.out) if args.out else Path(f"./mockplus-assets/{target_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 写 manifest
    manifest_fp = out_dir / "assets-manifest.json"
    manifest_fp.write_text(json.dumps({"slices": slices},
                                       ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"目标切图: {len(slices)} 个 → {out_dir}", file=sys.stderr)

    stats = client.download_slices(slices, out_dir)
    print(f"OK: 下载 {stats['ok']} (cached={stats['cached']}, "
          f"fail={stats['fail']}, total_files={stats['total']})",
          file=sys.stderr)

    if args.include_design:
        design_fp = out_dir / "design.png"
        if client.download_page_image(page_meta, design_fp):
            print(f"OK: design.png → {design_fp}", file=sys.stderr)
        else:
            print(f"WARN: 无 page imageURL,跳过 design.png", file=sys.stderr)

    return 0


# ============================================================
# all
# ============================================================


def action_all(args) -> int:
    app_id, target_id = client.parse_url_or_short(args.url)
    out_root = Path(args.out_dir) if args.out_dir else \
        Path(f"./mockplus-cache/{app_id}/{target_id}")
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"[mockplus all] APP_ID={app_id}  PAGE_ID={target_id}  out={out_root}",
          file=sys.stderr)

    # 1) data → data.yaml
    data_ns = _argparse.Namespace(
        url=args.url, out=str(out_root / "data.yaml"),
        format="yaml", coords=getattr(args, "coords", "relative"),
        stats=False, refresh=False,
    )
    rc = action_data(data_ns)
    if rc != 0:
        return rc

    # 2) download → assets/ + design.png
    assets_dir = out_root / "assets"
    download_ns = _argparse.Namespace(
        url=args.url, out=str(assets_dir),
        nodes="all", include_design=False, png_scale=2,
    )
    rc = action_download(download_ns)
    if rc != 0:
        return rc

    # 3) design.png 单独放外层(spec §5.3)
    kind = client.resolve_target_kind(app_id, target_id, refresh=False)
    if kind == "page":
        idx = client.fetch_index(app_id, refresh=False)
        pages, _ = client.flatten_pages(idx)
        page_meta = next(p for p in pages if p["id"] == target_id)
        design_fp = out_root / "design.png"
        if client.download_page_image(page_meta, design_fp):
            print(f"OK: design.png → {design_fp}", file=sys.stderr)

    print(f"\n==== 完成 ====", file=sys.stderr)
    print(f"页目录:     {out_root}", file=sys.stderr)
    print(f"data.yaml:  {out_root}/data.yaml", file=sys.stderr)
    print(f"design.png: {out_root}/design.png", file=sys.stderr)
    print(f"assets:     {assets_dir}/  ({len(list(assets_dir.glob('*.png')) + list(assets_dir.glob('*.svg')))} 个文件)",
          file=sys.stderr)
    return 0
