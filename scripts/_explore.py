#!/usr/bin/env python3
"""扫描若干 data.json,统计字段分布、enum 值集合、缺失模式。"""
import argparse, json, os, sys
from collections import Counter, defaultdict


def walk(node, path, field_count, enum_values, _samples):
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else k
            field_count[p] += 1
            if isinstance(v, (str, int, float, bool)) and not isinstance(v, bool):
                # 收集 string 类型字段的 enum 候选
                if isinstance(v, str) and len(v) < 64:
                    enum_values[p].add(v)
            walk(v, p, field_count, enum_values, _samples)
    elif isinstance(node, list):
        for item in node[:5]:  # 每个 list 只采样前 5 项,避免爆炸
            walk(item, f"{path}[]", field_count, enum_values, _samples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="包含 data.json 的目录(递归扫描)")
    ap.add_argument("--top", type=int, default=200, help="只打印出现频率 top N 字段")
    ap.add_argument("--enum-max", type=int, default=20, help="enum 取值超过这个数视为非枚举")
    args = ap.parse_args()

    field_count = Counter()
    enum_values = defaultdict(set)
    file_count = 0

    for root, _, files in os.walk(args.path):
        for f in files:
            if f == "data.json":
                fp = os.path.join(root, f)
                try:
                    data = json.load(open(fp))
                    walk(data, "", field_count, enum_values, None)
                    file_count += 1
                except Exception as e:
                    print(f"SKIP {fp}: {e}", file=sys.stderr)

    print(f"=== 扫描 {file_count} 份 data.json ===\n")
    print("## 字段出现频率(top {})".format(args.top))
    for path, cnt in field_count.most_common(args.top):
        line = f"  {cnt:6d}  {path}"
        # 附 enum 候选(取值数小于阈值)
        vals = enum_values.get(path, set())
        if 1 < len(vals) <= args.enum_max:
            line += f"  enum={sorted(vals)}"
        print(line)


if __name__ == "__main__":
    main()
