"""SSRF-safety helpers for server-side URL fetching.

Any URL the backend fetches (content fetcher for ranked sources) is passed
through `is_safe_to_fetch` first. This blocks obvious SSRF vectors: fetching
localhost, link-local, and private/internal IP ranges, plus non-http(s)
schemes. This is a practical mitigation, not a complete SSRF solution (see
README "Security" section for documented limitations — e.g. DNS rebinding
between the check and the actual request is not fully covered).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}

_BLOCKED_HOSTNAMES = {"localhost", "0.0.0.0", "metadata.google.internal"}


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # fail closed if we cannot parse it
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def is_safe_to_fetch(url: str, *, allow_private_network: bool = False) -> tuple[bool, str]:
    """Return (is_safe, reason). `reason` explains a rejection."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "unparseable_url"

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False, f"disallowed_scheme:{parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "missing_hostname"

    if hostname.lower() in _BLOCKED_HOSTNAMES and not allow_private_network:
        return False, "blocked_hostname"

    if allow_private_network:
        return True, "ok"

    # Resolve and check every returned address; block if any is private.
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False, "dns_resolution_failed"

    for info in infos:
        ip_str = info[4][0]
        if _is_private_ip(ip_str):
            return False, f"private_ip_blocked:{ip_str}"

    return True, "ok"
