"""
# backend/core/tools/ssrf_guard.py

Network and SSRF protection utility for Carole.ai.

Design for Local-First Developer Tool:
- Explicitly ALLOWS localhost (127.0.0.1, ::1, localhost, 0.0.0.0) and local dev ports (3000, 5173, 8000, 8080, etc.)
  when allow_local=True so agents can inspect and test user-developed web applications and services.
- Strictly BLOCKS dangerous cloud metadata endpoints (169.254.169.254, metadata.google.internal, 169.254.0.0/16)
  to protect the host from cloud credential exfiltration if running inside a cloud VM / hybrid environment.
- Enforces safe URL schemes (http, https).
"""

import ipaddress
import socket
import urllib.parse
from typing import Optional

# Cloud metadata hostnames and IP ranges to block under all circumstances
BLOCKED_METADATA_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
}

BLOCKED_METADATA_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local (AWS/GCP/Azure IMDS)
    ipaddress.ip_network("fe80::/10"),        # IPv6 Link-Local
]


def assert_safe_public_url(url: str, allow_local: bool = True) -> str:
    """
    Validates that a URL is safe to fetch.
    
    Args:
        url: The target URL string.
        allow_local: If True (default for local development tool), loopback and private LAN IPs are permitted.
                     If False, only public internet IPs are permitted.

    Returns:
        The validated URL string if safe.

    Raises:
        ValueError: If the URL scheme is unsupported or targets a blocked cloud metadata endpoint.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string.")

    url_clean = url.strip()
    parsed = urllib.parse.urlparse(url_clean)

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Unsafe or unsupported URL scheme '{parsed.scheme}'. Only http:// and https:// are allowed.")

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        raise ValueError("URL is missing a valid hostname.")

    # 1. Block known cloud metadata hostnames
    if hostname in BLOCKED_METADATA_HOSTS:
        raise ValueError(f"Access to cloud metadata service '{hostname}' is blocked for security.")

    # 2. Check if hostname is an IP literal or resolves to an IP
    try:
        ip_obj = ipaddress.ip_address(hostname)
        # Check cloud metadata link-local range
        for net in BLOCKED_METADATA_NETWORKS:
            if ip_obj in net:
                raise ValueError(f"Access to link-local / cloud metadata range ({ip_obj}) is blocked.")

        if not allow_local:
            if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_reserved or ip_obj.is_unspecified:
                raise ValueError(f"Access to private or local network address ({ip_obj}) is disallowed in strict mode.")
    except ValueError as e:
        # Not a valid IP literal; resolve DNS to verify IP target
        if "is blocked" in str(e) or "is disallowed" in str(e):
            raise
        try:
            resolved_ips = socket.getaddrinfo(hostname, None)
            for item in resolved_ips:
                sockaddr = item[4]
                ip_str = sockaddr[0]
                ip_resolved = ipaddress.ip_address(ip_str)
                for net in BLOCKED_METADATA_NETWORKS:
                    if ip_resolved in net:
                        raise ValueError(f"Hostname '{hostname}' resolves to blocked metadata address ({ip_resolved}).")
                if not allow_local:
                    if ip_resolved.is_loopback or ip_resolved.is_private or ip_resolved.is_reserved or ip_resolved.is_unspecified:
                        raise ValueError(f"Hostname '{hostname}' resolves to private address ({ip_resolved}).")
        except socket.gaierror:
            # DNS resolution will fail later during actual fetch; allow URL to proceed
            pass

    return url_clean
