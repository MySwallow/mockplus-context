# config/

`mockplus-context` 的运行时配置目录。

## 文件

| 文件 | 内容 | 入库? |
|---|---|---|
| `cookie` | Mockplus 认证 cookie(单行)+ 注释(`set_at` / `expires_at`) | **否**(`.gitignore`) |
| `cookie.bak` | 自动创建的 cookie 备份(暂未启用,占位) | 否 |
| `README.md` | 本文件 | 是 |

## Cookie 管理

通过 CLI 操作,不要手工编辑:

```bash
mockplus cookie set       # 写入(stdin / --from-file)
mockplus cookie status    # 查看路径 / 权限 / 到期
mockplus cookie test <APP_ID>   # 验证有效性
mockplus cookie clear     # 删除
```

详见 [docs/cookie.md](../docs/cookie.md)。

## 不在这里!

- 输出的设计稿数据 → `./mockplus-cache/`(可通过 `MOCKPLUS_OUT_ROOT` 改)
- 临时文件 → `mktemp`,不放仓库
