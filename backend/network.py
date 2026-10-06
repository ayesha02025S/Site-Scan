import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from aiohttp.abc import AbstractResolver


class ScanError(ValueError):
    pass


def public_ip(value):
    address = ipaddress.ip_address(value.split("%")[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def validate_url(value):
    value = value.strip()
    if (
        not value
        or len(value) > 2048
        or any(ord(c) < 33 for c in value)
        or "\\" in value
    ):
        raise ScanError("Enter a valid public website URL.")
    if "://" not in value:
        value = "https://" + value
    try:
        parsed = urlsplit(value)
        port = parsed.port
        host = parsed.hostname
    except ValueError:
        raise ScanError("Enter a valid public website URL.")
    if (
        parsed.scheme not in ("http", "https")
        or not host
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ScanError("Use an HTTP or HTTPS URL without embedded credentials.")
    if port not in (None, 80, 443):
        raise ScanError("Only standard website ports 80 and 443 are supported.")
    host = host.lower().rstrip(".")
    if (
        host == "localhost"
        or host.endswith((".localhost", ".local", ".internal"))
        or "%" in host
    ):
        raise ScanError("Private and local network addresses cannot be scanned.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not public_ip(str(address)):
        raise ScanError("Private and local network addresses cannot be scanned.")
    host = host.encode("idna").decode("ascii")
    if ":" in host:
        host = f"[{host}]"
    if port and port != (443 if parsed.scheme == "https" else 80):
        host = f"{host}:{port}"
    return parsed._replace(netloc=host, path=parsed.path or "/", fragment="").geturl()


class PublicResolver(AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        entries = await asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM, family=family
        )
        if not entries or any(not public_ip(item[4][0]) for item in entries):
            raise ScanError(
                "This hostname resolves to a private or restricted network address."
            )
        return [
            {
                "hostname": host,
                "host": item[4][0],
                "port": port,
                "family": item[0],
                "proto": item[2],
                "flags": socket.AI_NUMERICHOST,
            }
            for item in entries
        ]

    async def close(self):
        pass
