# mockplus-context

> 从 Mockplus(摹客)设计稿抓取**结构化 JSON + 切图**。Python 单文件 skill,无运行时外部依赖。

供 Claude / Cursor 等 LLM 直接消费。粘贴一个 Mockplus develop URL,LLM 就能拿到分层 JSON(metadata + globalVars + nodes),按需下载切图,然后还原 UI 代码。

## 仓库布局

```
mockplus-context/                          # repo root
├── README.md / CHANGELOG.md / LICENSE     # 项目门面
├── docs/                                  # 给真人开发者/用户看
│   ├── architecture.md
│   └── cookie.md
├── tests/                                 # 开发者跑 pytest
└── skills/
    └── mockplus-context/                  # skill 自包含 - LLM 直接消费
        ├── SKILL.md                       # LLM 入口
        ├── scripts/                       # Python CLI
        ├── references/                    # LLM 按需深读
        │   ├── api-reference.md
        │   ├── examples.md
        │   └── troubleshooting.md
        └── config/                        # 运行时 cookie(gitignored)
```

设计原则:`skills/mockplus-context/` 下的所有内容都是 **LLM runtime 直接消费的**——SKILL.md 入口、scripts 是 CLI、references 是 LLM 按需触发的深度参考、config 是 cookie 运行时位置。给真人看的(架构详解、cookie 抓取流程)在 repo root 的 `docs/`。

## 能力

- 把 Mockplus 单页设计稿转换为结构化 JSON(沿用 Sketch 原生 bounds 字段,LLM 写 CSS 直觉一致)
- 浏览 Mockplus 项目的 group / page 树
- 并发下载 Mockplus CDN 上的切图(`.png`)
- cookie 全生命周期管理(`set` / `test` / `status` / `clear` / `path`)
- `inspect` 子命令做回归检测(统计 + 异常)

> Mockplus API 的物理约束:**只能按整页(page)** 拉数据。Group/sub-group 没有节点级 API,所以拉数据只接受 page URL;group 浏览靠 `tree`。

## 安装

只要 Python 3.8+ 即可:

```bash
git clone https://github.com/<you>/mockplus-context.git
cd mockplus-context
python3 skills/mockplus-context/scripts/mockplus.py --help
```

加 alias 用着更顺手:

```bash
alias mockplus='python3 /path/to/mockplus-context/skills/mockplus-context/scripts/mockplus.py'
mockplus --help
```

下文示例假设已配好 `mockplus` alias。

## 5 分钟上手

```bash
# 1. 配 cookie(一次)
mockplus cookie set        # 粘贴浏览器 cookie

# 2. 验证
mockplus cookie test <任意 APP_ID>

# 3. 拉单页结构化 JSON
mockplus get-data 'https://app.mockplus.cn/app/<APP_ID>/develop/design/<PAGE_ID>' > page.json

# 4. 拉切图(把 page.json 里 asset.url 喂过来)
mockplus download-assets \
  --downloads '[{"url":"https://img02.mockplus.cn/.../<hash>.png","fileName":"nav-back.png"}]' \
  --local-path ./assets
```

cookie 怎么从浏览器抓取,详见 `docs/cookie.md`。

## 命令一览

| 命令 | 说明 |
|---|---|
| `mockplus get-data <URL>` | 单页结构化 JSON(stdout) |
| `mockplus tree <APP_ID> [--format text\|json]` | 项目结构(浏览 group/page) |
| `mockplus download-assets --downloads '[...]' --local-path <DIR>` | 并发下载切图 |
| `mockplus inspect <URL>` | 统计 + 异常(回归检测) |
| `mockplus cookie set [--from-file PATH]` | 写 cookie |
| `mockplus cookie test <APP_ID>` | 验证 cookie |
| `mockplus cookie status` | cookie 状态 |
| `mockplus cookie clear` | 删 cookie |
| `mockplus cookie path` | 打印 cookie 路径 |

命令完整签名见 `skills/mockplus-context/references/api-reference.md`。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MOCKPLUS_COOKIE` | (空) | 优先于文件 |
| `MOCKPLUS_COOKIE_FILE` | `skills/mockplus-context/config/cookie` | 覆盖 cookie 文件位置 |
| `MOCKPLUS_OUT_ROOT` | `~/.cache/mockplus-context` | API 响应 cache 根 |

## 文档导航

| 文档 | 受众 | 内容 |
|---|---|---|
| `skills/mockplus-context/SKILL.md` | LLM | skill 入口 |
| `skills/mockplus-context/references/api-reference.md` | LLM | 命令完整签名 |
| `skills/mockplus-context/references/examples.md` | LLM | 端到端调用样例 |
| `skills/mockplus-context/references/troubleshooting.md` | LLM | 错误处理建议 |
| `docs/architecture.md` | 开发者 | 模块拆分 / 关键设计决策 |
| `docs/cookie.md` | 真人用户 | cookie 获取与配置详解 |

## 开发 / 测试

```bash
python3 -m pip install --user -r tests/requirements.txt
python3 -m pytest tests/ -v
```

## 许可证

MIT
