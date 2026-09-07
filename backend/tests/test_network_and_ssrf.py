import ipaddress
import pytest

from core.tools.network_clients import (
    ToolNetworkError,
    _assert_public_ip,
    validate_public_url,
    bounded_number,
    bounded_integer,
)


def test_assert_public_ip_accepts_public_ips():
    # Public IPv4 and IPv6
    _assert_public_ip(ipaddress.ip_address("8.8.8.8"))
    _assert_public_ip("8.8.8.8")
    _assert_public_ip(ipaddress.ip_address("1.1.1.1"))
    _assert_public_ip("1.1.1.1")
    _assert_public_ip(ipaddress.ip_address("2607:f8b0:4005:805::200e"))
    _assert_public_ip("2607:f8b0:4005:805::200e")


def test_assert_public_ip_rejects_private_and_special():
    blocked_ips = [
        "127.0.0.1",
        "127.0.0.53",
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.1.254",
        "169.254.169.254",  # AWS/cloud metadata
        "169.254.1.1",
        "0.0.0.0",
        "255.255.255.255",
        "224.0.0.1",        # Multicast
        "::1",              # IPv6 loopback
        "fe80::1",          # IPv6 link-local
        "::ffff:127.0.0.1", # IPv4-mapped IPv6 loopback
        "::ffff:10.0.0.1",  # IPv4-mapped IPv6 private
        "::ffff:169.254.169.254",
        "64:ff9b::1",       # NAT64
        "2002:a00:1::1",    # 6to4
        "2001::1",          # Teredo
    ]

    for ip_str in blocked_ips:
        with pytest.raises(ToolNetworkError):
            _assert_public_ip(ip_str)
        with pytest.raises(ToolNetworkError):
            _assert_public_ip(ipaddress.ip_address(ip_str))


def test_validate_public_url_valid():
    u1 = validate_public_url("https://example.com")
    assert str(u1) == "https://example.com"

    u2 = validate_public_url("http://example.com:80/path?query=1#frag")
    assert u2.host == "example.com"
    assert u2.port == 80

    u3 = validate_public_url("https://sub.domain.org/test")
    assert u3.scheme == "https"
    assert u3.port == 443


def test_validate_public_url_invalid_schemes():
    invalid_schemes = [
        "ftp://example.com",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "gopher://example.com",
        "ws://example.com",
        "data:text/plain;base64,SGVsbG8=",
    ]
    for url in invalid_schemes:
        with pytest.raises(ToolNetworkError):
            validate_public_url(url)


def test_validate_public_url_forbidden_ports():
    invalid_ports = [
        "http://example.com:8080",
        "https://example.com:8443",
        "http://example.com:22",
        "https://example.com:3000",
        "http://example.com:6379",
    ]
    for url in invalid_ports:
        with pytest.raises(ToolNetworkError):
            validate_public_url(url)


def test_validate_public_url_forbidden_credentials():
    with pytest.raises(ToolNetworkError) as exc:
        validate_public_url("http://user:password@example.com")
    assert "credentials" in str(exc.value).lower()

    with pytest.raises(ToolNetworkError) as exc:
        validate_public_url("http://user@example.com")
    assert "credentials" in str(exc.value).lower()


def test_validate_public_url_rejects_localhost_and_private_ips():
    bad_urls = [
        "http://localhost",
        "http://localhost:80",
        "http://sub.localhost",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "http://192.168.1.1",
        "http://169.254.169.254",
        "http://[::1]",
    ]
    for url in bad_urls:
        with pytest.raises(ToolNetworkError):
            validate_public_url(url)


def test_validate_public_url_rejects_control_characters():
    with pytest.raises(ToolNetworkError):
        validate_public_url("http://example.com\r\n/path")


def test_bounded_validators():
    assert bounded_integer(5, name="val", minimum=1, maximum=10) == 5
    assert bounded_integer(8, name="val", minimum=1, maximum=10) == 8

    with pytest.raises(ValueError):
        bounded_integer(0, name="val", minimum=1, maximum=10)

    with pytest.raises(ValueError):
        bounded_integer(11, name="val", minimum=1, maximum=10)

    with pytest.raises(ValueError):
        bounded_integer("not_an_int", name="val", minimum=1, maximum=10)

    assert bounded_number(1.5, name="val", minimum=0.5, maximum=2.0) == 1.5
    assert bounded_number(1.25, name="val", minimum=0.5, maximum=2.0) == 1.25

    with pytest.raises(ValueError):
        bounded_number(0.2, name="val", minimum=0.5, maximum=2.0)

    with pytest.raises(ValueError):
        bounded_number(2.5, name="val", minimum=0.5, maximum=2.0)
