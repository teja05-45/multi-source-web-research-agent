from app.processing.normalizer import canonicalize_url, extract_domain


def test_strips_tracking_params():
    a = canonicalize_url("https://example.com/article?utm_source=google&utm_medium=cpc")
    b = canonicalize_url("https://example.com/article")
    assert a == b


def test_removes_fragment():
    assert canonicalize_url("https://example.com/page#section2") == canonicalize_url("https://example.com/page")


def test_removes_trailing_slash():
    assert canonicalize_url("https://example.com/page/") == canonicalize_url("https://example.com/page")


def test_root_path_slash_preserved():
    assert canonicalize_url("https://example.com/") == canonicalize_url("https://example.com")


def test_lowercases_host():
    assert canonicalize_url("https://Example.COM/Page") == canonicalize_url("https://example.com/Page")


def test_drops_default_ports():
    assert canonicalize_url("https://example.com:443/page") == canonicalize_url("https://example.com/page")
    assert canonicalize_url("http://example.com:80/page") == canonicalize_url("http://example.com/page")


def test_preserves_meaningful_query_params():
    a = canonicalize_url("https://example.com/search?q=foo")
    b = canonicalize_url("https://example.com/search?q=bar")
    assert a != b


def test_extract_domain_strips_www():
    assert extract_domain("https://www.example.com/page") == "example.com"


def test_extract_domain_no_www():
    assert extract_domain("https://blog.example.com/page") == "blog.example.com"
