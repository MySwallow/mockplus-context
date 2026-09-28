#!/usr/bin/env python3
"""mockplus-context skill 主入口(v0.8.0)。
   子命令: data / outline / download / all / tree / cookie
"""
import argparse
import os
import sys


def _nonneg_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"需要非负整数,收到 {value!r}")
    if n < 0:
        raise argparse.ArgumentTypeError(f"需要非负整数,收到 {value!r}")
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mockplus",
        description="Mockplus 设计稿 → YAML/JSON + 切图(v0.8.0)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # data
    g = sub.add_parser("data", help="拉单页结构化 YAML/JSON")
    g.add_argument("url", help="完整 URL 或 <APP_ID>:<PAGE_ID>")
    g.add_argument("--out", default="-", help="输出路径(默认 stdout)")
    g.add_argument("--format", choices=["yaml", "json"], default="yaml")
    g.add_argument("--coords", choices=["relative", "absolute"], default="relative",
                   help="坐标语义:relative=包含树重建+相对父坐标(默认);"
                        "absolute=v0.5 画布绝对坐标(回滚通道)")
    g.add_argument("--raw", action="store_true",
                   help="输出未蒸馏原文(v0.6 形态;默认 YAML 经 distill 蒸馏 −~49%)")
    g.add_argument("--node", default=None, metavar="ID[,ID...]",
                   help="只输出指定节点子树(id 取自 outline 或蒸馏 YAML;≥8 位前缀即可)")
    g.add_argument("--stats", action="store_true", help="额外打印统计到 stderr")
    g.add_argument("--refresh", action="store_true", help="跳过 cache 重拉")

    # outline
    g = sub.add_parser("outline", help="整页区块大纲(大页先看它,再 data --node 下钻)")
    g.add_argument("url", help="完整 URL 或 <APP_ID>:<PAGE_ID>")
    g.add_argument("--depth", type=_nonneg_int, default=None,
                   help="只展开到第 N 层(0 = 仅顶层;默认全部容器)")
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
    g.add_argument("--coords", choices=["relative", "absolute"], default="relative",
                   help="透传给 data 步骤(语义见 data --coords)")

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


def _force_utf8_stdio() -> None:
    """stdin/stdout/stderr 固定 UTF-8。

    Windows 下重定向到文件/管道时 Python 默认按系统 locale(中文系统 = GBK)编码,
    中文会变乱码、emoji 直接 UnicodeEncodeError。用户显式设了 PYTHONIOENCODING 则尊重之。
    """
    if os.environ.get("PYTHONIOENCODING"):
        return
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass  # 流已关闭/已读过/不可重配:保持原样,不因此中断命令


def main(argv=None) -> int:
    _force_utf8_stdio()
    args = build_parser().parse_args(argv)
    # 延迟 import,避免没装 PyYAML 时也能跑 cookie/tree
    import cli

    if args.cmd == "cookie":
        return cli.action_cookie(args)
    if args.cmd == "tree":
        return cli.action_tree(args)
    if args.cmd == "data":
        return cli.action_data(args)
    if args.cmd == "outline":
        return cli.action_outline(args)
    if args.cmd == "download":
        return cli.action_download(args)
    if args.cmd == "all":
        return cli.action_all(args)

    print(f"未知子命令: {args.cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
