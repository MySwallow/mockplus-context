# Architecture

## 包结构

```
skills/mockplus-context/scripts/
├── __init__.py       # 空,package 标识
├── mockplus.py       # argparse 主入口,根据 cmd 分派到 _xxx 模块
├── _api.py           # Mockplus 私有 API 客户端 + URL 解析 + cache 层
├── _transform.py     # sketch JSON → 结构化 JSON(字段契约见 SKILL.md "## 输出 JSON 速览")
├── _assets.py        # 纯 CDN 下载(无 cookie 依赖)
├── _cookie.py        # cookie 加载 + 5 个子命令
├── _tree.py          # 树形打印(含 group 与 page 嵌套 + 孤儿检测)
├── _schema.py        # 输出 JSON 校验(validate_lite + validate_full)
└── _explore.py       # 字段侦察辅助(开发用)
```

每个 `_xxx.py` 暴露一个 `cmd_<name>(args)` 函数给 `mockplus.py` 调用。

## 数据流

```
URL → _api.parse_url_or_short() → (app_id, target_id)
              ↓
_api.fetch_index() → _api.resolve_target_kind()
              ↓
   page:  _api.cmd_get_data → _api.fetch_page_data → _transform.transform → _schema.validate_lite → stdout
   group: 报错 22,提示用 tree
   app:   _tree.cmd_tree → 递归打印
              ↓
download-assets(独立流): _assets.cmd_download_assets → 并发 GET CDN → stdout
```

## 关键决策

- **Python 标准库 only**: `urllib.request` / `concurrent.futures` / `argparse`,运行时零 pip 依赖
- **schema 校验双层**: `validate_lite`(标准库)兜底,`validate_full`(jsonschema 可选)装了启用
- **API cache 24h**: `~/.cache/mockplus-context/<APP_ID>/{_index.json, <PAGE_ID>/data.json}`,`--refresh` 跳过
- **切图 cache 由用户管**: `download-assets --local-path` 决定保存位置,文件存在则 skip
- **globalVars 抽取**: 同样的 fill/text/shadow/stroke 用指纹去重,nodes 引用 ref 而非 inline,LLM token 占用大幅下降
- **bounds 字段沿用 Sketch 原生**: `{top, left, width, height}` — transform 少一层翻译,LLM 写 CSS 直觉一致
- **type / realType 双轨**: `basic.type`(粗类 group/text/rect 等,LLM 写 CSS)+ `basic.realType`(细类 Artboard/SymbolInstance 等,LLM debug)同时输出
- **sharedStyle 一对多**: 同一 sharedStyle.id 下不同 layer 解析出不一致的 fill/text 时,首次注册胜出,后续不一致写到 `_meta.warnings`
- **容错降级**: 单节点 transform panic 时输出 `{id: "_err_xxx", type: "error", ...}` 占位节点,不中断整体输出
- **未识别字段不静默丢**: transform 用 `LAYER_HANDLED` / `BASIC_HANDLED` 集合标记已消费字段,其余进 `_meta.unhandledFields` → Mockplus 改 schema 立刻可见

输出 JSON 字段速览见 `SKILL.md` 的 "输出 JSON 速览" 章节。
