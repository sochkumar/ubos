"""Issue (sign) a UBOS license for up to 2 machines. Vendor-only tool.

    python desktop/licensing/issue_license.py \
        --private-key ./secret/ubos_private_key.pem \
        --licensee "Friend Name" \
        --machine UBOS-1A2B-3C4D-5E6F-7788-99AA \
        --machine UBOS-AAAA-BBBB-CCCC-DDDD-EEEE \
        --out ./ubos.lic

The friend runs the app's "Machine ID" screen on each PC and sends you the two
ids. Send them back the generated `ubos.lic`.
"""
from __future__ import annotations

import argparse
import base64
import json
from datetime import datetime, timezone

from cryptography.hazmat.primitives.serialization import load_pem_private_key

MAX_MACHINES = 2


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--private-key", required=True)
    ap.add_argument("--licensee", required=True)
    ap.add_argument("--machine", action="append", required=True,
                    help="machine id (repeat for the 2nd; max 2)")
    ap.add_argument("--out", default="./ubos.lic")
    args = ap.parse_args()

    machines = list(dict.fromkeys(args.machine))  # de-dupe, keep order
    if len(machines) > MAX_MACHINES:
        raise SystemExit(f"at most {MAX_MACHINES} machines allowed, got {len(machines)}")

    with open(args.private_key, "rb") as f:
        priv = load_pem_private_key(f.read(), password=None)

    payload = {
        "product": "ubos",
        "version": 1,
        "licensee": args.licensee,
        "machines": machines,
        "issued": datetime.now(timezone.utc).isoformat(),
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = priv.sign(payload_bytes)
    token = f"{b64url(payload_bytes)}.{b64url(sig)}"

    with open(args.out, "w") as f:
        f.write(token + "\n")

    print(f"License written -> {args.out}")
    print(f"  licensee: {args.licensee}")
    print(f"  machines: {machines}")


if __name__ == "__main__":
    main()
