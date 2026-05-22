"""assets 下载测试。用本地 http.server 起一个临时 PNG。"""
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _assets


# 最小合法 PNG(1x1 透明)
TINY_PNG = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000D4944415478DA63F8FFFF3F0005FE02FE9C5E1EFF0000000049454E44AE426082"
)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(TINY_PNG)

    def log_message(self, *a, **kw):
        pass


def _serve():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def test_invalid_host_rejected(tmp_path, capsys):
    class Args:
        downloads = json.dumps([{"url": "https://evil.com/x.png", "fileName": "x.png"}])
        local_path = str(tmp_path)
    _assets.cmd_download_assets(Args())
    out = json.loads(capsys.readouterr().out)
    assert len(out["failed"]) == 1
    assert out["failed"][0]["reason"] == "invalid host"


def test_non_png_extension_rejected(tmp_path, capsys):
    class Args:
        downloads = json.dumps([{"url": "https://img02.mockplus.cn/x.svg", "fileName": "x.svg"}])
        local_path = str(tmp_path)
    _assets.cmd_download_assets(Args())
    out = json.loads(capsys.readouterr().out)
    assert out["failed"][0]["reason"] == "unsupported format"


def test_filename_must_be_png(tmp_path, capsys):
    class Args:
        downloads = json.dumps([{"url": "https://img02.mockplus.cn/x.png", "fileName": "x.jpg"}])
        local_path = str(tmp_path)
    _assets.cmd_download_assets(Args())
    out = json.loads(capsys.readouterr().out)
    assert out["failed"][0]["reason"] == "filename must end with .png"


def test_download_via_local_server(tmp_path, capsys, monkeypatch):
    server = _serve()
    port = server.server_address[1]
    # Monkeypatch host regex to accept localhost for this test
    monkeypatch.setattr(_assets, "HOST_OK", re.compile(r"^http://127\.0\.0\.1:\d+/"))
    class Args:
        downloads = json.dumps([
            {"url": f"http://127.0.0.1:{port}/a.png", "fileName": "a.png"},
            {"url": f"http://127.0.0.1:{port}/b.png", "fileName": "b.png"},
        ])
        local_path = str(tmp_path)
    _assets.cmd_download_assets(Args())
    server.shutdown()
    out = json.loads(capsys.readouterr().out)
    assert len(out["downloaded"]) == 2
    assert (tmp_path / "a.png").exists()
    assert (tmp_path / "b.png").exists()


def test_download_skip_cached(tmp_path, capsys, monkeypatch):
    """文件已存在 + size > 0 应该 cached=True 而不重新下载。"""
    server = _serve()
    port = server.server_address[1]
    monkeypatch.setattr(_assets, "HOST_OK", re.compile(r"^http://127\.0\.0\.1:\d+/"))
    # 预先在 tmp_path 写一个 a.png
    (tmp_path / "a.png").write_bytes(b"existing content")
    class Args:
        downloads = json.dumps([{"url": f"http://127.0.0.1:{port}/a.png", "fileName": "a.png"}])
        local_path = str(tmp_path)
    _assets.cmd_download_assets(Args())
    server.shutdown()
    out = json.loads(capsys.readouterr().out)
    assert out["downloaded"][0].get("cached") is True
    # 文件没被覆盖
    assert (tmp_path / "a.png").read_bytes() == b"existing content"
