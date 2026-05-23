"""client.download_slices 测试。用本地 http.server 起一个临时 PNG。"""
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "skills" / "mockplus-context" / "scripts"))
import client


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


def test_download_via_local_server(tmp_path):
    server = _serve()
    port = server.server_address[1]
    slices = [
        {"hash": "abc123",
         "bitmapURL": f"http://127.0.0.1:{port}/abc123.png",
         "svgURL": ""},
        {"hash": "def456",
         "bitmapURL": f"http://127.0.0.1:{port}/def456.png",
         "svgURL": ""},
    ]
    stats = client.download_slices(slices, tmp_path)
    server.shutdown()
    assert stats["ok"] == 2 and stats["fail"] == 0
    assert (tmp_path / "abc123.png").exists()
    assert (tmp_path / "def456.png").exists()


def test_download_skip_cached(tmp_path):
    server = _serve()
    port = server.server_address[1]
    (tmp_path / "abc.png").write_bytes(b"existing")
    slices = [{"hash": "abc",
               "bitmapURL": f"http://127.0.0.1:{port}/abc.png",
               "svgURL": ""}]
    stats = client.download_slices(slices, tmp_path)
    server.shutdown()
    assert stats["cached"] == 1
    assert (tmp_path / "abc.png").read_bytes() == b"existing"


def test_extract_slices_all():
    data = {
        "layers": {"children": [
            {"basic": {"name": "icon-a"}, "bounds": {"width": 24, "height": 24},
             "slice": {"bitmapURL": "https://img02.mockplus.cn/idoc/sketch/h1/x.png",
                       "svgURL": "https://img02.mockplus.cn/idoc/sketch/h1/x.svg"}},
            {"basic": {"name": "no-slice"}, "bounds": {"width": 100, "height": 50}},
        ]}
    }
    slices = client.extract_slices(data)
    assert len(slices) == 1
    assert slices[0]["hash"] == "h1"


def test_extract_slices_filter_by_hash():
    data = {
        "layers": {"children": [
            {"basic": {"sourceID": "s1"},
             "slice": {"bitmapURL": "https://img02.mockplus.cn/idoc/sketch/h1/a.png"}},
            {"basic": {"sourceID": "s2"},
             "slice": {"bitmapURL": "https://img02.mockplus.cn/idoc/sketch/h2/b.png"}},
        ]}
    }
    s = client.extract_slices(data, wanted={"h1"})
    assert len(s) == 1 and s[0]["hash"] == "h1"
