#!/usr/bin/env python3
"""mockplus-context skill 主入口(v0.5.0)。
   子命令: data / download / all / tree / cookie
"""
import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mockplus",
        description="Mockplus 设计稿 → YAML/JSON + 切图(v0.5.0)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # data
    g = sub.add_parser("data", help="拉单页结构化 YAML/JSON")
    g.add_argument("url", help="完整 URL 或 <APP_ID>:<PAGE_ID>")
    g.add_argument("--out", default="-", help="输出路径(默认 stdout)")
    g.add_argument("--format", choices=["yaml", "json"], default="yaml")
    g.add_argument("--stats", action="store_true", help="额外打印统计到 stderr")
    g.add_argument("--refresh", action="store_true", help="跳过 cache 重拉")

    # download
    g = sub.add_parser("download", help="按 --nodes 下载切图")
    g.add_argument("url")
    g.add_argument("--nodes", default="all",
                   help="all 或 hash1,hash2(对应 YAML 里 imageRef)")
    g.add_argument("--out", help="输出目录(默认 ./mockplus-assets/<PAGE_ID>/)")
    g.add_argument("--include-design", action="store_true",
                   help="同时下整页截图 design.png")
    g.add_argument("--png-scale", type=int, default=2, choices=[1, 2],
                   help="(保留参数,目前固定 @2x)")

    # all
    g = sub.add_parser("all", help="一站式 = data + download(all + design)")
    g.add_argument("url")
    g.add_argument("out_dir", nargs="?", default=None,
                   help="输出目录(默认 ./mockplus-cache/<APP>/<PAGE>/)")

    # tree
    g = sub.add_parser("tree", help="树形打印项目结构(找 page id)")
    g.add_argument("app_id")
    g.add_argument("--format", choices=["text", "json"], default="text")
    g.add_argument("--refresh", action="store_true")

    # cookie
    g = sub.add_parser("cookie", help="Cookie 管理")
    csub = g.add_subparsers(dest="cookie_cmd", required=True)
    cset = csub.add_parser("set")
    cset.add_argument("--from-file", help="从文件读 cookie(默认 stdin)")
    ctest = csub.add_parser("test")
    ctest.add_argument("app_id")
    csub.add_parser("status")
    csub.add_parser("clear")
    csub.add_parser("path")

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # 延迟 import,避免没装 PyYAML 时也能跑 cookie/tree
    import cli

    if args.cmd == "cookie":
        return cli.action_cookie(args)
    if args.cmd == "tree":
        return cli.action_tree(args)
    if args.cmd == "data":
        return cli.action_data(args)
    if args.cmd == "download":
        return cli.action_download(args)
    if args.cmd == "all":
        return cli.action_all(args)

    print(f"未知子命令: {args.cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
