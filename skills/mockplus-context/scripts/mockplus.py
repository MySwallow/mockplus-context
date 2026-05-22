#!/usr/bin/env python3
"""mockplus-context skill 主入口。
   子命令: get-data / tree / download-assets / cookie / inspect
"""
import argparse
import sys


def build_parser():
    p = argparse.ArgumentParser(prog="mockplus", description="Mockplus 设计稿抓取 skill")
    sub = p.add_subparsers(dest="cmd", required=True)

    # get-data
    g = sub.add_parser("get-data", help="拉单页结构化 JSON")
    g.add_argument("url", help="完整 URL 或 <APP_ID>:<PAGE_ID>")
    g.add_argument("--refresh", action="store_true")

    # tree
    g = sub.add_parser("tree", help="树形打印项目结构")
    g.add_argument("app_id")
    g.add_argument("--format", choices=["text", "json"], default="text")
    g.add_argument("--refresh", action="store_true")

    # download-assets
    g = sub.add_parser("download-assets", help="并发下载 CDN 图片")
    g.add_argument("--downloads", required=True,
                   help='JSON 数组,每项 {url, fileName}')
    g.add_argument("--local-path", required=True)

    # inspect
    g = sub.add_parser("inspect", help="拉单页并打印统计(回归检测)")
    g.add_argument("url")
    g.add_argument("--refresh", action="store_true")

    # cookie
    g = sub.add_parser("cookie", help="Cookie 管理")
    csub = g.add_subparsers(dest="cookie_cmd", required=True)
    cset = csub.add_parser("set")
    cset.add_argument("--from-file")
    ctest = csub.add_parser("test")
    ctest.add_argument("app_id")
    csub.add_parser("status")
    csub.add_parser("clear")
    csub.add_parser("path")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.cmd == "cookie":
        from _cookie import cmd_cookie
        return cmd_cookie(args)
    if args.cmd == "get-data":
        from _api import cmd_get_data
        return cmd_get_data(args)
    if args.cmd == "tree":
        from _tree import cmd_tree
        return cmd_tree(args)
    if args.cmd == "download-assets":
        from _assets import cmd_download_assets
        return cmd_download_assets(args)
    if args.cmd == "inspect":
        from _api import cmd_inspect
        return cmd_inspect(args)

    print(f"未知子命令: {args.cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
