"""
Bounded HTTP clients for tools.

APIHTTP:
    For fixed, application-controlled provider endpoints only.

PublicHTTP:
    For untrusted public URLs. Validates URLs and resolved addresses,
    checks every redirect, disables environment proxies and cookies,
    and bounds response size and execution time.

Neither client automatically retries requests. Retrying POST requests can
duplicate side effects or provider charges.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import math
import socket
from dataclasses import dataclass
from typing import Any

import aiohttp
import httpx
from aiohttp.abc import AbstractResolver
from yarl import URL

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024

# Reject address-transition mechanisms that may embed another destination.
_TRANSITION_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
    ipaddress.ip_network("2002::/16"),
    ipaddress.ip_network("2001::/32"),
)


class ToolNetworkError(Exception):
    """An intentionally sanitized error safe to return to tool callers."""


def bounded_number(
    value: Any,
    *,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number.")

    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(
            f"{name} must be between {minimum:g} and {maximum:g}."
        )
    return number


def bounded_integer(
    value: Any,
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer.")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _assert_public_ip(address: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if isinstance(address, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        ip = address
    else:
        address_str = str(address)
        if "%" in address_str:
            raise ToolNetworkError("Scoped IP addresses are not allowed.")

        try:
            ip = ipaddress.ip_address(address_str)
        except ValueError:
            raise ToolNetworkError("Invalid resolved IP address.") from None

    if (
        not ip.is_global
        or ip.is_multicast
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_reserved
    ):
        raise ToolNetworkError("The destination is not a public IP address.")

    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            raise ToolNetworkError("IPv4-mapped IPv6 addresses are not allowed.")
        if any(ip in network for network in _TRANSITION_NETWORKS):
            raise ToolNetworkError("IP transition addresses are not allowed.")


def validate_public_url(value: str) -> URL:
    """
    Validate URL syntax and literal IP addresses.

    Hostname addresses are additionally validated by PublicResolver at
    connection time. Calling this function alone is NOT sufficient SSRF
    protection for hostnames.
    """
    if not isinstance(value, str) or not value or len(value) > 8192:
        raise ToolNetworkError("URL must be a non-empty string under 8193 characters.")

    if "\\" in value or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise ToolNetworkError("URL contains forbidden characters.")

    try:
        url = URL(value)
        host = url.host
        port = url.port

        if url.scheme not in {"http", "https"}:
            raise ToolNetworkError("Only HTTP and HTTPS URLs are allowed.")
        if not host:
            raise ToolNetworkError("URL must include a hostname.")
        if host.lower() == "localhost" or host.lower().endswith(".localhost") or host.lower().endswith(".local"):
            raise ToolNetworkError("Localhost and local domains are not permitted.")
        if url.user is not None or url.password is not None:
            raise ToolNetworkError("Credentials in URLs are not allowed.")
        if port not in {80, 443}:
            raise ToolNetworkError("Only public HTTP ports 80 and 443 are allowed.")
        if "%" in host:
            raise ToolNetworkError("Scoped or escaped hostnames are not allowed.")

        try:
            ipaddress.ip_address(host)
        except ValueError:
            # The resolver checks all addresses before connection.
            pass
        else:
            _assert_public_ip(host)

        return url.with_fragment(None)
    except (ValueError, UnicodeError):
        raise ToolNetworkError("Invalid URL.") from None


class PublicResolver(AbstractResolver):
    """Resolve hostnames and reject the entire answer if any IP is non-public."""

    def __init__(self) -> None:
        self._resolver = aiohttp.DefaultResolver()

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: int = socket.AF_UNSPEC,
    ) -> list:
        results = await self._resolver.resolve(host, port, family)
        if not results:
            raise ToolNetworkError("Hostname did not resolve.")

        for result in results:
            _assert_public_ip(result["host"])

        return results

    async def close(self) -> None:
        await self._resolver.close()


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: dict[str, str]
    content: bytes
    url: str
    charset: str = "utf-8"

    @property
    def text(self) -> str:
        try:
            return self.content.decode(self.charset, errors="replace")
        except (LookupError, UnicodeError):
            return self.content.decode("utf-8", errors="replace")

    @property
    def mime_type(self) -> str:
        return self.headers.get("content-type", "").split(";", 1)[0].strip().lower()


class APIHTTP:
    """Reusable bounded client for application-controlled API URLs."""

    def __init__(self, concurrency: int = 8) -> None:
        self._client: httpx.AsyncClient | None = None
        self._semaphore = asyncio.Semaphore(concurrency)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0, pool=10.0),
                limits=httpx.Limits(
                    max_connections=16,
                    max_keepalive_connections=8,
                ),
                follow_redirects=False,
                trust_env=False,
            )
        return self._client

    async def request(
        self,
        method: str,
        url: str,
        *,
        max_bytes: int,
        deadline: float,
        **kwargs: Any,
    ) -> HTTPResult:
        async def perform() -> HTTPResult:
            async with self._semaphore:
                client = self._get_client()
                async with client.stream(method, url, **kwargs) as response:
                    # Never return raw provider errors: they may contain
                    # submitted text, account details, or other sensitive data.
                    if not 200 <= response.status_code < 300:
                        logger.warning(
                            "Provider request failed: status=%d",
                            response.status_code,
                        )
                        raise ToolNetworkError(
                            f"Provider returned HTTP {response.status_code}."
                        )

                    data = bytearray()
                    async for chunk in response.aiter_bytes(CHUNK_SIZE):
                        if len(data) + len(chunk) > max_bytes:
                            raise ToolNetworkError(
                                "Provider response exceeded the size limit."
                            )
                        data.extend(chunk)

                    return HTTPResult(
                        status=response.status_code,
                        headers=dict(response.headers),
                        content=bytes(data),
                        url=str(response.url),
                    )

        try:
            return await asyncio.wait_for(perform(), timeout=deadline)
        except asyncio.TimeoutError:
            raise ToolNetworkError("Provider request timed out.") from None
        except httpx.RequestError:
            logger.warning("Provider transport failure")
            raise ToolNetworkError("Could not contact the provider.") from None

    async def aclose(self) -> None:
        # Call only after application requests have drained.
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()


class PublicHTTP:
    """
    Public-only arbitrary HTTP transport.

    Each operation gets an isolated session:
      - no cookie persistence or cross-request credential state;
      - no connection reuse across independently validated operations;
      - DNS addresses are validated by the connector's resolver.

    The semaphore bounds concurrent operations within this process.
    """

    REDIRECT_STATUSES = {301, 302, 303, 307, 308}

    def __init__(self, concurrency: int = 8) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: bytes | None = None,
        timeout: float = 30.0,
        max_bytes: int = 10 * 1024 * 1024,
        follow_redirects: bool = False,
    ) -> HTTPResult:
        timeout = bounded_number(
            timeout, name="timeout", minimum=1, maximum=120
        )
        initial_url = validate_public_url(url)

        if follow_redirects and method not in {"GET", "HEAD"}:
            raise ValueError("Automatic redirects are only supported for GET/HEAD.")

        async def perform() -> HTTPResult:
            async with self._semaphore:
                resolver = PublicResolver()
                connector = aiohttp.TCPConnector(
                    resolver=resolver,
                    use_dns_cache=False,
                    force_close=True,
                    limit=1,
                )
                try:
                    async with aiohttp.ClientSession(
                        connector=connector,
                        cookie_jar=aiohttp.DummyCookieJar(),
                        trust_env=False,
                        auto_decompress=False,
                        timeout=aiohttp.ClientTimeout(
                            total=timeout,
                            connect=min(timeout, 10.0),
                        ),
                    ) as session:
                        current = initial_url
                        current_headers = dict(headers or {})
                        current_headers["Accept-Encoding"] = "identity"

                        for hop in range(6):
                            async with session.request(
                                method,
                                current,
                                headers=current_headers,
                                data=json_body,
                                allow_redirects=False,
                            ) as response:
                                if (
                                    follow_redirects
                                    and response.status in self.REDIRECT_STATUSES
                                ):
                                    location = response.headers.get("Location")
                                    if not location:
                                        raise ToolNetworkError(
                                            "Redirect response is missing Location."
                                        )
                                    if hop == 5:
                                        raise ToolNetworkError("Too many redirects.")

                                    if (
                                        "\\" in location
                                        or any(
                                            ord(char) <= 32 or ord(char) == 127
                                            for char in location
                                        )
                                    ):
                                        raise ToolNetworkError(
                                            "Redirect contains an invalid URL."
                                        )

                                    destination = validate_public_url(
                                        str(current.join(URL(location)))
                                    )
                                    if (
                                        current.scheme == "https"
                                        and destination.scheme != "https"
                                    ):
                                        raise ToolNetworkError(
                                            "HTTPS-to-HTTP redirects are not allowed."
                                        )

                                    # Do not forward caller-supplied credentials
                                    # or other custom headers across redirects.
                                    current_headers = {
                                        "User-Agent": "CaroleAI/1.0",
                                        "Accept-Encoding": "identity",
                                    }
                                    current = destination
                                    continue

                                encoding = response.headers.get(
                                    "Content-Encoding", "identity"
                                ).strip().lower()
                                if encoding not in {"", "identity"}:
                                    raise ToolNetworkError(
                                        "Server ignored the uncompressed-response "
                                        "request; compressed responses are not accepted."
                                    )

                                if (
                                    response.content_length is not None
                                    and response.content_length > max_bytes
                                ):
                                    raise ToolNetworkError(
                                        "Response exceeded the download size limit."
                                    )

                                data = bytearray()
                                async for chunk in response.content.iter_chunked(
                                    CHUNK_SIZE
                                ):
                                    if len(data) + len(chunk) > max_bytes:
                                        raise ToolNetworkError(
                                            "Response exceeded the download size limit."
                                        )
                                    data.extend(chunk)

                                return HTTPResult(
                                    status=response.status,
                                    headers={
                                        key.lower(): value
                                        for key, value in response.headers.items()
                                    },
                                    content=bytes(data),
                                    url=str(response.url),
                                    charset=response.charset or "utf-8",
                                )

                        raise ToolNetworkError("Too many redirects.")
                finally:
                    await resolver.close()

        try:
            # Includes waiting for the concurrency slot.
            return await asyncio.wait_for(perform(), timeout=timeout)
        except asyncio.TimeoutError:
            raise ToolNetworkError("HTTP request timed out.") from None
        except (aiohttp.ClientError, OSError):
            logger.warning("Public HTTP transport failure")
            raise ToolNetworkError("Could not complete the HTTP request.") from None
        except (ValueError, UnicodeError):
            raise ToolNetworkError("Invalid HTTP request or redirect.") from None
