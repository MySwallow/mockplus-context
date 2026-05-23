# mockplus-context

[![CI](https://github.com/MySwallow/mockplus-context/actions/workflows/ci.yml/badge.svg)](https://github.com/MySwallow/mockplus-context/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

> 从 Mockplus(摹客)设计稿抓取**结构化 YAML + 切图**。Python 实现,YAML 优先,按需下载。

供 Claude / Cursor 等 LLM 直接消费。粘贴一个 Mockplus develop URL,LLM 就能拿到分层 YAML(`metadata` + `nodes` + `globalVars.styles`),按需下载切图,然后还原 UI 代码。

## 精度对比

| 方式 | 精度 | 速度 |
|---|---|---|
| 让 LLM 看 PNG 截图猜 spec | 估算,常有 ±5px 误差,字号/字重靠猜 | 慢 |
| 用这个 skill | **从 Sketch 导出的原始 token**,字节级精确 | 一秒内 |

## 仓库布局

```
mockplus-context/                          # repo root
├── README.md / CHANGELOG.md / LICENSE     # 项目门面
├── docs/                                  # 给真人开发者/用户看
│   ├── architecture.md
│   ├── cookie.md
│   └── superpowers/                       # 内部 spec/plan(执行档案)
├── tests/                                 # pytest
└── skills/
    └── mockplus-context/                  # skill 自包含 - LLM 直接消费
        ├── SKILL.md                       # LLM 入口
        ├── scripts/                       # Python CLI(mockplus / cli / transform / client)
        └── references/                    # LLM 按需深读
            ├── examples.md
            └── troubleshooting.md
```

Cookie 默认在 `~/.config/mockplus/cookie`(系统级,跨多个 install 共享)。

## 5 分钟上手

```bash
# 1. clone
git clone https://github.com/MySwallow/mockplus-context.git
cd mockplus-context

# 2. 装 PyYAML
pip install PyYAML

# 3. 配 cookie(浏览器登录 mockplus.cn → F12 复制全部 cookie)
python3 skills/mockplus-context/scripts/mockplus.py cookie set

# 4. 拉数据
python3 skills/mockplus-context/scripts/mockplus.py data \
  'https://app.mockplus.cn/app/<APP>/develop/design/<PAGE>' --out page.yaml

# 5. 按需下切图(看 yaml 里 imageRef:<hash>)
python3 skills/mockplus-context/scripts/mockplus.py download \
  '<URL>' --nodes <hash1>,<hash2> --out ./assets

# 一站式拿齐 yaml + 切图 + 整页截图
python3 skills/mockplus-context/scripts/mockplus.py all '<URL>' ./my-page-dir
```

## 命令参考

| 命令 | 用途 |
|---|---|
| `mockplus data <URL> [--out PATH] [--format yaml\|json] [--stats]` | 拉结构化数据,默认 YAML 到 stdout |
| `mockplus download <URL> [--nodes all\|h1,h2] [--include-design]` | 按 hash 下切图,可加整页截图 |
| `mockplus all <URL> [<OUT_DIR>]` | 一站式 = data + download(all + design) |
| `mockplus tree <APP_ID> [--format text\|json]` | 树形浏览项目结构,找 page id |
| `mockplus cookie {set\|test\|status\|clear\|path}` | Cookie 管理 |

完整字段契约见 [`docs/architecture.md`](docs/architecture.md);Cookie 详细见 [`docs/cookie.md`](docs/cookie.md)。

## 升级(v0.4 → v0.5)

v0.5 是 breaking change,详见 [CHANGELOG.md](CHANGELOG.md) Migration 段。一句话总结:

- 命令重命名:`get-data` → `data`、`download-assets` → `download`、`inspect` → `data --stats`
- 输出默认从 JSON 改 YAML
- cookie 路径从 `skills/mockplus-context/config/cookie` 迁到 `~/.config/mockplus/cookie`
- download 接口改用 `--nodes hash,...`(从 YAML 里 `imageRef` 直取)

## 开发 / 测试

```bash
pip install -r tests/requirements.txt
pytest tests/
```

## 贡献

欢迎 PR。约定:

- 分支命名:`feat/<topic>` / `fix/<topic>` / `refactor/<topic>`
- 提交消息:`<type>: <description>`(type: feat/fix/refactor/docs/test/chore/perf/ci)
- Breaking change:在 CHANGELOG `Breaking` 段说明 + Migration 段提供命令映射

## License

MIT
