from __future__ import annotations

import pytest

from medusa.report import safe_url


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "  javascript:alert(1)",
    "vbscript:msgbox(1)",
    "ftp://example.org/x",
    "//evil.example.org",
    'https://x.org/a"><script>',  # a URL carrying raw HTML metacharacters is dropped entirely
    "",
    None,
])
def test_safe_url_drops_non_http_schemes(url: str | None) -> None:
    # retrieved-literature URLs are untrusted; only clean http(s) may become a clickable href
    assert safe_url(url) == ""


@pytest.mark.parametrize("url", [
    "https://arxiv.org/abs/2401.00001",
    "http://openalex.org/W123",
    "https://doi.org/10.1000/xyz",
])
def test_safe_url_keeps_http_and_escapes(url: str) -> None:
    assert safe_url(url) == url


def test_safe_url_escapes_ampersands_in_kept_urls() -> None:
    assert safe_url("https://x.org/s?a=1&b=2") == "https://x.org/s?a=1&amp;b=2"
