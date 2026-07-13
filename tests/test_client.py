"""client.py 离线回退(_stale_fallback 及其两处接线)测试。

注入网络/cookie 失败 + 控制缓存 mtime,验证 v0.6 离线重转回退的边界:
≤7 天回退成功、>7 天拒绝、损坏缓存拒绝、--refresh 永不回退、
cookie 缺失(SystemExit)同样回退——这正是"离线重转本地缓存"的目标场景。
"""
import json
import os
import sys
import time
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "skills" / "mockplus-context" / "scripts"))
import client

INDEX = {"code": 0, "payload": {"pages": [{"_id": "pg1", "name": "n"}]}}
PAGE_DATA = {"layers": {"children": []}, "pluginVersion": "t"}


def _age(fp: Path, days: float) -> None:
    ts = time.time() - days * 86400
    os.utime(fp, (ts, ts))


def _write_index_cache(root: Path, age_days: float, text: str = None) -> Path:
    fp = root / "app1" / "_index.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(text if text is not None else json.dumps(INDEX))
    _age(fp, age_days)
    return fp


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """缓存目录隔离 + cookie 可用 + 网络必失败。"""
    monkeypatch.setenv("MOCKPLUS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("MOCKPLUS_COOKIE", "fake=1")

    def _no_net(*a, **kw):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(client, "_get", _no_net)
    return tmp_path


def test_fetch_index_offline_falls_back_to_stale_cache(offline, capsys):
    _write_index_cache(offline, age_days=2)
    assert client.fetch_index("app1") == INDEX
    assert "回退" in capsys.readouterr().err


def test_fetch_index_rejects_cache_older_than_cap(offline, capsys):
    _write_index_cache(offline, age_days=8)
    with pytest.raises(urllib.error.URLError):
        client.fetch_index("app1")
    assert "7 天上限" in capsys.readouterr().err


def test_fetch_index_rejects_corrupt_stale_cache(offline):
    _write_index_cache(offline, age_days=2, text="{not json")
    with pytest.raises(urllib.error.URLError):
        client.fetch_index("app1")


def test_fetch_index_refresh_never_falls_back(offline):
    _write_index_cache(offline, age_days=2)
    with pytest.raises(urllib.error.URLError):
        client.fetch_index("app1", refresh=True)


def test_fetch_index_missing_cookie_falls_back(tmp_path, monkeypatch):
    """cookie 未配置(sys.exit 10)也走回退——离线重转不该被认证挡住。"""
    monkeypatch.setenv("MOCKPLUS_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("MOCKPLUS_COOKIE", raising=False)
    monkeypatch.setenv("MOCKPLUS_COOKIE_FILE", str(tmp_path / "no-such-cookie"))
    _write_index_cache(tmp_path, age_days=2)
    assert client.fetch_index("app1") == INDEX


def test_page_data_offline_falls_back(offline, monkeypatch):
    fp = offline / "app1" / "pg1" / "data.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(PAGE_DATA))
    _age(fp, 2)

    def _no_cdn(page_meta):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(client, "fetch_page_data", _no_cdn)
    meta = {"id": "pg1", "dataURL": "https://img01.mockplus.cn/x"}
    assert client.get_page_data_cached("app1", meta) == PAGE_DATA


def test_page_data_rejects_cache_older_than_cap(offline, monkeypatch):
    fp = offline / "app1" / "pg1" / "data.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(PAGE_DATA))
    _age(fp, 8)

    def _no_cdn(page_meta):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(client, "fetch_page_data", _no_cdn)
    meta = {"id": "pg1", "dataURL": "https://img01.mockplus.cn/x"}
    with pytest.raises(urllib.error.URLError):
        client.get_page_data_cached("app1", meta)
