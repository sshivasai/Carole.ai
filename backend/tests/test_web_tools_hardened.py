import json
import os
import pytest

from core.tools.network_clients import ToolNetworkError
from core.tools.web_tools import (
    DownloadStore,
    web_tools,
    _clip,
    _extract_links,
    FORBIDDEN_REQUEST_HEADERS,
)


def test_download_store_lifecycle():
    store = DownloadStore(max_files=5, max_total_bytes=1000)
    data1 = b"Hello, World!"
    path1 = store.save(data1, ".txt")
    assert os.path.exists(path1)
    assert path1.endswith(".txt")
    with open(path1, "rb") as f:
        assert f.read() == data1

    data2 = b"Another test content"
    path2 = store.save(data2, ".pdf")
    assert os.path.exists(path2)
    assert path2.endswith(".pdf")

    # Release path1
    assert store.release(path1) is True
    assert not os.path.exists(path1)
    # Releasing again returns False
    assert store.release(path1) is False

    # Close store
    store.close()
    assert not os.path.exists(path2)


def test_download_store_bounds():
    store = DownloadStore(max_files=2, max_total_bytes=100)
    # File larger than total capacity is rejected
    with pytest.raises(ToolNetworkError):
        store.save(b"A" * 150, ".txt")

    # Save 2 files
    f1 = store.save(b"12345", ".txt")
    f2 = store.save(b"67890", ".txt")

    # Saving a 3rd file reaches file count limit and raises ToolNetworkError
    with pytest.raises(ToolNetworkError):
        store.save(b"abcde", ".txt")

    store.close()


def test_extract_links_from_html():
    html = """
    <html>
        <body>
            <a href="https://example.com/page1">Page 1</a>
            <a href="/relative/path">Relative</a>
            <a href="javascript:void(0)">JS Link</a>
            <a href="mailto:test@example.com">Email</a>
            <a href="https://example.com/page1#hash">Page 1 Hash</a>
            <a href="https://example.com/page2">Page 2</a>
        </body>
    </html>
    """
    links = _extract_links(html, page_url="https://example.com/base/", limit=5)
    urls = [item["url"] for item in links]
    # javascript and mailto should be excluded, relative resolved
    assert "https://example.com/page1" in urls
    assert "https://example.com/relative/path" in urls
    assert "https://example.com/page2" in urls
    assert not any("javascript" in u for u in urls)
    assert not any("mailto" in u for u in urls)


@pytest.mark.asyncio
async def test_web_extract_links_validation():
    res = await web_tools.web_extract_links("ftp://example.com")
    assert "Error:" in res

    res_priv = await web_tools.web_extract_links("http://127.0.0.1")
    assert "Error:" in res_priv


@pytest.mark.asyncio
async def test_http_request_forbidden_headers():
    for forbidden in FORBIDDEN_REQUEST_HEADERS:
        res = await web_tools.http_request(
            url="https://example.com",
            method="GET",
            headers={forbidden: "forbidden_val"},
        )
        assert "Error:" in res
        assert "transport-controlled" in res


@pytest.mark.asyncio
async def test_http_request_rejects_ssrf():
    res = await web_tools.http_request(url="http://169.254.169.254/latest/meta-data")
    assert "Error:" in res

    res = await web_tools.http_request(url="http://localhost:8000/api")
    assert "Error:" in res


def test_clip_helper():
    short = "Hello"
    assert _clip(short, 10) == "Hello"

    long_text = "A" * 50
    clipped = _clip(long_text, 20)
    assert len(clipped.split("\n\n")[0]) == 20
    assert "[Content truncated]" in clipped
