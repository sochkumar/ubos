"""Generate the vendor Ed25519 signing keypair (run ONCE, keep the private key).

    python desktop/licensing/keygen.py --out ./secret

Writes:
    secret/ubos_private_key.pem   ← KEEP SECRET. Never commit. Never ship.
    secret/ubos_public_key.txt    ← safe to embed in the app / commit.

Embed the printed public key in the app via env UBOS_LICENSE_PUBLIC_KEY or the
LICENSE_PUBLIC_KEY_B64 constant in backend/licensing.py.
"""
from __future__ import annotations

import argparse
import base64
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="./secret", help="output directory")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pub_b64 = b64url(pub_raw)

    priv_path = os.path.join(args.out, "ubos_private_key.pem")
    pub_path = os.path.join(args.out, "ubos_public_key.txt")
    with open(priv_path, "wb") as f:
        f.write(priv_pem)
    os.chmod(priv_path, 0o600)
    with open(pub_path, "w") as f:
        f.write(pub_b64 + "\n")

    print(f"Private key -> {priv_path}  (KEEP SECRET, never commit/ship)")
    print(f"Public key  -> {pub_path}")
    print(f"\nPublic key (embed this in the app):\n{pub_b64}")


if __name__ == "__main__":
    main()
