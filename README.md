# mockplus-context

> 从 Mockplus(摹客)设计稿抓取**结构化 JSON + 切图**,接口对齐 figma-context MCP 心智模型。Python 单文件 skill,无外部依赖。

## 与 figma-context 的对照

| | figma-context | mockplus-context |
|---|---|---|
| 拿数据 | `get_figma_data(fileKey, nodeId?)` | `get-data <URL>`(仅整页,Mockplus API 物理约束) |
| 下图 | `download_figma_images(nodes[], localPath)` | `download-assets --downloads '[{url,fileName}]' --local-path` |
| 项目浏览 | LLM 自己从 file 推 | `tree <APP_ID>` 浏览 group/page 树 |
| 输出 | typed JSON(globalVars+nodes) | 同结构,字段沿用 Sketch 原生命名(bounds.top/left/width/height) |

## 安装

只要 Python 3.8+ 即可:

```bash
git clone https://github.com/<you>/mockplus-context.git
cd mockplus-context
python3 scripts/mockplus.py --help
```

加 PATH 后用着方便:

```bash
alias mockplus='python3 /path/to/mockplus-context/scripts/mockplus.py'
mockplus --help
```

## 5 分钟上手

```bash
# 1. 配 cookie(一次)
mockplus cookie set        # 粘贴浏览器 cookie

# 2. 验证
mockplus cookie test <任意 APP_ID>

# 3. 拉单页结构化 JSON
mockplus get-data 'https://app.mockplus.cn/app/<APP_ID>/develop/design/<PAGE_ID>' > page.json

# 4. 拉切图(把 page.json 里的 asset.url 喂过来)
mockplus download-assets \
  --downloads '[{"url":"https://img02.mockplus.cn/.../<hash>.png","fileName":"nav-back.png"}]' \
  --local-path ./assets
```

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

详见 `docs/api-reference.md`。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MOCKPLUS_COOKIE` | (空) | 优先于文件 |
| `MOCKPLUS_COOKIE_FILE` | `config/cookie` | 覆盖 cookie 文件位置 |
| `MOCKPLUS_OUT_ROOT` | `~/.cache/mockplus-context` | API 响应 cache 根 |

## 文档

| 文档 | 内容 |
|---|---|
| `SKILL.md` | LLM 入口(给 Claude / Cursor 等读) |
| `docs/specs/2026-05-22-skill-redesign-design.md` | 设计 spec |
| `docs/api-reference.md` | 命令完整签名 |
| `docs/architecture.md` | 模块划分 |
| `docs/cookie.md` | cookie 获取 / 配置 |
| `docs/troubleshooting.md` | 故障排查 |
| `docs/examples.md` | 使用示例 |

## 开发 / 测试

```bash
python3 -m pip install --user -r tests/requirements.txt
python3 -m pytest tests/ -v
```

## 许可证

MIT
