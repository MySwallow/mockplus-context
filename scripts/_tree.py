"""树形打印项目结构。
   DFS 全树遍历,容忍混合树(group 同时含 page + 子 group)。
   孤儿 page(parentID 指向不存在 group)显式 stderr 警告。
"""
import json
import sys
from _api import fetch_index, flatten_pages


def _node_summary_json(node: dict) -> dict:
    """递归把 _index.json 节点转成精简 JSON(LLM 友好)。"""
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


def cmd_tree(args):
    idx = fetch_index(args.app_id, refresh=args.refresh)

    if args.format == "json":
        out = [_node_summary_json(root) for root in idx["payload"]["pages"]]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # text 格式(emoji + 缩进)
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

    # 检测孤儿 page(parentID 不为空 + 不在已知 group ids 集合里)
    pages, groups = flatten_pages(idx)
    group_ids = {g["id"] for g in groups}
    for p in pages:
        parent = p.get("parentID", "")
        if parent and parent not in group_ids:
            print(f"⚠️  孤儿 page {p['id']} (parentID={parent} 不在树里): {p['name']}",
                  file=sys.stderr)
    return 0
