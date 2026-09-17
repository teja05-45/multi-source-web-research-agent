from app.security.url_safety import is_safe_to_fetch


def test_rejects_non_http_scheme():
    safe, reason = is_safe_to_fetch("file:///etc/passwd")
    assert not safe
    assert "scheme" in reason


def test_rejects_localhost():
    safe, reason = is_safe_to_fetch("http://localhost/admin")
    assert not safe


def test_rejects_loopback_ip():
    safe, reason = is_safe_to_fetch("http://127.0.0.1/admin")
    assert not safe


def test_rejects_private_ip_literal():
    safe, reason = is_safe_to_fetch("http://10.0.0.5/internal")
    assert not safe


def test_allows_public_https_url():
    safe, reason = is_safe_to_fetch("https://example.com/page")
    assert safe


def test_allow_private_network_flag_bypasses_dns_check():
    # Used only for controlled local/dev testing, off by default in config.
    safe, reason = is_safe_to_fetch("http://10.0.0.5/internal", allow_private_network=True)
    assert safe
