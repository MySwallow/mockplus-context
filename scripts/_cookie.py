"""Cookie 加载与管理子命令。
   优先级: env MOCKPLUS_COOKIE > MOCKPLUS_COOKIE_FILE > <repo_root>/config/cookie
"""
import os
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COOKIE_FILE = REPO_ROOT / "config" / "cookie"
COOKIE_TTL_DAYS = 30  # 估算到期


def cookie_file_path() -> Path:
    env = os.environ.get("MOCKPLUS_COOKIE_FILE")
    return Path(env) if env else DEFAULT_COOKIE_FILE


def load_cookie() -> str:
    """返回 cookie 字符串;未配置返回空字符串。"""
    env = os.environ.get("MOCKPLUS_COOKIE")
    if env:
        return env.strip()
    fp = cookie_file_path()
    if fp.exists():
        text = fp.read_text()
        # 跳过 `# set_at:` `# expires_at:` 注释行
        return "".join(l for l in text.splitlines() if not l.startswith("#")).strip()
    return ""


def require_cookie() -> str:
    c = load_cookie()
    if not c:
        print("ERR: cookie 未配置,运行 `mockplus cookie set`", file=sys.stderr)
        sys.exit(10)
    return c


def _write_cookie(content: str) -> None:
    fp = cookie_file_path()
    fp.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    set_at = int(time.time())
    expires_at = set_at + COOKIE_TTL_DAYS * 86400
    body = (
        f"# set_at: {set_at}\n"
        f"# expires_at: {expires_at}\n"
        f"{content.strip()}\n"
    )
    fp.write_text(body)
    os.chmod(fp.parent, 0o700)
    os.chmod(fp, 0o600)


def cmd_cookie(args):
    sub = args.cookie_cmd

    if sub == "set":
        if args.from_file:
            p = Path(args.from_file)
            if not p.exists():
                print(f"ERR: 文件不存在: {p}", file=sys.stderr)
                return 11
            content = p.read_text()
        elif sys.stdin.isatty():
            print("粘贴 cookie(单行),回车结束:", file=sys.stderr)
            content = sys.stdin.readline()
        else:
            content = sys.stdin.read()
        if not content.strip():
            print("ERR: cookie 为空", file=sys.stderr)
            return 12
        _write_cookie(content)
        print(f"OK: cookie 已写入 {cookie_file_path()}", file=sys.stderr)
        return 0

    if sub == "test":
        from _api import test_cookie
        return test_cookie(args.app_id)

    if sub == "status":
        fp = cookie_file_path()
        if not fp.exists():
            print(f"Status: 未配置(运行 mockplus cookie set)")
            print(f"Path:   {fp}")
            return 0
        text = fp.read_text()
        set_at = expires_at = None
        for line in text.splitlines():
            if line.startswith("# set_at:"):
                set_at = int(line.split(":", 1)[1].strip())
            elif line.startswith("# expires_at:"):
                expires_at = int(line.split(":", 1)[1].strip())
        now = int(time.time())
        print(f"Path:    {fp}")
        print(f"Mode:    {oct(fp.stat().st_mode & 0o777)}")
        if set_at:
            print(f"SetAt:   {time.ctime(set_at)}")
        if expires_at:
            days_left = (expires_at - now) // 86400
            print(f"Expires: {time.ctime(expires_at)} ({days_left} 天后)")
        return 0

    if sub == "clear":
        fp = cookie_file_path()
        if fp.exists():
            fp.unlink()
            print(f"OK: 已删除 {fp}", file=sys.stderr)
        return 0

    if sub == "path":
        print(cookie_file_path())
        return 0

    return 2
