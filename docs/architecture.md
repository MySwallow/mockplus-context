# Architecture (v0.5.0)

## 模块拆分

```
skills/mockplus-context/scripts/
├── mockplus.py      # 入口:argparse + 子命令 dispatch（~77 行）
├── cli.py           # 各 action 实现:data/download/all/tree/cookie（~280 行）
├── transform.py     # sketch JSON → 结构化 dict(YAML/JSON 可序列化)（~600 行）
└── client.py        # API 客户端 + cookie + CDN 下载 + cache 管理（~360 行）
```

**为什么 `client.py` 不叫 `io.py`**:Python 标准库已有 `io` 模块,子目录里 `from io import StringIO` 会被本地 `io.py` 遮蔽。

## 依赖关系

```
mockplus.py  →  cli.py  →  transform.py
                       \→  client.py
```

`cli.py` 是唯一引入命令行 IO 的层(stdout / stderr / exit code)。`transform.py` 与 `client.py` 是可被测试直接 import 的纯/显式 IO 模块。

## 数据流

```
URL → client.parse_url_or_short → client.fetch_index → client.flatten_pages
                                                                    ↓
                                                          client.get_page_data_cached
                                                                    ↓
                                                         transform.transform
                                                                    ↓
                                              transform.serialize(yaml|json)
                                                                    ↓
                                                            stdout / file
```

`download` 数据流:`URL → fetch_index → get_page_data_cached → client.extract_slices(wanted=...) → client.download_slices`。

## 关键设计:Token 表(`transform.TokenTable`)

- `globalVars.styles` 注册器,累积式
- fill/stroke/effect/layout 用 6 位序号 key(`fill_000001`),fingerprint 去重
- textStyle 优先用 `sharedStyle.name`(语义化);同名同 spec 复用,同名不同 spec 加 `_2`/`_3` 后缀;无 sharedStyle 退回序号 key
- 节点上只放引用,不内联 spec,YAML 体积大幅下降

## 关键设计:unhandledFields 探针

`transform.py` 维护 `LAYER_HANDLED` / `BASIC_HANDLED` 字段白名单。每次 transform 完一个节点,把没消费的字段路径塞进 `_meta.unhandledFields`(去重)。Mockplus 升级 sketch schema 时,新字段立刻出现在这个列表,提示需要更新 transform。

## 关键设计:容错降级

`extract_node` 递归 children 时单 child 抛异常会被捕获 → 占位节点 `{type: "_ERROR", _error: ...}` 替代 → 其他兄弟节点不受影响。`_meta.warnings` 记录降级事件。

## 路径约定

| 用途 | 默认 | 覆盖环境变量 |
|---|---|---|
| cookie 文件 | `~/.config/mockplus/cookie` | `MOCKPLUS_COOKIE_FILE` |
| API/cache 根 | `~/.cache/mockplus/<APP_ID>/` | `MOCKPLUS_CACHE_DIR` |
| 直接传 cookie | (无) | `MOCKPLUS_COOKIE` |
| `download` 输出 | `./mockplus-assets/<PAGE_ID>/` | `--out` |
| `all` 输出 | `./mockplus-cache/<APP_ID>/<PAGE_ID>/` | 第 2 个位置参数 |

## 退出码

```
0   成功
2   CLI 参数错 / transform 输出 assert 失败
10  cookie 未配置
11  --from-file 文件不存在
12  cookie 为空
14  HTTP 层失败
15  cookie test API 拒绝
21  index API code != 0
22  TARGET_ID 误判(group / notfound)
```

## 测试策略

- `tests/test_transform.py`:5 个 fixture 黄金对照(YAML expected),含 `unhandledFields == []` 断言
- `tests/test_assets.py`:本地 http.server 起 PNG 测 `client.download_slices` + `extract_slices`
- `tests/test_tree.py`:`cli.action_tree` text/json 输出
- `tests/test_token_naming.py`:TokenTable 命名策略(设计师命名优先、同名冲突后缀)
- 端到端(`all` 命令)依赖真 cookie + 真 CDN,作为手动 smoke,不入 CI
