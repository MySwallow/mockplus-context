"""编码回归:Windows 反馈 data.yaml 里中文全是 �(如 `�ݷü�¼�б�` = "拜访记录列表")。

根因:Path.read_text/write_text 不带 encoding 时跟随系统 locale(中文 Windows = GBK/cp936),
文件按 GBK 写出,Claude Code / 编辑器按 UTF-8 读就成了乱码。

本机(macOS/Linux)复现方式:LC_ALL=C + 关掉 PEP 538(locale 强制)/PEP 540(UTF-8 模式),
locale 编码退化为 ASCII —— 修复前写中文直接 UnicodeEncodeError(用例变红),
修复后所有文件读写与 stdout/stderr 固定 UTF-8,与 locale 无关。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "mockplus-context" / "scripts"
FIXTURES = Path(__file__).parent / "fixtures"

sys.path.insert(0, str(SCRIPTS))
import client  # noqa: E402

PAGE_NAME = "拜访记录列表"  # 反馈里乱码成 �ݷü�¼�б� 的页名
INDEX = {"code": 0, "payload": {"pages": [{
    "_id": "pg1", "name": PAGE_NAME, "device": "ios1x",
    "size": {"width": 375, "height": 812},
    "dataURL": "https://example.com/pg1.json",
}]}}


# ------------------------------------------------------------
# 非 UTF-8 locale 子进程环境
# ------------------------------------------------------------

def _non_utf8_env(cache_dir: Path) -> dict:
    env = {**os.environ,
           "MOCKPLUS_CACHE_DIR": str(cache_dir),
           "MOCKPLUS_COOKIE": "fake=1",
           "LC_ALL": "C", "LANG": "C", "LC_CTYPE": "C",
           "PYTHONCOERCECLOCALE": "0", "PYTHONUTF8": "0"}
    env.pop("PYTHONIOENCODING", None)
    return env


@pytest.fixture(scope="module")
def non_utf8_locale_works():
    """自证前提:该环境下 Python 的 locale 编码确实不是 UTF-8,否则用例会空过。"""
    probe = subprocess.run(
        [sys.executable, "-c",
         "import locale, sys; print(locale.getpreferredencoding(False)); "
         "print(sys.stdout.encoding)"],
        env=_non_utf8_env(Path(".")), capture_output=True, text=True)
    enc = probe.stdout.strip().lower().replace("-", "")
    if "utf8" in enc:
        pytest.skip(f"此平台无法关闭 UTF-8 模式(probe={enc!r}),无法模拟 Windows locale")
    return enc


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """预热 24h 内的新鲜缓存,子进程完全不触网。"""
    (tmp_path / "app1").mkdir(parents=True)
    (tmp_path / "app1" / "_index.json").write_text(
        json.dumps(INDEX, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "app1" / "pg1").mkdir()
    shutil.copy(FIXTURES / "simple-text.json", tmp_path / "app1" / "pg1" / "data.json")
    return tmp_path


def _run(cache: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "mockplus.py"), *argv],
        env=_non_utf8_env(cache), capture_output=True, cwd=str(ROOT))


def test_data_out_file_is_utf8_under_non_utf8_locale(non_utf8_locale_works, cache_dir):
    """反馈的原路径:`all`/`data --out data.yaml` 在 GBK locale 下写文件。"""
    out = cache_dir / "data.yaml"
    proc = _run(cache_dir, "data", "app1:pg1", "--out", str(out))
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    text = out.read_bytes().decode("utf-8")   # GBK 字节在这里会直接抛 UnicodeDecodeError
    assert f"name: {PAGE_NAME}" in text
    assert "�" not in text


def test_data_stdout_is_utf8_under_non_utf8_locale(non_utf8_locale_works, cache_dir):
    """`data` 走 stdout(重定向/管道场景)同样固定 UTF-8。"""
    proc = _run(cache_dir, "data", "app1:pg1")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert f"name: {PAGE_NAME}" in proc.stdout.decode("utf-8")


def test_tree_emoji_and_cjk_stdout_under_non_utf8_locale(non_utf8_locale_works, cache_dir):
    """`tree` 打 emoji + 中文到 stdout,修复前在 ASCII/GBK locale 下 UnicodeEncodeError。"""
    proc = _run(cache_dir, "tree", "app1")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert f"📄 {PAGE_NAME}" in proc.stdout.decode("utf-8")


def test_cookie_set_stdin_is_utf8_under_non_utf8_locale(non_utf8_locale_works, tmp_path):
    """`cookie set` 从管道读入(stdin)同样固定 UTF-8:含中文注释不乱码、不崩。"""
    cookie_fp = tmp_path / "cfg" / "cookie"
    env = {**_non_utf8_env(tmp_path), "MOCKPLUS_COOKIE_FILE": str(cookie_fp)}
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "mockplus.py"), "cookie", "set"],
        input="# 备注:测试账号\nsid=abc123\n".encode("utf-8"),
        env=env, capture_output=True, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert cookie_fp.read_bytes().decode("utf-8").endswith("sid=abc123\n")


# ------------------------------------------------------------
# 升级路径:v0.7.0 在 Windows 上按 GBK 写出的旧缓存
# ------------------------------------------------------------

def test_legacy_gbk_cache_is_ignored_and_refetched(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MOCKPLUS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("MOCKPLUS_COOKIE", "fake=1")
    fp = tmp_path / "app1" / "_index.json"
    fp.parent.mkdir(parents=True)
    fp.write_bytes(json.dumps(INDEX, ensure_ascii=False).encode("gbk"))  # 新鲜但 GBK

    monkeypatch.setattr(client, "_get",
                        lambda *a, **kw: json.dumps(INDEX, ensure_ascii=False).encode("utf-8"))
    assert client.fetch_index("app1") == INDEX
    assert "不是 UTF-8 JSON" in capsys.readouterr().err
    assert json.loads(fp.read_text(encoding="utf-8")) == INDEX  # 重写后已是 UTF-8


def test_legacy_gbk_cache_offline_raises_original_error(tmp_path, monkeypatch):
    """GBK 旧缓存 + 断网:过期回退也拒收,抛原网络错误而不是 UnicodeDecodeError。"""
    monkeypatch.setenv("MOCKPLUS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("MOCKPLUS_COOKIE", "fake=1")
    fp = tmp_path / "app1" / "_index.json"
    fp.parent.mkdir(parents=True)
    fp.write_bytes(json.dumps(INDEX, ensure_ascii=False).encode("gbk"))

    def _no_net(*a, **kw):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(client, "_get", _no_net)
    with pytest.raises(urllib.error.URLError):
        client.fetch_index("app1")


# ------------------------------------------------------------
# 静态守门:scripts/ 里任何文本 open/read_text/write_text 必须显式 encoding
# ------------------------------------------------------------

_CALL_RE = re.compile(r"(?:(?<![\w.])open|\.(?:read_text|write_text))\(")


def _call_text(src: str, start: int) -> str:
    """从 '(' 位置取到配对的 ')'(足够应付本仓库的调用形态,不处理字符串里的括号)。"""
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    return src[start:]


def _bare_text_io_calls(path: Path) -> list:
    src = path.read_text(encoding="utf-8")
    bad = []
    for m in _CALL_RE.finditer(src):
        call = _call_text(src, m.end() - 1)
        if "encoding=" in call or re.search(r"""['"][rwa]b['"]""", call):
            continue
        bad.append(f"{path.name}:{src.count(chr(10), 0, m.start()) + 1}: {m.group(0)}{call[1:40]}")
    return bad


@pytest.mark.parametrize("script", sorted(SCRIPTS.glob("*.py")), ids=lambda p: p.name)
def test_scripts_never_rely_on_locale_encoding(script):
    assert _bare_text_io_calls(script) == []
