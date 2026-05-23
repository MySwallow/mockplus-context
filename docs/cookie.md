# Cookie 配置与更新

`mockplus-context` 通过 Mockplus 的私有 cookie 调用 idoc API。
本文档讲清楚:**怎么拿 cookie、怎么写入、怎么更新、怎么保证安全**。

> **v0.4 → v0.5 迁移**:cookie 文件默认从 `skills/mockplus-context/config/cookie` 迁到系统级 `~/.config/mockplus/cookie`。如果你之前用的是仓库内路径,可以这样迁移:
>
> ```bash
> mkdir -p ~/.config/mockplus && chmod 700 ~/.config/mockplus
> mv skills/mockplus-context/config/cookie ~/.config/mockplus/cookie
> chmod 600 ~/.config/mockplus/cookie
> ```
>
> 或重跑 `mockplus cookie set` 一次。

## 为什么需要 cookie

Mockplus 没有公开 API,也没有 OAuth / API Token。所有 idoc 接口都靠浏览器的会话 cookie
鉴权。我们的方案就是把浏览器 cookie 拿出来,直接以"伪装成浏览器"的方式调 API。

这是事实上的"只读访问"——cookie 仅用来 GET 设计稿数据。但 cookie **理论上有写入权限**
(可以删页、改项目),所以**绝不要泄露**。

## 获取 cookie(浏览器侧)

1. 浏览器登录 `https://app.mockplus.cn`
2. 进入任一项目的开发模式(URL 形如 `/app/<APPID>/develop/design/<PAGEID>`)
3. 打开 DevTools → Application → Cookies → `https://app.mockplus.cn`
4. 把表格里**所有 cookie** 拼成一行,格式:
   ```
   name1=value1; name2=value2; name3=value3
   ```
   (用 `; ` 分隔,**注意分号后面有个空格**,跟 HTTP `Cookie:` header 规范一致)

关键 cookie 通常包括:`ds.sid`、`ds.sid.sig`、`mockuuid`、`_clck`、`_clsk` 等。
不确定的话**全拷过来**最稳。

**Chrome 偷懒法**:
1. DevTools → Network → 任意一个 `app.mockplus.cn` 的请求
2. Headers → Request Headers → 找 `Cookie:` 那一行
3. 复制冒号后面整条字符串(去掉前后空格)

## 写入(本地侧)

### 方式 A:交互式(推荐日常使用)

```bash
mockplus cookie set
# 粘贴 cookie(单行),回车结束:
# <粘贴你的 cookie 一行,回车>
# OK: cookie 已写入 /Users/xx/.config/mockplus/cookie
```

**默认位置**:cookie 写到 **`~/.config/mockplus/cookie`**(系统级,跨多个 clone / install 共享)。
要换位置用 `MOCKPLUS_COOKIE_FILE` 环境变量。

### 方式 B:从文件

```bash
# 临时把 cookie 写到文件
echo '_clck=...; mockuuid=...; ds.sid=...' > /tmp/mp.cookie

# 导入
mockplus cookie set --from-file /tmp/mp.cookie

# 用完立刻删源文件
shred -u /tmp/mp.cookie   # 或 rm -P
```

### 方式 C:环境变量(适合 CI / 临时会话)

```bash
export MOCKPLUS_COOKIE='_clck=...; mockuuid=...; ds.sid=...'
mockplus data <URL>
```

**优先级**:`MOCKPLUS_COOKIE`(环境变量)> `MOCKPLUS_COOKIE_FILE` > 默认 `~/.config/mockplus/cookie`。

## 验证

```bash
# 用任意一个你能访问的 APP_ID(从 URL 里 /app/XXX/ 段抠出)
mockplus cookie test <APP_ID>
# OK: code=0 项目页面数=12
```

如果报 `code != 0` 或非 0 退出:
- cookie 过期或被吊销 → 重新 `set`
- APP_ID 无权限 → 换一个你能访问的

## 查看状态

```bash
mockplus cookie status
# Path:    /Users/xx/.config/mockplus/cookie
# Mode:    0o600
# SetAt:   Thu May 22 13:35:00 2026
# Expires: Sat Jun 21 13:35:00 2026 (28 天后)
```

**注意**:`Expires` 是基于"假设 30 天"的估算,实际有效期可能更短或更长。
真正过期的判定标准是 `mockplus cookie test` 返回 `code != 0`。

## 更新 cookie(过期或主动轮换)

```bash
# 直接 set 会覆盖旧的(无需先 clear)
mockplus cookie set

# 或先清,再写
mockplus cookie clear
mockplus cookie set
```

## 删除

```bash
mockplus cookie clear
# OK: 已删除 /Users/xx/.config/mockplus/cookie
```

## 自定义存储位置

```bash
# 单次
MOCKPLUS_COOKIE_FILE=/path/to/cookie mockplus data <URL>

# 永久(写到 ~/.zshrc / ~/.bashrc)
export MOCKPLUS_COOKIE_FILE=$HOME/Secrets/mockplus.cookie
```

## 安全

| 风险 | 措施 |
|---|---|
| cookie 泄露到 git | 默认存在 `~/.config/mockplus/cookie`(系统级,不在仓库下) |
| cookie 泄露到 shell history | **绝不要** `mockplus cookie set "_clck=..."` 这种位置参数。本工具也没设计这种接口——只接受 stdin / `--from-file` / 环境变量 |
| cookie 泄露到日志 | 脚本所有日志走 stderr,从不打印 cookie 内容,debug 日志只打印 URL 不打印 header |
| cookie 文件被其他用户读 | 自动 `chmod 600`(只有 owner 可读写),父目录 `chmod 700` |
| 长期不轮换 | `cookie status` 显示剩余天数,过期前 `cookie set` 重写 |
| Linux 多用户共享机器 | 把存储位置改到加密目录:`MOCKPLUS_COOKIE_FILE=$HOME/.ecryptfs/mockplus.cookie` |

## 公共网络 / 误操作处置

如果意识到 cookie 可能已经泄露(贴到群里、提交进 git、上传到 pastebin 等):

1. **立刻** 在浏览器 Mockplus 设置里 logout(所有设备) — 会让所有 cookie 失效
2. 本地 `mockplus cookie clear`
3. 重新登录浏览器,重新 `mockplus cookie set`
