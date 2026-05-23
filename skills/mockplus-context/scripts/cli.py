"""cli.py - 各子命令的 action 实现。

调用约定:每个 action_<name>(args) 返回退出码 int。
- args 是 argparse.Namespace
- 标准输出走 stdout(用户/下游消费)
- 进度 / 错误走 stderr
"""
import argparse as _argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List

import client
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
            content = p.read_text()
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


def action_data(args) -> int:
    app_id, target_id = client.parse_url_or_short(args.url)
    kind = client.resolve_target_kind(app_id, target_id, refresh=args.refresh)
    if kind == "group":
        print(f"ERR: URL 指向 group,先用 `mockplus tree {app_id}` 浏览找到具体 page id",
              file=sys.stderr)
        return 22
    if kind != "page":
        print(f"ERR: TARGET_ID={target_id} 不是 page(kind={kind})", file=sys.stderr)
        return 22

    idx = client.fetch_index(app_id, refresh=args.refresh)
    pages, _ = client.flatten_pages(idx)
    page_meta = next(p for p in pages if p["id"] == target_id)

    data = client.get_page_data_cached(app_id, page_meta, refresh=args.refresh)
    result = _transform.transform(data, page_meta, app_id)

    # 校验:断言关键字段(替代砍掉的 _schema.py)
    try:
        assert "metadata" in result and result["metadata"].get("pageId"), "metadata.pageId 缺失"
        assert isinstance(result["nodes"], list), "nodes 不是 list"
        assert isinstance(result["globalVars"]["styles"], dict), "globalVars.styles 不是 dict"
    except AssertionError as e:
        print(f"ERR: transform 输出校验失败: {e}", file=sys.stderr)
        return 2

    # 输出
    out_text = _transform.serialize(result, fmt=args.format)
    if args.out and args.out != "-":
        Path(args.out).write_text(out_text)
        print(f"OK: 写入 {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(out_text)
        if not out_text.endswith("\n"):
            sys.stdout.write("\n")

    # --stats:额外输出统计到 stderr
    if args.stats:
        stats = _transform.compute_stats(result)
        print("---- stats ----", file=sys.stderr)
        print(json.dumps(stats, ensure_ascii=False, indent=2), file=sys.stderr)
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
                                       ensure_ascii=False, indent=2))
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
        format="yaml", stats=False, refresh=False,
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
