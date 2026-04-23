"""Local IP detection for TUI status bar.

Prefers private RFC1918 LAN addresses (what mobile devices on same Wi-Fi
can actually reach) over public/default-route IPs.
"""

import re
import subprocess


def _is_private(ip: str) -> bool:
    if ip.startswith("192.168."):
        return True
    if ip.startswith("10."):
        return True
    if ip.startswith("172."):
        try:
            second = int(ip.split(".")[1])
            return 16 <= second <= 31
        except (IndexError, ValueError):
            return False
    return False


def _is_usable(ip: str) -> bool:
    if ip.startswith("127.") or ip.startswith("169.254."):
        return False
    return True


def _collect_interface_ips() -> list[str]:
    """Parse ifconfig output to collect all usable IPv4 addresses."""
    try:
        out = subprocess.run(
            ["ifconfig"], capture_output=True, text=True, timeout=2
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    ips = []
    for line in out.splitlines():
        match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", line)
        if match:
            ip = match.group(1)
            if _is_usable(ip):
                ips.append(ip)
    return ips


def _default_route_ip() -> str | None:
    """Fallback: UDP dummy connect to learn default route IP."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip if _is_usable(ip) else None
    except Exception:
        return None


def get_local_ip() -> str:
    """Return the best LAN IP for mobile device proxy setup.

    Priority:
      1. Private RFC1918 LAN address (192.168.*, 10.*, 172.16-31.*)
      2. Any usable public IP from ifconfig
      3. Default-route IP (UDP trick)
      4. 127.0.0.1 fallback
    """
    ips = _collect_interface_ips()

    for ip in ips:
        if _is_private(ip):
            return ip

    if ips:
        return ips[0]

    fallback = _default_route_ip()
    if fallback:
        return fallback

    return "127.0.0.1"
