# mockplus-context

[![CI](https://github.com/MySwallow/mockplus-context/actions/workflows/ci.yml/badge.svg)](https://github.com/MySwallow/mockplus-context/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Skill: Claude Code](https://img.shields.io/badge/Skill-Claude%20Code%20%2F%20claude.ai-7C3AED)](https://docs.claude.com/en/docs/claude-code/skills)

> 让 **AI 看懂 Mockplus(摹客)设计稿**的 Skill。装到 Claude Code / claude.ai 后,你只需要把 Mockplus URL 贴给 AI,AI 就能拿到结构化 YAML + 切图 + 整页截图,直接生成 Vue / React / Flutter / 小程序代码 —— 不再让 AI 看 PNG 截图猜规格。

## 这不是 CLI,这是 Skill

你**不需要敲命令**。装好 skill 之后,Mockplus 设计稿在 AI 那里变成"原生消费品":

```
你 → AI: "把这个还原成 Vue 组件:
         https://app.mockplus.cn/app/<APP>/develop/design/<PAGE>"

AI → (内部自动)  mockplus data <URL>        # 拿 YAML
                mockplus download <URL> ... # 按需下切图
                把 YAML 翻译成 <template> + <style>

AI → 你: 这是 src/views/Home.vue 完整组件 + 已下到 public/assets/ 的切图
```

## 为什么这事重要

| 路径 | 精度 | 速度 | 一致性 |
|---|---|---|---|
| 让 AI 看 PNG 截图猜规格 | 估算,字号/字重靠猜,常 ±5px 误差 | 慢 | 同一张图每次重写答案可能不同 |
| **用这个 skill** | **Sketch 导出的原始 token**,字节级精确 | 一秒内 | 设计师改动同步反映 |

## AI 工作流(典型 5 步)

收到 Mockplus URL 时,AI 自动按这个顺序工作 —— 不需要你提醒:

1. **检查 cookie**(首次使用引导你 30 秒配一次,后续 30 天免)
2. **若 URL 是 group 而非 page,先列树找 page id**
3. **拉 YAML** — 含整页 metadata、节点树、token 表(fill/layout/textStyle)
4. **扫 YAML 收集需要的切图 hash,按需下载** — 只下 LLM 实际需要的,不下全部
5. **基于 YAML 写代码**(Vue/React/Flutter/小程序均可,设计 token 直接映射成 CSS 变量 / Tailwind class)

## AI 看到的数据长这样

> 以下是字段形态示意,所有名称、ID、hash 均为占位符。

```yaml
metadata:
  name: <PAGE_NAME>
  pageId: <PAGE_ID>
  device: ios1x
  size: { width: 375, height: 812 }
  components:                          # SymbolInstance 反推的组件库注册表
    <library>/<component>: { id, name, libraryName }

nodes:
  - id: <UUID>
    name: <node-name>
    type: TEXT                         # FRAME / TEXT / INSTANCE / RECTANGLE / ELLIPSE / VECTOR
    layout: layout_000001              # 引用 globalVars.styles
    fills: fill_000001
    text: "<text-content>"
    textStyle: <sharedStyle.name>      # ← 设计师命名(原样)保留语义,不是 hash
    children: [...]

globalVars:
  styles:
    fill_000002:                       # 切图填充 — AI 看到这个会调 download
      - type: IMAGE
        imageRef: <hash>               # ← hash 跟 ./assets/<hash>.png 一一对应
        scaleMode: FILL
    layout_000001:
      mode: none
      locationRelativeToParent: { x: <int>, y: <int> }
      dimensions: { width: <int>, height: <int> }
    <sharedStyle.name>:                # token key 直接复用设计师在 Mockplus 里定义的名字
      fontFamily: <font>
      fontWeight: <weight>
      fontSize: <px>

_meta:
  unhandledFields: []                  # Mockplus schema 升级时这里会列字段
```

**关键设计:**

- **Token 复用** — 相同 fill/layout/effect 自动去重,节点上只放引用,YAML 体积下降 ~60%
- **文字样式 key 用设计师命名**(`sharedStyle.name`) — AI 写代码时可以直接复用作 CSS 变量名,语义不丢
- **切图按需** — AI 看 YAML 才决定下哪些图,不会盲下整页几十张
- **`_meta.unhandledFields` 探针** — Mockplus 升级 schema 时立刻可见,不静默丢字段

## 一站式产物

```bash
# AI 内部会跑(或者你也可以直接给 AI 说"用 all 一次拿齐")
mockplus all <URL> ./design-cache
```

产物结构:

```
./design-cache/
├── data.yaml         # 结构化页面数据(给 AI 写代码用)
├── design.png        # 整页 @2x 截图(视觉对照用)
└── assets/           # 所有切图(<hash>.png + <hash>.svg)
```

AI 同时拿到 YAML(写代码)+ design.png(视觉对比)+ 切图(`<img src>`),一气呵成。

## 安装

把仓库 clone 到 Claude Code 的 skills 目录(skill 自包含):

```bash
# Claude Code 用户
git clone https://github.com/MySwallow/mockplus-context.git ~/.claude/skills/mockplus-context

# 安装 skill 唯一外部依赖
pip install PyYAML
```

首次使用时 AI 会引导你配 Mockplus cookie(浏览器登录后 F12 复制,30 秒搞定,见 [`docs/cookie.md`](docs/cookie.md))。之后 30 天内无需再配。

> claude.ai / Cursor / 其他 skill-aware AI 平台:把 `skills/mockplus-context/` 目录按各自平台的 skill 安装规范放进去即可。

## 触发场景(AI 会自动用这个 Skill,不用你提醒)

- 你粘贴任何 `mockplus.cn` / `app.mockplus.cn` / `idoc` URL
- 你说"Mockplus / 摹客"加任何设计/原型/页面/标注/切图字眼
- Mockplus 链接 + "看看"、"按这个做"、"还原"、"转成 Vue/React/Flutter/小程序"、"对比"、"取源数据"、"拿标注"、"导出切图"

**不会触发:** Figma 链接(用 `figma-context`)、孤立 PNG/PDF 截图、本地 .sketch 解析、"想做一个像 Mockplus 的工具"、Mockplus 桌面客户端 bug 提问。

## 仓库布局

```
mockplus-context/
├── README.md / CHANGELOG.md / LICENSE     # 项目门面
├── docs/                                  # 给真人开发者/用户看
│   ├── architecture.md                    # 模块拆分与设计原理
│   ├── cookie.md                          # cookie 获取与轮换
│   └── superpowers/                       # 内部 spec/plan 档案
├── tests/                                 # pytest(开发者)
└── skills/
    └── mockplus-context/                  # ← skill 本体(自包含,LLM 直接消费)
        ├── SKILL.md                       # LLM 入口(触发条件 + 输出契约 + 失败处理)
        ├── scripts/                       # Python 实现(LLM 间接调用)
        │   ├── mockplus.py                # argparse 入口
        │   ├── cli.py                     # 5 个 action 实现
        │   ├── transform.py               # sketch JSON → 结构化 YAML
        │   └── client.py                  # API + cookie + CDN 下载
        └── references/                    # LLM 按需深读
            ├── examples.md                # 端到端调用样例
            └── troubleshooting.md         # 错误码 + 诊断
```

## 升级到 v0.5

v0.5 是 breaking change(从 JSON / hash token key 升级到 YAML / 设计师命名 token key)。如果你之前用 v0.4 老 CLI 命令,迁移指令见 [CHANGELOG.md](CHANGELOG.md) Migration 段(命令映射表 + cookie 路径迁移一键脚本)。

## 隐私 & 安全

- skill 只读 cookie,**不上传、不存储任何远程位置**
- cookie 自动 `~/.config/mockplus/cookie` 系统级保存,`chmod 600`,父目录 `chmod 700`
- API 中间产物 cache 在 `~/.cache/mockplus/`(可被 `MOCKPLUS_CACHE_DIR` 覆盖)
- 切图产物保存到用户指定目录,**默认不污染任何 git 仓库**

## 开发者文档

如果你想给这个 skill 提 PR 或自己 fork 改:

- 架构与设计原理:[`docs/architecture.md`](docs/architecture.md)
- 跑测试:`pip install -r tests/requirements.txt && pytest tests/`
- 命令行细节(如果你不通过 AI 也想直接调):看 [`skills/mockplus-context/SKILL.md`](skills/mockplus-context/SKILL.md) 的"命令速查"段

## License

MIT
