"""Helpers for onboard/doctor commands — kept out of setup_cmds.py to stay under the 300-line file-size cap."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import click


def generate_ca_cert(ca_path: Path, timeout: float = 8.0) -> tuple[bool, str]:
    """Boot mitmdump briefly so mitmproxy writes its CA cert, then stop it.

    Returns (success, stderr_tail). stderr is captured so the caller can
    surface bind errors (e.g. port 19481 already in use) to the user.
    """
    mitmdump = shutil.which("mitmdump")
    venv_mitmdump = os.path.join(os.path.dirname(sys.executable), "mitmdump")
    if os.path.exists(venv_mitmdump):
        mitmdump = venv_mitmdump
    if not mitmdump:
        return False, "mitmdump not found on PATH"

    ca_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [mitmdump, "--listen-port", "19481", "-q"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if ca_path.exists():
                return True, ""
            if proc.poll() is not None:
                break
            time.sleep(0.2)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    stderr = ""
    if proc.stderr is not None:
        try:
            stderr = proc.stderr.read().decode(errors="replace").strip()
        except Exception:
            stderr = ""
    return ca_path.exists(), stderr


_IOS_HINT = (
    "  🍎 iOS Simulator (macOS)\n"
    "    ① 시뮬레이터 부팅\n"
    "        open -a Simulator                       # 마지막에 쓴 시뮬레이터 자동 실행\n"
    "        # 특정 기기로 띄우려면:\n"
    "        xcrun simctl list devices available     # 사용 가능 기기 확인\n"
    "        xcrun simctl boot \"<디바이스명>\"\n"
    "    ② 프록시 설정\n"
    "        설정 → Wi-Fi → (i) → 프록시 구성 → 수동\n"
    "        서버: 127.0.0.1   포트: 8080\n"
    "\n"
    "  🔐 시뮬레이터에 CA 설치 (HTTPS 가로채려면 필수)\n"
    "    1. 다른 터미널에서 `troxy start` 실행 (계속 켜두기)\n"
    "    2. 시뮬레이터 → Safari → http://mitm.it 접속 → iOS 탭 → 다운로드 허용\n"
    "    3. 설정 → 일반 → VPN 및 기기 관리 → mitmproxy 프로파일 설치\n"
    "    4. 설정 → 일반 → 정보 → 인증서 신뢰 설정 → mitmproxy 토글 ON\n"
)

_ANDROID_HINT = (
    "  🤖 Android Emulator\n"
    "    ① 에뮬레이터를 프록시와 함께 부팅\n"
    "        emulator -avd <name> -http-proxy http://127.0.0.1:8080\n"
    "    ② 또는 실행 중인 에뮬레이터에서\n"
    "        설정 → 네트워크 → APN → 프록시\n"
    "\n"
    "  🔐 CA 설치\n"
    "    1. http://mitm.it 접속 → .cer 파일 다운로드\n"
    "    2. 설정 → 보안 → 저장소에서 설치\n"
    "  ⚠️  Android 7+ : 앱이 user CA를 신뢰하려면 network_security_config.xml 필요\n"
    '                  (<trust-anchors><certificates src="user"/></trust-anchors>)\n'
    "  ⚠️  Android 14+: production-signed 앱은 user CA 사용 제한 — debug 빌드만 가능\n"
)

_GENERIC_HINT = (
    "  📡 실제 기기\n"
    "    ① Wi-Fi 설정 → HTTP 프록시 → 수동 → 127.0.0.1 / 8080\n"
    "    ② 프록시 연결된 상태에서 http://mitm.it 접속 → CA 설치\n"
)

_WEB_HINT = (
    "  🌐 데스크톱 웹 브라우저 / CLI\n"
    "    ① Safari / Chrome / Edge — macOS 시스템 프록시 사용\n"
    "        시스템 설정 → 네트워크 → Wi-Fi → 세부사항 → 프록시\n"
    "          ☑︎ 웹 프록시(HTTP)      서버: 127.0.0.1   포트: 8080\n"
    "          ☑︎ 보안 웹 프록시(HTTPS) 서버: 127.0.0.1   포트: 8080\n"
    "        (onboard Step 2에서 시스템 키체인 신뢰 완료 시 HTTPS도 바로 복호화)\n"
    "\n"
    "    ② Firefox — 자체 프록시 + CA 필요\n"
    "        Settings → Network Settings → Manual proxy → 127.0.0.1 / 8080\n"
    "        about:preferences#privacy → Certificates → Import →\n"
    "          ~/.mitmproxy/mitmproxy-ca-cert.pem 선택 (Trust for websites 체크)\n"
    "\n"
    "    ③ curl / httpie / 기타 CLI\n"
    "        export HTTPS_PROXY=http://127.0.0.1:8080 HTTP_PROXY=http://127.0.0.1:8080\n"
    "        curl --cacert ~/.mitmproxy/mitmproxy-ca-cert.pem https://api.example.com\n"
    "\n"
    "    ⚠️  주의\n"
    "        • HSTS 캐시된 사이트는 프록시 통과 불가 → 새 브라우저 프로필에서 테스트\n"
    "        • Certificate pinning 사용 사이트(은행/결제)는 우회 불가\n"
)


def print_device_hints(platform: str | None) -> None:
    if platform == "ios-sim":
        click.echo(_IOS_HINT)
    elif platform == "android-emu":
        click.echo(_ANDROID_HINT)
    elif platform == "web":
        click.echo(_WEB_HINT)
    elif platform == "manual":
        click.echo(_GENERIC_HINT)
    else:
        click.echo(_IOS_HINT + "\n" + _ANDROID_HINT + "\n" + _WEB_HINT + "\n" + _GENERIC_HINT)
