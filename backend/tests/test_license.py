"""Round-trip tests for offline license signing/verification (desktop build)."""
import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import licensing


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


@pytest.fixture
def keypair():
    priv = Ed25519PrivateKey.generate()
    pub_b64 = _b64url(
        priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    )
    return priv, pub_b64


def _issue(priv, machines, product="ubos", licensee="Test"):
    payload = {"product": product, "version": 1, "licensee": licensee, "machines": machines}
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = priv.sign(payload_bytes)
    return f"{_b64url(payload_bytes)}.{_b64url(sig)}"


def test_valid_machine_passes(keypair):
    priv, pub = keypair
    lic = _issue(priv, ["MID-A", "MID-B"])
    ok, payload, reason = licensing.verify_license(lic, "MID-A", pub)
    assert ok is True and reason == "ok"
    assert payload["licensee"] == "Test"


def test_second_machine_passes(keypair):
    priv, pub = keypair
    lic = _issue(priv, ["MID-A", "MID-B"])
    ok, _, _ = licensing.verify_license(lic, "MID-B", pub)
    assert ok is True


def test_unlicensed_machine_fails(keypair):
    priv, pub = keypair
    lic = _issue(priv, ["MID-A", "MID-B"])
    ok, _, reason = licensing.verify_license(lic, "MID-C", pub)
    assert ok is False and "not licensed" in reason


def test_third_machine_ignored_beyond_max(keypair):
    priv, pub = keypair
    # even if a token lists 3, only the first 2 are honored
    lic = _issue(priv, ["MID-A", "MID-B", "MID-C"])
    assert licensing.verify_license(lic, "MID-A", pub)[0] is True
    assert licensing.verify_license(lic, "MID-C", pub)[0] is False


def test_tampered_payload_fails(keypair):
    priv, pub = keypair
    lic = _issue(priv, ["MID-A", "MID-B"])
    head, sig = lic.split(".")
    tampered = head[:-2] + ("AA" if head[-2:] != "AA" else "BB") + "." + sig
    ok, _, reason = licensing.verify_license(tampered, "MID-A", pub)
    assert ok is False


def test_wrong_key_fails(keypair):
    priv, _ = keypair
    lic = _issue(priv, ["MID-A"])
    other_pub = _b64url(
        Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    )
    ok, _, _ = licensing.verify_license(lic, "MID-A", other_pub)
    assert ok is False


def test_missing_public_key_fails(keypair):
    priv, _ = keypair
    lic = _issue(priv, ["MID-A"])
    ok, _, reason = licensing.verify_license(lic, "MID-A", "")
    assert ok is False and "no public key" in reason


def test_wrong_product_fails(keypair):
    priv, pub = keypair
    lic = _issue(priv, ["MID-A"], product="other")
    ok, _, reason = licensing.verify_license(lic, "MID-A", pub)
    assert ok is False and "not a UBOS license" in reason


def test_machine_id_is_stable_and_formatted():
    a = licensing.machine_id()
    b = licensing.machine_id()
    assert a == b
    assert a.startswith("UBOS-") and len(a.split("-")) == 6
