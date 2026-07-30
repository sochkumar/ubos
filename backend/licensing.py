"""Offline license verification + machine fingerprinting (desktop build).

A license is a signed token: `b64url(payload_json) . b64url(ed25519_sig)`.
The payload names the licensee and the machine ids it is valid for (max 2).
Only the PUBLIC key ships in the app; the private key stays with the vendor and
is used by `desktop/licensing/issue_license.py` to sign licenses.

Verification is fully offline: check the Ed25519 signature with the embedded
public key, then confirm the current machine id is in the licensed list.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import subprocess

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Base64url of the 32-byte Ed25519 public key. Set at build time (env or here)
# after running `desktop/licensing/keygen.py`. Empty => licensing not configured
# (the boot gate treats that as "unlicensed" in desktop mode).
LICENSE_PUBLIC_KEY_B64 = os.environ.get("UBOS_LICENSE_PUBLIC_KEY", "")

MAX_MACHINES = 2
PRODUCT = "ubos"


# ─────────────────────── machine fingerprint ───────────────────────
def _windows_fingerprint() -> str:
    import winreg  # noqa: PLC0415 (Windows-only)
    import ctypes

    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
    ) as k:
        guid, _ = winreg.QueryValueEx(k, "MachineGuid")
    serial = ctypes.c_uint()
    try:
        ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p("C:\\"), None, 0, ctypes.byref(serial), None, None, None, 0
        )
    except Exception:
        serial.value = 0
    return f"{guid}:{serial.value}"


def _macos_fingerprint() -> str:
    out = subprocess.check_output(
        ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], text=True
    )
    for line in out.splitlines():
        if "IOPlatformUUID" in line:
            return line.split('"')[-2]
    return ""


def _linux_fingerprint() -> str:
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(p) as f:
                v = f.read().strip()
                if v:
                    return v
        except OSError:
            continue
    return ""


def raw_fingerprint() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            return _windows_fingerprint()
        if system == "Darwin":
            return _macos_fingerprint()
        return _linux_fingerprint() or platform.node()
    except Exception:
        return platform.node()


def machine_id() -> str:
    """Stable, human-readable per-machine id, e.g. UBOS-1A2B-3C4D-5E6F-7788-99AA."""
    raw = raw_fingerprint() or platform.node() or "unknown"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    return "UBOS-" + "-".join(h[i : i + 4] for i in range(0, 20, 4))


# ─────────────────────── license verification ───────────────────────
def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify_license(
    license_str: str, current_machine_id: str, public_key_b64: str | None = None
) -> tuple[bool, dict | None, str]:
    """Returns (ok, payload, reason)."""
    pub_b64 = public_key_b64 if public_key_b64 is not None else LICENSE_PUBLIC_KEY_B64
    if not pub_b64:
        return False, None, "no public key configured"
    try:
        payload_b64, sig_b64 = license_str.strip().split(".")
        payload_bytes = _b64url_decode(payload_b64)
        sig = _b64url_decode(sig_b64)
        pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(pub_b64))
        pub.verify(sig, payload_bytes)  # raises InvalidSignature on mismatch
        payload = json.loads(payload_bytes)
    except InvalidSignature:
        return False, None, "signature invalid (tampered or wrong key)"
    except Exception as e:  # malformed token
        return False, None, f"malformed license: {e}"

    if payload.get("product") != PRODUCT:
        return False, payload, "not a UBOS license"
    machines = list(payload.get("machines") or [])[:MAX_MACHINES]
    if current_machine_id not in machines:
        return False, payload, "this machine is not licensed"
    return True, payload, "ok"


def verify_license_file(
    path: str, current_machine_id: str | None = None, public_key_b64: str | None = None
) -> tuple[bool, dict | None, str]:
    mid = current_machine_id or machine_id()
    try:
        with open(path) as f:
            return verify_license(f.read(), mid, public_key_b64)
    except OSError as e:
        return False, None, f"license file not readable: {e}"


if __name__ == "__main__":  # `python -m licensing` prints this machine's id
    print(machine_id())
