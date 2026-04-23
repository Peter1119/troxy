"""Tests for local IP detection.

Bug #3 regression: the old implementation used a UDP dummy-connect trick
which returned whatever the default route was. On a laptop with a VPN, that
meant the *tunnel* IP — unreachable from the phone on the same Wi-Fi. The
current implementation parses ``ifconfig`` and prefers private RFC1918
addresses. These tests pin down that priority so it can't silently regress.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from troxy.tui import network
from troxy.tui.network import _is_private, _is_usable, get_local_ip


# ----- pure helpers -----------------------------------------------------

@pytest.mark.parametrize(
    "ip,expected",
    [
        ("192.168.1.5", True),
        ("10.0.0.1", True),
        ("172.16.0.1", True),
        ("172.31.255.254", True),
        ("172.15.0.1", False),   # just outside 16-31
        ("172.32.0.1", False),   # just outside 16-31
        ("8.8.8.8", False),
        ("127.0.0.1", False),
        ("169.254.1.1", False),
    ],
)
def test_is_private(ip, expected):
    assert _is_private(ip) is expected


@pytest.mark.parametrize(
    "ip,expected",
    [
        ("192.168.1.5", True),
        ("10.0.0.1", True),
        ("8.8.8.8", True),
        ("127.0.0.1", False),
        ("127.9.9.9", False),
        ("169.254.1.1", False),
    ],
)
def test_is_usable(ip, expected):
    assert _is_usable(ip) is expected


# ----- end-to-end priority ---------------------------------------------

def test_get_local_ip_returns_string_ipv4():
    ip = get_local_ip()
    assert isinstance(ip, str)
    parts = ip.split(".")
    assert len(parts) == 4
    for part in parts:
        assert 0 <= int(part) <= 255


def test_prefers_private_over_public_when_both_present():
    """Bug #3 core case: VPN laptop has a public tunnel IP AND a LAN IP.

    The LAN IP (192.168.*) must win — that's what the phone can reach.
    """
    with patch.object(
        network, "_collect_interface_ips",
        return_value=["100.64.0.5", "8.8.8.8", "192.168.1.42"],
    ):
        assert get_local_ip() == "192.168.1.42"


def test_returns_first_usable_when_no_private_available():
    with patch.object(
        network, "_collect_interface_ips", return_value=["100.64.0.5", "8.8.8.8"]
    ):
        assert get_local_ip() == "100.64.0.5"


def test_falls_back_to_default_route_when_ifconfig_empty():
    with patch.object(network, "_collect_interface_ips", return_value=[]), \
         patch.object(network, "_default_route_ip", return_value="10.9.9.9"):
        assert get_local_ip() == "10.9.9.9"


def test_falls_back_to_loopback_when_all_discovery_fails():
    with patch.object(network, "_collect_interface_ips", return_value=[]), \
         patch.object(network, "_default_route_ip", return_value=None):
        assert get_local_ip() == "127.0.0.1"


def test_loopback_filtered_out_of_interface_list():
    """Even if ifconfig reports 127.0.0.1, we must not surface it to the user."""
    with patch.object(
        network, "_collect_interface_ips", return_value=["127.0.0.1", "192.168.0.9"]
    ):
        # 127.0.0.1 never makes it past _is_usable, so the private wins.
        assert get_local_ip() == "192.168.0.9"


def test_link_local_filtered_out():
    """169.254.* is APIPA, never reachable from a phone — must be dropped."""
    with patch.object(
        network, "_collect_interface_ips", return_value=["169.254.5.5", "192.168.0.9"]
    ):
        assert get_local_ip() == "192.168.0.9"


# ----- Gate-3 end-to-end scenarios (team-lead sign-off list) ---------
#
# Each scenario mocks ``subprocess.run`` so the real ``ifconfig`` binary is
# not invoked. This makes the test deterministic across dev machines and
# CI, but still exercises the real ``_collect_interface_ips`` parser —
# i.e. we're testing the parsing + priority pipeline end to end, not just
# the post-parse logic.
#
# ifconfig snippets are trimmed versions of real macOS output. The parser
# grabs the FIRST ``inet X.X.X.X`` match per line; multi-line interface
# blocks are fine so long as each ``inet`` line is on its own row.


def _mock_ifconfig(stdout: str):
    """Context-manager patch that makes subprocess.run return ``stdout``."""
    class _Result:
        def __init__(self, out): self.stdout = out
    return patch.object(
        network.subprocess, "run",
        return_value=_Result(stdout),
    )


WIFI_ONLY_IFCONFIG = """\
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.1.42 netmask 0xffffff00 broadcast 192.168.1.255
\tstatus: active
"""

WIRED_AND_WIFI_IFCONFIG = """\
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 10.0.0.5 netmask 0xffffff00 broadcast 10.0.0.255
\tstatus: active
en1: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.1.42 netmask 0xffffff00 broadcast 192.168.1.255
\tstatus: active
"""

PUBLIC_ONLY_IFCONFIG = """\
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 203.0.113.42 netmask 0xffffff00 broadcast 203.0.113.255
\tstatus: active
"""

ALL_DOWN_IFCONFIG = """\
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<BROADCAST,MULTICAST> mtu 1500
\tstatus: inactive
"""


def test_scenario_1_wifi_only_returns_private():
    """Scenario 1: single active Wi-Fi interface in 192.168.*."""
    with _mock_ifconfig(WIFI_ONLY_IFCONFIG):
        assert get_local_ip() == "192.168.1.42"


def test_scenario_2_wired_plus_wifi_returns_a_private():
    """Scenario 2: two active private interfaces.

    The priority spec does not pin which private wins — both are reachable
    from a phone on the same Wi-Fi. We just require the answer to be one of
    them, never the loopback or a public address.
    """
    with _mock_ifconfig(WIRED_AND_WIFI_IFCONFIG):
        result = get_local_ip()
        assert result in ("10.0.0.5", "192.168.1.42"), (
            f"expected one of the private IPs, got {result!r}"
        )


def test_scenario_3_public_only_returns_public():
    """Scenario 3: Wi-Fi off, only a public/default-route IP remains.

    Bug #3 did NOT mean "never return public" — it meant "prefer private".
    When no private is available, the public IP is the best we've got
    (e.g. co-working Wi-Fi without NAT, direct Ethernet).
    """
    with _mock_ifconfig(PUBLIC_ONLY_IFCONFIG):
        assert get_local_ip() == "203.0.113.42"


def test_scenario_4_all_down_falls_back_to_loopback():
    """Scenario 4: every usable interface is down / unconfigured.

    ``_default_route_ip`` is also unreachable (mocked), so the final
    fallback is 127.0.0.1. Surfacing it in the info bar at least tells the
    user "no network" rather than silently lying about a stale IP.
    """
    with _mock_ifconfig(ALL_DOWN_IFCONFIG), \
         patch.object(network, "_default_route_ip", return_value=None):
        assert get_local_ip() == "127.0.0.1"


def test_scenario_ifconfig_missing_falls_back_gracefully():
    """If ``ifconfig`` is not on PATH (Docker, stripped CI), we must not crash."""
    with patch.object(
        network.subprocess, "run", side_effect=FileNotFoundError("ifconfig")
    ), patch.object(network, "_default_route_ip", return_value="192.168.9.9"):
        assert get_local_ip() == "192.168.9.9"


def test_scenario_ifconfig_times_out_falls_back_gracefully():
    """Hung ``ifconfig`` must not hang the TUI startup."""
    import subprocess as sp
    with patch.object(
        network.subprocess, "run",
        side_effect=sp.TimeoutExpired(cmd="ifconfig", timeout=2),
    ), patch.object(network, "_default_route_ip", return_value="10.0.0.7"):
        assert get_local_ip() == "10.0.0.7"
